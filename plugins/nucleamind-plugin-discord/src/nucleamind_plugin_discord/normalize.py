"""Discord 平台事件 → 契约 `InboundMessage` 的归一化（`MSG-004`，开发方案 `D33`）。

职责：判定一条平台消息该不该处理（自环 / 系统消息 / 白名单 / 频道白名单 / 群聊 @ 门控），
把该处理的那条拍成 `InboundMessage`；附件转成 `AttachmentRef` 与正文标记。
不负责：接触 `discord.py`（`gateway.py` 已经把 SDK 对象拍成了 `RawInbound`）、
下载附件、发反应或 typing（`indicators.py`）、任何 IO。

**判定顺序本身是行为，改它就是改「谁能用这个 bot」**：

    自环 → 系统消息 → allow_from → allow_channels → 群聊 @ 门控 → 归一化

顺序照搬 legacy `_should_accept_inbound` 那一串，唯一的差别是 legacy 在 DM 未授权时会走
配对码流程（`D33` 不迁，理由见包 docstring）：这里直接丢弃。

**只丢自己账号的消息，不丢其它 bot 的**（legacy `runtime.py:557` + 上游 issue #3217）。
多 bot 编排要靠这条成立：一个 bot @ 另一个 bot 求助是合法用法，而 bot 之间的循环仍然被
「每个 bot 都忽略自己」挡住。**这是本模块最容易被「顺手改成 `if author.bot: return`」
毁掉的一条**，因此它有一条用例名里写着 #3217。

**thread 天然是独立会话**：`conversation_id` 取 `channel.id`，而 Discord 的 thread 有自己的
id。因此不需要 legacy 那个自造的 `f"{name}:{parent}:thread:{id}"` session key——
`SessionKey(channel_id, conversation_id)` 已经把它表达完了，父频道只作为元数据留着。

**附件不下载**：契约层只存引用不存字节，而 Discord CDN 直接给 URL。这比 legacy 的
「下载到 media_dir」少一整套 `fs:write` 权限。
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Final

from nucleamind.contracts import (
    AttachmentRef,
    AttachmentSource,
    InboundMessage,
    InstanceId,
    JsonValue,
    Sender,
)

__all__ = [
    "EMPTY_CONTENT",
    "GROUP_POLICY_MENTION",
    "GROUP_POLICY_OPEN",
    "InboundGate",
    "RawAttachment",
    "RawAuthor",
    "RawInbound",
    "normalize",
]

#: 两种群聊门控。取值与配置字面量同名。
GROUP_POLICY_MENTION: Final = "mention"
GROUP_POLICY_OPEN: Final = "open"

#: 正文与附件都空时的地板值。契约要求「内容与 attachments 不能同时为空」，而 Discord 上
#: 一条只有 sticker 或只有嵌入的消息在这里确实两者皆空。
EMPTY_CONTENT: Final = "[empty message]"

#: 只有这两种消息带用户的 prompt。系统消息（加人、pin、thread 生命周期）一律丢弃。
_USER_MESSAGE_TYPES: Final[frozenset[str]] = frozenset({"default", "reply"})

#: 正文里的 mention 写法。`<@!id>` 是旧版昵称形式，Discord 仍会发。
_MENTION_PATTERNS: Final = ("<@{bot}>", "<@!{bot}>")

#: 附件太大时的正文标记。**不给 ref**：给了下游会去下载一个我们已经知道超限的东西。
_TOO_LARGE: Final = "[attachment: {name} - too large]"

#: 附件的正文标记。模型看不见 `AttachmentRef` 的结构，只看得见正文。
_ATTACHMENT_NOTE: Final = "[attachment: {name}]"

_INVALID_ID = re.compile(r"[^\w.-]")


@dataclass(frozen=True, slots=True)
class RawAuthor:
    """一条消息的作者，已经从 SDK 对象里拍平。"""

    id: str
    display_name: str = ""
    is_bot: bool = False


@dataclass(frozen=True, slots=True)
class RawAttachment:
    """一个附件，已经从 SDK 对象里拍平。`url` 是 Discord CDN 的直链。"""

    filename: str
    url: str
    size: int = 0
    content_type: str = ""


@dataclass(frozen=True, slots=True)
class RawInbound:
    """一条平台消息的归一化输入。**`gateway.py` 是它唯一的构造者。**

    它存在的理由是让 `normalize()` 与它的用例**不需要装 `discord.py`**：本模块只认识
    这个 dataclass，因此全部判定都能在没有平台连接的情况下逐条钉住。
    """

    message_id: str
    channel_id: str
    author: RawAuthor
    content: str
    timestamp: datetime
    message_type: str = "default"
    guild_id: str | None = None
    parent_channel_id: str | None = None
    reply_to: str | None = None
    #: 回复目标的作者 id；用于「回复了 bot 自己的消息」这条 @ 门控命中路径。
    reply_to_author_id: str | None = None
    mention_ids: tuple[str, ...] = ()
    attachments: tuple[RawAttachment, ...] = ()

    @property
    def is_direct_message(self) -> bool:
        """私聊。Discord 的 DM 没有 guild。"""
        return self.guild_id is None


@dataclass(frozen=True, slots=True)
class InboundGate:
    """归一化需要的全部配置。由 `settings.py` 构造，本模块不认识 `ctx.config`。"""

    instance_id: InstanceId
    channel_id: str
    bot_user_id: str = ""
    allow_from: frozenset[str] = frozenset()
    allow_channels: frozenset[str] = frozenset()
    operators: frozenset[str] = frozenset()
    group_policy: str = GROUP_POLICY_MENTION
    max_attachment_bytes: int = 20 * 1024 * 1024
    #: 被拒的原因会写进这里（同一个 gate 反复用时由调用方自己清），仅供诊断。
    rejections: list[str] = field(default_factory=list, compare=False)


def _is_self(raw: RawInbound, gate: InboundGate) -> bool:
    """自环判定。**只认自己的账号 id**——见模块 docstring 的 #3217。"""
    return bool(gate.bot_user_id) and raw.author.id == gate.bot_user_id


def _channel_keys(raw: RawInbound) -> frozenset[str]:
    """能满足 `allow_channels` 的 id 集合。

    thread 命中它的父频道也算：运维在配置里写的是「这个频道」，而 thread 是那个频道里
    长出来的东西，要求他把每条 thread 的 id 都列一遍是不可能的。
    """
    keys = {raw.channel_id}
    if raw.parent_channel_id:
        keys.add(raw.parent_channel_id)
    return frozenset(keys)


def _addressed_to_bot(raw: RawInbound, gate: InboundGate) -> bool:
    """群聊 @ 门控的四条命中路径，逐条对应 legacy `_should_respond_in_group`。

    第四条（回复的是 bot 自己发的消息）最容易漏：在 Discord 上「回复」是接着说话的常规
    方式，把它排除掉会让多轮对话在群里只能第一句用 @。
    """
    if gate.group_policy == GROUP_POLICY_OPEN:
        return True
    bot = gate.bot_user_id
    if not bot:
        # 身份还没拿到（`on_ready` 之前）：宁可不答也不要在群里乱说话。
        return False
    if bot in raw.mention_ids:
        return True
    if any(pattern.format(bot=bot) in raw.content for pattern in _MENTION_PATTERNS):
        return True
    return raw.reply_to_author_id == bot


def _attachments(
    raw: RawInbound, gate: InboundGate
) -> tuple[tuple[AttachmentRef, ...], list[str]]:
    """附件 → `(引用, 正文标记)`。超限的只留标记，不给引用。"""
    refs: list[AttachmentRef] = []
    notes: list[str] = []
    for item in raw.attachments:
        if gate.max_attachment_bytes and item.size > gate.max_attachment_bytes:
            notes.append(_TOO_LARGE.format(name=item.filename))
            continue
        refs.append(
            AttachmentRef(
                source=AttachmentSource.URL,
                locator=item.url,
                media_type=item.content_type or "application/octet-stream",
                filename=item.filename or None,
                size_bytes=item.size or None,
            )
        )
        notes.append(_ATTACHMENT_NOTE.format(name=item.filename))
    return tuple(refs), notes


def _metadata(raw: RawInbound) -> Mapping[str, JsonValue]:
    """平台私有字段只进 `metadata["discord"]`（`MSG-002`）。

    值必须可 JSON 化——`normalize_metadata()` 会当场拒绝别的东西，那正是「原始 SDK 对象
    不得进入 Kernel」在类型层的强制。
    """
    payload: dict[str, JsonValue] = {"channel_id": raw.channel_id}
    if raw.guild_id is not None:
        payload["guild_id"] = raw.guild_id
    if raw.parent_channel_id is not None:
        # thread 已经是独立会话，父频道只作为「它长在哪儿」的线索留着。
        payload["parent_channel_id"] = raw.parent_channel_id
        payload["is_thread"] = True
    if raw.author.display_name:
        payload["author_display_name"] = raw.author.display_name
    return {"discord": payload}


def _content(raw: RawInbound, notes: Sequence[str]) -> str:
    parts = [raw.content.strip()] if raw.content.strip() else []
    parts.extend(notes)
    return "\n".join(parts)


def normalize(raw: RawInbound, gate: InboundGate) -> InboundMessage | None:
    """一条平台消息 → `InboundMessage`，或 `None` 表示「不处理」。

    **返回 `None` 不是错误**：绝大多数被丢掉的消息是别人在群里正常聊天。原因记进
    `gate.rejections` 供诊断，不发事件——一个热闹的服务器每秒能产生几十条。
    """
    if _is_self(raw, gate):
        gate.rejections.append("self")
        return None
    if raw.message_type not in _USER_MESSAGE_TYPES:
        gate.rejections.append("system_message")
        return None
    if gate.allow_from and raw.author.id not in gate.allow_from:
        gate.rejections.append("sender_not_allowed")
        return None
    if gate.allow_channels and not (_channel_keys(raw) & gate.allow_channels):
        gate.rejections.append("channel_not_allowed")
        return None
    if not raw.is_direct_message and not _addressed_to_bot(raw, gate):
        gate.rejections.append("not_addressed")
        return None

    refs, notes = _attachments(raw, gate)
    content = _content(raw, notes)
    if not content and not refs:
        content = EMPTY_CONTENT
    return InboundMessage(
        message_id=_INVALID_ID.sub("_", raw.message_id),
        instance_id=gate.instance_id,
        channel_id=gate.channel_id,
        conversation_id=raw.channel_id,
        sender=Sender(
            user_id=raw.author.id,
            display_name=raw.author.display_name or None,
            # **`is_operator` 由 Channel 在边界决定，Kernel 不猜**（契约原话）：
            # `operator_only` 命令（`/config` 这类）的可达性全靠这一行。
            is_operator=raw.author.id in gate.operators,
            is_bot=raw.author.is_bot,
        ),
        content=content,
        timestamp=raw.timestamp,
        attachments=refs,
        reply_to=raw.reply_to,
        metadata=_metadata(raw),
    )
