"""官方插件 `feishu`：把实例接到一个飞书 / Lark 机器人上（开发方案 `D34`）。

职责：声明一条 `CHANNEL` 能力，把飞书的消息翻成 `InboundMessage`、把 `OutboundMessage`
翻成文本 / 富文本 / 卡片与 CardKit 流式更新。
不负责：执行 turn、管理会话历史、路由命令（分别是 `kernel/turn/`、会话存储能力与
`kernel/routing/dispatcher.py` 的事）。

**它取代的是被 `D34` 删掉的 `legacy/channels/feishu/`**，但不是移植。四样没搬：

- **扫码自动建应用的设备码流程**（约 670 行）。它服务的是 WebUI 的扫码连接面板，
  `D31` 已删后端；而且它打的是**未公开端点**（`accounts.feishu.cn/oauth/v1/app/registration`），
  飞书改一次就碎。改成：在开放平台自己建应用，把 `app_id` / `app_secret` 填进配置。
- **多实例**。旧实现能在一份配置里声明 N 个飞书实例并动态注册 N 条 Channel；
  **新的能力模型表达不了这件事**——manifest 的 `capabilities` 是静态声明且双向约束
  （声明了没注册、注册了没声明都是 `PLUGIN_LOAD_FAILED`，`D16`），而 `D20` 的 `keep`
  只能按配置**少**注册几条、不能多注册。要跑多个飞书应用就开多个 nm 实例。
- **`ChannelSetupSpec` / `webui/` 三个 tsx + 10 份 locale**：legacy WebUI 的契约，
  服务端不存在。新层的同位物是 manifest 的 `config_schema` + `setup()` 里一次性校验。
- **`encrypt_key` / `verification_token`**：WS 长连接下 SDK 走 `do_without_validation`，
  **没有 AES 解密也没有签名校验**（那是 webhook 模式才有的），legacy 传的恒是可空值、
  从来没被用过。保留一个永远不生效的安全配置项比没有它更糟。

**三条如实记着的边界**，写在这里而不是留给用户发现：

- **五种权限里没有「连接一个聊天平台」这一种**（`fs:read` / `fs:write` / `net` / `shell` /
  `secret`，其中 `net` 判的是经 `ctx.net` 门面的出站请求）。`lark-oapi` 自己开 WebSocket
  与 HTTPS，一个字节都不过门面，因此本插件除两条 `secret` 外声明不出任何权限，
  而它确实会连出去。这是权限模型当前的一个空档，与 `openai-api` 的「没有『监听端口』」
  和 `discord` 的同一条并列。
- **出站 workspace 附件传不出去**：`sdk.api.FileAccess` 只有 `read_text` / `write_text` /
  `list_dir`，没有 `read_bytes`；绕过 `ctx.fs` 直接 `open()` 会让权限声明变成谎话。
  今天新层也没有任何地方产出带附件的 `OutboundMessage`，因此这是一条没有生产者的死路径。
- **应用级权限不是进程隔离**（`sdk/api.py` 的原话）。能在允许的会话里说话的人就能驱动
  实例上的全部工具，包括 `shell.exec`。`allow_from` 与 `allow_chats` 是唯一的闸门。
"""

from __future__ import annotations

from typing import Final

from nucleamind.contracts import (
    CapabilityKind,
    ErrorCode,
    EventName,
    NucleaError,
    PermissionKind,
    SecretStr,
)
from nucleamind.sdk import (
    CapabilityDecl,
    ManifestJsonSchema,
    NucleaAPI,
    PermissionDecl,
    PluginContext,
    PluginManifest,
)

from .cards import build_elements, split_by_table_limit
from .channel import FeishuChannel
from .client import FeishuClient
from .content import extract_interactive, extract_post, extract_share_card
from .gateway import MISSING_SDK_FIX, FeishuGateway, event_to_raw
from .indicators import Indicators
from .mentions import Mention, is_addressed_to_bot, resolve_mentions, strip_leading_bot_mention
from .normalize import (
    InboundGate,
    RawInbound,
    decode_conversation,
    encode_conversation,
    normalize,
)
from .outbound import (
    POST_MAX_LEN,
    TERMINAL_MARKERS,
    TEXT_MAX_LEN,
    detect_format,
    markdown_to_post,
)
from .settings import (
    CAPABILITY_NAME,
    CONFIG_KEYS,
    SECRET_APP_ID,
    SECRET_APP_SECRET,
    FeishuSettings,
    resolve_settings,
)
from .stream import StreamRelay

__all__ = [
    "CAPABILITY_NAME",
    "CONFIG_KEYS",
    "CONFIG_SCHEMA",
    "MANIFEST",
    "MISSING_SDK_FIX",
    "POST_MAX_LEN",
    "SECRET_APP_ID",
    "SECRET_APP_SECRET",
    "TERMINAL_MARKERS",
    "TEXT_MAX_LEN",
    "FeishuChannel",
    "FeishuClient",
    "FeishuGateway",
    "FeishuSettings",
    "InboundGate",
    "Indicators",
    "Mention",
    "RawInbound",
    "StreamRelay",
    "build_elements",
    "decode_conversation",
    "detect_format",
    "encode_conversation",
    "event_to_raw",
    "extract_interactive",
    "extract_post",
    "extract_share_card",
    "is_addressed_to_bot",
    "markdown_to_post",
    "normalize",
    "resolve_mentions",
    "resolve_settings",
    "setup",
    "split_by_table_limit",
    "strip_leading_bot_mention",
]

#: 插件配置块的 JSON Schema。阶段 A 在**加载之前**按它校验形状，`settings.py` 在 `setup()`
#: 里再校验语义（枚举、区间）。两处由一条 `set(properties) == CONFIG_KEYS` 用例钉住。
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
        "domain": {"type": "string", "enum": ["feishu", "lark"]},
        "allow_from": {"type": "array", "items": {"type": "string"}},
        "allow_chats": {"type": "array", "items": {"type": "string"}},
        "operators": {"type": "array", "items": {"type": "string"}},
        "group_policy": {"type": "string", "enum": ["mention", "open"]},
        "topic_isolation": {"type": "boolean"},
        "reply_to_message": {"type": "boolean"},
        "streaming": {"type": "boolean"},
        "stream_edit_interval_ms": {"type": "integer", "minimum": 100},
        "react_emoji": {"type": "string"},
        "done_emoji": {"type": "string"},
        "tool_hint_prefix": {"type": "string"},
    },
    "additionalProperties": False,
}

MANIFEST: Final = PluginManifest(
    id="feishu",
    version="0.1.0",
    sdk_range=">=0.1.0,<0.2.0",
    setup="nucleamind_plugin_feishu:setup",
    # **不写 `overrides`**（它不取代任何内建）、**不写 `priority`**（默认值 100 会被原样
    # 采纳，而内建基准是 0——`D16` 记的坑）。
    capabilities=(CapabilityDecl(kind=CapabilityKind.CHANNEL, name=CAPABILITY_NAME),),
    # **两条 secret，没有 `net`**：见模块 docstring 的第一条边界。
    # **`app_id` 也走 secrets**：`ctx.config` 不解析 `${VAR}`，放 config 会让写
    # `${FEISHU_APP_ID}` 的人拿到字面串并在连接时得到一个无法诊断的 401。凭据是一对。
    permissions=(
        PermissionDecl(
            kind=PermissionKind.SECRET,
            target=SECRET_APP_ID,
            reason="飞书应用的 App ID，与 App Secret 成对换取 tenant_access_token。",
        ),
        PermissionDecl(
            kind=PermissionKind.SECRET,
            target=SECRET_APP_SECRET,
            reason="飞书应用的 App Secret。",
        ),
    ),
    config_schema=CONFIG_SCHEMA,
    # `critical=False`：飞书连不上（应用被停用、网络不通）不该让 CLI 与其它 Channel
    # 一起下线。`PLG-004`：失败的后果由装配根决定。
    critical=False,
)

_MISSING_CREDENTIALS: Final = "飞书 Channel 必须同时配置 app_id 与 app_secret。"


def setup(api: NucleaAPI) -> None:
    """注册 Channel。配置与凭据在这里各解析一次，不拖到第一条消息（`D18` 的先例）。

    **顺带订阅 `tool.call_started`**：工具提示的唯一数据源（`channel.py` 的 docstring 说明
    了为什么不能从出站流里拿）。订阅不需要权限声明——事件流是只读可观测性，与 `ctx.events`
    同一档；它的生命周期就是插件的生命周期，由 Kernel 在禁用时统一取消（`EDG-105`）。
    """
    settings = resolve_settings(api.ctx)
    channel = FeishuChannel(
        settings,
        app_id=_required_secret(api.ctx, SECRET_APP_ID),
        app_secret=_required_secret(api.ctx, SECRET_APP_SECRET),
    )
    if settings.tool_hint_prefix:
        api.ctx.events.subscribe(EventName.TOOL_CALL_STARTED, channel.on_tool_call)
    api.register_channel(CAPABILITY_NAME, channel)


def _required_secret(ctx: PluginContext, name: str) -> SecretStr:
    """取一条必填凭据。**没配就是配置错误**——一个没有凭据的飞书 Channel 连不上任何东西，
    让它「起来了但什么都不做」比直接说清楚更糟。

    未授权的 `PERMISSION_DENIED` 原样抛出：那与「没配」是两件事，补救动作也不同。
    """
    try:
        return ctx.secret(name)
    except NucleaError as exc:
        if exc.code is ErrorCode.CONFIG_SECRET_MISSING:
            raise NucleaError(
                ErrorCode.CONFIG_INVALID,
                _MISSING_CREDENTIALS,
                detail={
                    "pointer": f"/plugins/{MANIFEST.id}/secrets/{name}",
                    "fix": "配一个 ${VAR} 引用，例如 ${FEISHU_APP_ID} / ${FEISHU_APP_SECRET}。",
                },
            ) from exc
        raise
