"""`discord` 插件的配置读取与校验（`CFG-002`：插件只看得见自己那一块）。

职责：把 `ctx.config` 校验成一份不可变的 `DiscordSettings`，并派生 `normalize.InboundGate`。
全部校验在 `setup()` 时发生一次。
不负责：读凭据（那是 `ctx.secret()`，在 `__init__.py`）、接触平台、任何 IO。

三条：

- **默认值一字不改地沿用 legacy**，只换单位与命名（秒 → `*_ms`：新层配置里所有时长都是
  毫秒，留一个秒制字段会让它成为唯一的例外）。`allow_from` 为空 = **允许所有**，
  与 legacy 一致——改它等于静默改变谁能用这个 bot。
- **`operators` 是新增的**：legacy 没有这个概念（它的 `allow_from` 就是全部权限），而契约
  要求 `Sender.is_operator` 由 Channel 在边界决定。默认空 = 无人是 operator，因此
  `/config` 这类 `operator_only` 命令在 Discord 上默认不可用——那是安全的一侧。
- **坏配置让插件加载失败**（`PLUGIN_LOAD_FAILED`，`critical=False` 因此不连累实例），
  不拖到第一条消息（`D18` 的先例）。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from nucleamind.contracts import ErrorCode, InstanceId, JsonValue, NucleaError
from nucleamind.sdk import PluginContext

from .indicators import DEFAULT_TYPING_INTERVAL_MS, DEFAULT_WORKING_DELAY_MS
from .normalize import GROUP_POLICY_MENTION, GROUP_POLICY_OPEN, InboundGate
from .stream import DEFAULT_EDIT_INTERVAL_MS

__all__ = [
    "CAPABILITY_NAME",
    "CONFIG_KEYS",
    "DEFAULT_INTENTS",
    "GROUP_POLICIES",
    "SECRET_PROXY_PASSWORD",
    "SECRET_TOKEN",
    "DiscordSettings",
    "resolve_settings",
]

#: 本插件的能力名，同时是 `channel_id` 的默认值。
CAPABILITY_NAME: Final = "discord"

#: 凭据名固定不可配置，使配置路径与 `ctx.secret()` 调用保持同源。
SECRET_TOKEN: Final = "bot_token"
SECRET_PROXY_PASSWORD: Final = "proxy_password"

#: legacy `DiscordConfig.intents` 的原值。它是一个位掩码，含义归 Discord 管，本插件
#: 只负责原样转发——猜一个「更合理」的默认会让 bot 收不到消息且极难诊断。
DEFAULT_INTENTS: Final = 37377

GROUP_POLICIES: Final[frozenset[str]] = frozenset({GROUP_POLICY_MENTION, GROUP_POLICY_OPEN})

_DEFAULT_MAX_ATTACHMENT_BYTES: Final = 20 * 1024 * 1024

_NOT_A_LIST: Final = "该配置项必须是数组。"
_NOT_AN_ID: Final = "名单里的每一项都必须是 id 字符串。"
_EMPTY_ID: Final = "名单里不允许出现空 id。"
_BAD_POLICY: Final = "group_policy 的取值受限。"
_PROXY_INCOMPLETE: Final = "配置了 proxy_username 就必须同时配置 proxy。"

#: 全部配置键。与 manifest 的 `config_schema` 由一条对照测试钉住——两处都「自洽」而对不上
#: 时，一个写对了的配置会在阶段 A 被 schema 拒掉，而错误指向的是 schema 不是这里。
CONFIG_KEYS: Final[frozenset[str]] = frozenset(
    {
        "channel_id",
        "instance_id",
        "allow_from",
        "allow_channels",
        "operators",
        "group_policy",
        "intents",
        "streaming",
        "stream_edit_interval_ms",
        "read_receipt_emoji",
        "working_emoji",
        "working_emoji_delay_ms",
        "typing_interval_ms",
        "max_attachment_bytes",
        "proxy",
        "proxy_username",
    }
)


def _invalid(message: str, **detail: object) -> NucleaError:
    return NucleaError(ErrorCode.CONFIG_INVALID, message, detail=detail)


def _read_str(config: Mapping[str, JsonValue], key: str, *, default: str) -> str:
    value = config.get(key)
    if value is None:
        return default
    if not isinstance(value, str):
        raise _invalid("该配置项必须是字符串。", key=key, actual_type=type(value).__name__)
    return value


def _read_opt_str(config: Mapping[str, JsonValue], key: str) -> str | None:
    value = config.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise _invalid("该配置项必须是非空字符串。", key=key, actual_type=type(value).__name__)
    return value.strip()


def _read_bool(config: Mapping[str, JsonValue], key: str, *, default: bool) -> bool:
    value = config.get(key)
    if value is None:
        return default
    if not isinstance(value, bool):
        raise _invalid("该配置项必须是布尔值。", key=key, actual_type=type(value).__name__)
    return value


def _read_int(config: Mapping[str, JsonValue], key: str, *, default: int, minimum: int = 1) -> int:
    value = config.get(key)
    if value is None:
        return default
    # `bool` 是 `int` 的子类，但 `"intents": true` 是配置写错了。
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise _invalid(
            "该配置项必须是整数且不小于下限。",
            key=key,
            minimum=minimum,
            actual_type=type(value).__name__,
        )
    return value


def _read_ids(config: Mapping[str, JsonValue], key: str) -> frozenset[str]:
    """读一份 id 名单。**数字也接受并转成字符串**——Discord 的 id 在 JSON 里既可能被写成
    `"123"` 也可能被写成 `123`，为这个细节拒绝一份配置只会让人困惑。"""
    value = config.get(key)
    if value is None:
        return frozenset()
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        raise _invalid(_NOT_A_LIST, key=key, actual_type=type(value).__name__)
    items: set[str] = set()
    for item in value:
        if isinstance(item, bool) or not isinstance(item, str | int):
            raise _invalid(_NOT_AN_ID, key=key)
        text = str(item).strip()
        if not text:
            raise _invalid(_EMPTY_ID, key=key)
        items.add(text)
    return frozenset(items)


@dataclass(frozen=True, slots=True)
class DiscordSettings:
    """一份已校验的配置。构造后不可变，每条消息直接读它。"""

    instance_id: InstanceId
    channel_id: str
    allow_from: frozenset[str]
    allow_channels: frozenset[str]
    operators: frozenset[str]
    group_policy: str
    intents: int
    streaming: bool
    stream_edit_interval_ms: int
    read_receipt_emoji: str
    working_emoji: str
    working_emoji_delay_ms: int
    typing_interval_ms: int
    max_attachment_bytes: int
    proxy: str | None
    proxy_username: str | None

    def gate(self, *, bot_user_id: str = "") -> InboundGate:
        """派生归一化用的门控。`bot_user_id` 要等 `on_ready` 才知道，因此是参数。"""
        return InboundGate(
            instance_id=self.instance_id,
            channel_id=self.channel_id,
            bot_user_id=bot_user_id,
            allow_from=self.allow_from,
            allow_channels=self.allow_channels,
            operators=self.operators,
            group_policy=self.group_policy,
            max_attachment_bytes=self.max_attachment_bytes,
        )


def resolve_settings(ctx: PluginContext) -> DiscordSettings:
    """把 `ctx.config` 校验成一份设置。

    **异常约定**：类型或取值不对抛 `CONFIG_INVALID`。校验在 `setup()` 时发生一次。
    """
    config = ctx.config
    policy = _read_str(config, "group_policy", default=GROUP_POLICY_MENTION)
    if policy not in GROUP_POLICIES:
        raise _invalid(
            _BAD_POLICY,
            key="group_policy",
            allowed=sorted(GROUP_POLICIES),
            actual=policy,
        )
    proxy = _read_opt_str(config, "proxy")
    proxy_username = _read_opt_str(config, "proxy_username")
    if proxy_username is not None and proxy is None:
        # 配了代理用户名却没配代理地址：那个用户名永远不会被用到，而用户以为配好了。
        raise _invalid(_PROXY_INCOMPLETE, key="proxy")
    return DiscordSettings(
        instance_id=InstanceId(_read_str(config, "instance_id", default="default")),
        channel_id=_read_str(config, "channel_id", default=CAPABILITY_NAME),
        allow_from=_read_ids(config, "allow_from"),
        allow_channels=_read_ids(config, "allow_channels"),
        operators=_read_ids(config, "operators"),
        group_policy=policy,
        intents=_read_int(config, "intents", default=DEFAULT_INTENTS, minimum=0),
        streaming=_read_bool(config, "streaming", default=True),
        stream_edit_interval_ms=_read_int(
            config, "stream_edit_interval_ms", default=DEFAULT_EDIT_INTERVAL_MS, minimum=100
        ),
        read_receipt_emoji=_read_str(config, "read_receipt_emoji", default="👀"),
        working_emoji=_read_str(config, "working_emoji", default="🔧"),
        working_emoji_delay_ms=_read_int(
            config, "working_emoji_delay_ms", default=DEFAULT_WORKING_DELAY_MS, minimum=0
        ),
        typing_interval_ms=_read_int(
            config, "typing_interval_ms", default=DEFAULT_TYPING_INTERVAL_MS, minimum=1000
        ),
        max_attachment_bytes=_read_int(
            config, "max_attachment_bytes", default=_DEFAULT_MAX_ATTACHMENT_BYTES
        ),
        proxy=proxy,
        proxy_username=proxy_username,
    )
