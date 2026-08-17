"""契约 `OutboundMessage` → Discord 发送动作（`MSG-003`、`EDG-304`，开发方案 `D33`）。

职责：2000 字符分段、中断/失败标记、附件分流（正文成行 vs 真上传）、回复引用。
纯函数，零 IO——**读附件字节不在这里**（那要 `ctx.fs`，归 `channel.py`）。
不负责：真的发出去（`channel.py` / `gateway.py`）、流式的编辑时机（`stream.py`）。

**分段规则逐字节照搬 legacy `utils/helpers.split_message`**（换行 > 空格 > 硬切），
但这是**本插件自己的一份**：技术方案 §9.1 明确「允许 channel 之间重复实现发送重试、
消息分段、媒体处理，不为消除重复引入共享基类」，而 `R4` 也不允许插件 import `legacy/`
或 `builtins/`。

**`EDG-304` 的标记是文本，不是 emoji 或 embed 颜色。** 三条理由：文本能逐字节断言，
而契约测试要强制的正是这一条；用户复制粘贴时颜色会丢；`cli_entry` 已经用文本，两处
用同一句话意味着「被中断」在所有 Channel 上读起来一样。取值与
`builtins/cli_entry/console.py::TERMINAL_MARKERS` **逐字相同**——那是同一件事的两个
呈现端，不是巧合。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from nucleamind.contracts import (
    AttachmentRef,
    AttachmentSource,
    OutboundMessage,
    StreamState,
)

__all__ = [
    "MAX_MESSAGE_LENGTH",
    "TERMINAL_MARKERS",
    "SendPlan",
    "attachment_lines",
    "marker_for",
    "plan_outbound",
    "split_message",
    "unsendable_line",
]

#: Discord 单条消息的字符上限。超过就是 400，不是「会被截断」。
MAX_MESSAGE_LENGTH: Final = 2000

#: 非完整答案的标记（`EDG-304`）。与 `builtins/cli_entry/console.py` 的同名表逐字相同。
TERMINAL_MARKERS: Final[Mapping[StreamState, str]] = {
    StreamState.CANCELLED: "[已中断：以上是中断前已产生的内容]",
    StreamState.FAILED: "[本轮失败]",
}

#: 上传不了的附件如实说一句，不假装发过。`WORKSPACE` 走真上传（`D47`），因此这一行现在
#: 只留给 `INLINE` / `OPAQUE`（本插件拿不到它们的字节）与**读盘失败**那条退路。
_UNSENDABLE: Final = "[附件：{name}（本轮无法上传）]"


def split_message(content: str, max_len: int = MAX_MESSAGE_LENGTH) -> list[str]:
    """按平台上限切块，优先在换行处切、其次空格、最后硬切。

    空串返回空列表（**不是 `[""]`**）：一条空消息发过去是 400，而调用方要的是「没什么
    可发的」。`max_len <= 0` 时原样返回一块——那是调用方配错了，切不动的循环比一条超长
    消息更糟。
    """
    if not content:
        return []
    if max_len <= 0 or len(content) <= max_len:
        return [content]
    chunks: list[str] = []
    remaining = content
    while remaining:
        if len(remaining) <= max_len:
            chunks.append(remaining)
            break
        head = remaining[:max_len]
        cut = head.rfind("\n")
        if cut <= 0:
            cut = head.rfind(" ")
        if cut <= 0:
            cut = max_len
        chunks.append(remaining[:cut])
        remaining = remaining[cut:].lstrip()
    return chunks


def marker_for(state: StreamState) -> str:
    """该终态要附加的标记；完整答案返回空串。"""
    return TERMINAL_MARKERS.get(state, "")


def attachment_lines(attachments: Sequence[AttachmentRef]) -> list[str]:
    """附件的**正文**呈现。

    `URL` 直接成行——Discord 会自己 embed。`WORKSPACE` 不在这里：`D47` 起它走真上传
    （`uploads`），成行只会让频道里多出一条读不懂的相对路径。其余来源
    （`INLINE` / `OPAQUE`）本插件拿不到字节，如实说一句。
    """
    lines: list[str] = []
    for item in attachments:
        if item.source is AttachmentSource.URL:
            lines.append(item.locator)
            continue
        if item.source is AttachmentSource.WORKSPACE:
            continue
        lines.append(unsendable_line(item))
    return lines


def unsendable_line(attachment: AttachmentRef) -> str:
    """「这个附件没发出去」那一行。读盘失败时 `channel.py` 也用它。"""
    return _UNSENDABLE.format(name=attachment.filename or attachment.locator)


@dataclass(frozen=True, slots=True)
class SendPlan:
    """一条出站消息要发的东西。`chunks` 与 `uploads` 都空表示什么都不用发。"""

    chunks: tuple[str, ...] = ()
    #: 要真的上传字节的附件（`WORKSPACE` 来源，`D47`）。**计划阶段不读盘**——本模块零 IO，
    #: 读字节归 `channel.py`（它才有 `ctx.fs`）。
    uploads: tuple[AttachmentRef, ...] = ()
    #: 只有第一块带回复引用——每一块都引用会在频道里刷出一串重复的引用条。
    reply_to: str | None = None

    @property
    def empty(self) -> bool:
        return not self.chunks and not self.uploads


def plan_outbound(message: OutboundMessage, *, max_len: int = MAX_MESSAGE_LENGTH) -> SendPlan:
    """把一条出站消息拍成待发的块 + 待上传的附件。

    **标记追加在正文之后再分段**，不是发第二条消息：被中断的半截答案与「它被中断了」
    必须在同一条消息里，否则前者孤零零留在上面看着像完整回答（`EDG-304` 要防的正是这个）。
    正文为空时只发标记那一行。
    """
    parts = [message.content] if message.content else []
    parts.extend(attachment_lines(message.attachments))
    marker = marker_for(message.stream_state)
    if marker:
        parts.append(marker)
    body = "\n\n".join(part for part in parts if part)
    return SendPlan(
        chunks=tuple(split_message(body, max_len)),
        uploads=tuple(
            item for item in message.attachments if item.source is AttachmentSource.WORKSPACE
        ),
        reply_to=message.reply_to,
    )
