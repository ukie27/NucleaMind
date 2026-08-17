"""官方插件 `discord`：把实例接到一个 Discord bot 上（开发方案 `D33`）。

职责：声明一条 `CHANNEL` 能力，把 Discord 的消息翻成 `InboundMessage`、把
`OutboundMessage` 翻成发消息与流式编辑。
不负责：执行 turn、管理会话历史、路由命令（分别是 `kernel/turn/`、会话存储能力与
`kernel/routing/dispatcher.py` 的事）。

**它取代的是被 `D33` 删掉的 `legacy/channels/discord/`**，但不是移植：

- 旧实现的**配对码流程**没搬。它服务的 pairing store 与 WebUI 审批界面在 `D31` 已经删了，
  搬过来就是一条走不通的分支。新层的等价物是 `allow_from` 白名单（明确拒绝）+
  `permissions.json` 的 TOFU 模型。**代价如实说**：陌生人发 DM 从「收到一个配对码」
  变成「被静默忽略」。
- 旧实现注册的一整套 **Discord 原生 slash command** 没搬。命令只有
  `kernel/routing/dispatcher.py` 一个来源——再注册一套会让「命令有几个来源」变成两个
  答案。用户在 Discord 里打 `/help` 就是一条普通消息，由 `commands-core` 处理。
- 旧实现的 `ChannelSetupSpec` / `webui/index.ts` / 10 份 locale 没搬：那是 legacy WebUI 的
  契约，服务端已不存在。新层的同位物是 manifest 的 `config_schema` + `setup()` 里一次性校验。
- 旧实现的 `_StreamBuf` 与指示器缠在同一个类里，`discord.py` 的类型散布在 842 行里。
  这里按「碰不碰平台」切开：`gateway.py` 是唯一 import `discord` 的模块，其余全是纯函数或
  对 Protocol 编程，因此**不装 `discord.py` 也能跑绝大多数用例**。

**三条如实记着的边界**，写在这里而不是留给用户发现：

- **五种权限里没有「连接一个聊天平台」这一种**（`fs:read` / `fs:write` / `net` / `shell` /
  `secret`，其中 `net` 判的是经 `ctx.net` 门面的出站请求）。`discord.py` 自己开 WebSocket
  与 HTTPS，一个字节都不过门面，因此本插件除 `secret` 外一条权限都声明不出来，而它确实
  会连出去。这是权限模型当前的一个空档，与 `openai-api` 那条「没有『监听端口』」并列。
- **出站 workspace 附件传不出去**：`sdk.api.FileAccess` 只有 `read_text` / `write_text` /
  `list_dir`，没有 `read_bytes`，绕过 `ctx.fs` 直接 `open()` 会让权限声明变成谎话。
  今天新层没有任何地方产出带附件的 `OutboundMessage`，因此这是一条没有生产者的死路径；
  本插件发一条文本标记而不是假装发过。`FileAccess.read_bytes` 已记为契约变更候选。
- **应用级权限不是进程隔离**（`sdk/api.py` 的原话）。能在允许的频道里说话的人就能驱动
  实例上的全部工具，包括 `shell.exec`。`allow_from` 与 `allow_channels` 是唯一的闸门。
"""

from __future__ import annotations

from typing import Final

from nucleamind.contracts import CapabilityKind, ErrorCode, NucleaError, PermissionKind, SecretStr
from nucleamind.sdk import (
    CapabilityDecl,
    ManifestJsonSchema,
    NucleaAPI,
    PermissionDecl,
    PluginContext,
    PluginManifest,
)

from .channel import DiscordChannel
from .gateway import DiscordGateway, to_raw
from .indicators import Indicators
from .normalize import InboundGate, RawAttachment, RawAuthor, RawInbound, normalize
from .outbound import (
    MAX_MESSAGE_LENGTH,
    TERMINAL_MARKERS,
    SendPlan,
    plan_outbound,
    split_message,
)
from .settings import (
    CAPABILITY_NAME,
    CONFIG_KEYS,
    DEFAULT_INTENTS,
    SECRET_PROXY_PASSWORD,
    SECRET_TOKEN,
    DiscordSettings,
    resolve_settings,
)
from .stream import StreamRelay

__all__ = [
    "CAPABILITY_NAME",
    "CONFIG_KEYS",
    "CONFIG_SCHEMA",
    "DEFAULT_INTENTS",
    "MANIFEST",
    "MAX_MESSAGE_LENGTH",
    "SECRET_PROXY_PASSWORD",
    "SECRET_TOKEN",
    "TERMINAL_MARKERS",
    "DiscordChannel",
    "DiscordGateway",
    "DiscordSettings",
    "InboundGate",
    "Indicators",
    "RawAttachment",
    "RawAuthor",
    "RawInbound",
    "SendPlan",
    "StreamRelay",
    "normalize",
    "plan_outbound",
    "resolve_settings",
    "setup",
    "split_message",
    "to_raw",
]

#: 插件配置块的 JSON Schema。阶段 A 在**加载之前**按它校验一次形状，`settings.py` 在
#: `setup()` 里再按语义校验一次（取值之间的关系，例如代理三元组的完整性）。
#:
#: 标注成 `ManifestJsonSchema` 而不是 `contracts.JsonSchema`：契约那个类型进不了
#: pydantic 模型（会 `RecursionError`），细节与另外两个被否掉的候选见
#: `sdk/manifest.py::ManifestJsonValue`。`D41` 之前这里刻意不标注，因为当时的字段
#: 类型是 pydantic 的 `JsonValue`，`dict` 值不变导致嵌套字面量怎么标都不成子类型。
CONFIG_SCHEMA: Final[ManifestJsonSchema] = {
    "type": "object",
    "properties": {
        "channel_id": {"type": "string"},
        "instance_id": {"type": "string"},
        "allow_from": {"type": "array", "items": {"type": ["string", "integer"]}},
        "allow_channels": {"type": "array", "items": {"type": ["string", "integer"]}},
        "operators": {"type": "array", "items": {"type": ["string", "integer"]}},
        "group_policy": {"type": "string", "enum": ["mention", "open"]},
        # 位掩码，含义归 Discord 管。`minimum: 0` 而不是 1：0 是合法的（什么都不订阅），
        # 而任何下限都要能容纳真实用得上的值（`D31` 踩过 `port: 0`）。
        "intents": {"type": "integer", "minimum": 0},
        "streaming": {"type": "boolean"},
        "stream_edit_interval_ms": {"type": "integer", "minimum": 100},
        "read_receipt_emoji": {"type": "string"},
        "working_emoji": {"type": "string"},
        "working_emoji_delay_ms": {"type": "integer", "minimum": 0},
        "typing_interval_ms": {"type": "integer", "minimum": 1000},
        "max_attachment_bytes": {"type": "integer", "minimum": 1},
        "proxy": {"type": "string"},
        "proxy_username": {"type": "string"},
    },
    "additionalProperties": False,
}

MANIFEST: Final = PluginManifest(
    id="discord",
    version="0.1.0",
    sdk_range=">=1.0.0,<2.0.0",
    setup="nucleamind_plugin_discord:setup",
    # **不写 `overrides`**（它不取代任何内建）、**不写 `priority`**（默认值 100 会被原样
    # 采纳，而内建基准是 0——`D16` 记的坑）。
    capabilities=(CapabilityDecl(kind=CapabilityKind.CHANNEL, name=CAPABILITY_NAME),),
    # **只声明 secret**：`net` 判的是经 `ctx.net` 门面的出站请求，而 `discord.py` 自己开
    # 连接、一个字节都不过门面。声明一条门面根本不经过的权限会让「这个插件到底要什么」
    # 变模糊（`openai-api` 拒绝声明 `net` 的同一条理由）。空档如实写在模块 docstring 里。
    permissions=(
        PermissionDecl(
            kind=PermissionKind.SECRET,
            target=SECRET_TOKEN,
            reason="Discord bot token，用于登录 gateway。",
        ),
        PermissionDecl(
            kind=PermissionKind.SECRET,
            target=SECRET_PROXY_PASSWORD,
            reason="HTTP 代理的密码；没配代理时不会取用。",
        ),
    ),
    config_schema=CONFIG_SCHEMA,
    # `critical=False`：一个聊天平台连不上（token 过期、Discord 挂了、代理不通）不该让
    # CLI 与其它 Channel 一起下线。`PLG-004`：失败的后果由装配根决定。
    critical=False,
)

_MISSING_TOKEN: Final = "Discord Channel 必须配置 bot_token。"


def setup(api: NucleaAPI) -> None:
    """注册 Channel。配置与凭据在这里各解析一次，不拖到第一条消息（`D18` 的先例）。"""
    settings = resolve_settings(api.ctx)
    token = _required_secret(api.ctx)
    api.register_channel(
        CAPABILITY_NAME,
        DiscordChannel(
            settings,
            token=token,
            proxy_password=_optional_secret(api.ctx, SECRET_PROXY_PASSWORD),
        ),
    )


def _required_secret(ctx: PluginContext) -> SecretStr:
    """取 bot token。**没配就是配置错误**——一个没有 token 的 Discord Channel 连不上任何
    东西，让它「起来了但什么都不做」比直接说清楚更糟。

    未授权的 `PERMISSION_DENIED` 原样抛出：那与「没配」是两件事，补救动作也不同。
    """
    try:
        return ctx.secret(SECRET_TOKEN)
    except NucleaError as exc:
        if exc.code is ErrorCode.CONFIG_SECRET_MISSING:
            raise NucleaError(
                ErrorCode.CONFIG_INVALID,
                _MISSING_TOKEN,
                detail={
                    "pointer": f"/plugins/{MANIFEST.id}/secrets/{SECRET_TOKEN}",
                    "fix": "配一个 ${VAR} 引用，例如 ${DISCORD_BOT_TOKEN}。",
                },
            ) from exc
        raise


def _optional_secret(ctx: PluginContext, name: str) -> SecretStr | None:
    """取一个可选凭据。**没配不是错误**（`openai-api._optional_secret` 的同一条）。"""
    try:
        return ctx.secret(name)
    except NucleaError as exc:
        if exc.code is ErrorCode.CONFIG_SECRET_MISSING:
            return None
        raise
