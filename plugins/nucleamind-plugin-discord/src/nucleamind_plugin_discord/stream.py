"""流式 edit-in-place 的状态机（`MSG-005`、`EDG-304`，开发方案 `D33`）。

职责：把一串 `STARTED` / `DELTA` / 终态出站消息变成「发一条、然后按节流反复编辑它、
最后收束」的平台动作序列。
不负责：分段规则（`outbound.py`）、真的调用平台（`Platform` 由调用方注入）、
判断什么是终态（`OutboundMessage.stream_state` 已经说了）。

**注入时钟**（`now_ms`）：节流是本模块唯一的时间语义，而用真实时间测它意味着用例要
`sleep(0.8)`，慢机器上还会假阳性。注入之后节流是确定的——`indicators.py` 同理。

八条判定，每条对应一个用例：

1. **`STARTED` 不上线**：Discord 上不会因此出现一条空消息。
2. **首片必须 `strip()` 非空才上线**：模型的第一个 delta 常常是空白。
3. **节流跳过的文本不丢**：它留在缓冲里，下一次编辑或终态收束会带上。
4. **终态优先用 `message.content`**（非空时）而不是累积文本：终态消息带的是同一段完整
   正文（`cli_entry/console.py` 的同一条），用它可以避免 delta 丢片造成的漂移。
5. **超长收束是「编辑首块 + 补发其余」**，不能只编辑——2000 之外的内容会静默消失。
6. **`turn_id` 换了就换缓冲**，旧消息原样留在频道里不追加标记：那条 turn 自己的终态
   消息会带 `EDG-304` 标记，在这里再补一条会说两遍。
7. **`deliver()` 可能被并发调用**（`D33` 的泵扇出之后）。缓冲表按 `conversation_id`
   分片，而同一 conversation 内由 lane 与 `SessionScheduler` 双重串行——因此各条 lane
   只碰自己那个键，**不需要加锁**。这条依赖 `kernel/routing/fanout.py` 的不变量。
8. **附件在正文之后上传**（`D47`）：先看到答案再看到图；读不出来的附件如实印一行而不是
   静默丢掉，且**不抛**——`deliver()` 照约定抛的只有正文发不出去那一种。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import Protocol

from nucleamind.contracts import (
    AttachmentRef,
    AttachmentSource,
    OutboundMessage,
    StreamState,
)

from .outbound import (
    MAX_MESSAGE_LENGTH,
    attachment_lines,
    marker_for,
    split_message,
    unsendable_line,
)

__all__ = [
    "DEFAULT_EDIT_INTERVAL_MS",
    "AttachmentReader",
    "FileReader",
    "Platform",
    "SentMessage",
    "StreamRelay",
]

#: 两次编辑之间的最小间隔。legacy 的 `_STREAM_EDIT_INTERVAL = 0.8` 原值，只换了单位。
DEFAULT_EDIT_INTERVAL_MS: int = 800


class SentMessage(Protocol):
    """一条已经发出去的平台消息，还能被编辑。"""

    async def edit(self, content: str) -> None: ...


class Platform(Protocol):
    """本模块需要的全部平台能力。

    做成 Protocol 而不是直接吃 `discord.py` 的类型，是为了让整套用例不必装那个 SDK——
    `gateway.py` 是唯一接触它的模块。
    """

    async def send(self, conversation_id: str, content: str, *, reply_to: str | None) -> SentMessage:
        ...

    async def send_files(
        self, conversation_id: str, files: Sequence[tuple[str, bytes]], *, reply_to: str | None
    ) -> None:
        """上传若干附件（`D47`）。`files` 是 `(文件名, 字节)`。

        **不返回 `SentMessage`**：附件消息不需要被编辑（流式编辑只作用于正文），
        交出一个能编辑的句柄只会让调用方以为它该被编辑。
        """
        ...


#: 读一个附件的字节；`None` 表示读不出来（`channel.py` 把异常折成它）。
AttachmentReader = Callable[[AttachmentRef], Awaitable[bytes | None]]


class FileReader(Protocol):
    """`ctx.fs` 里本插件用得到的那一个方法。

    **不直接标注 `sdk.FileAccess`**：用例要一个可注入的替身，而
    `FakePluginContext.fs` 按设计抛 `NotImplementedError`（`sdk.testing` 是冻结表面，
    为一个插件的方便去改它的语义不划算）。窄到只有一个方法，替身因此是三行。
    """

    async def read_bytes(self, path: str) -> bytes: ...


@dataclass(slots=True)
class _Buffer:
    """一个 conversation 的流式缓冲。"""

    turn_id: str
    text: str = ""
    wire: SentMessage | None = None
    last_edit_ms: int = 0


@dataclass(slots=True)
class StreamRelay:
    """把出站流翻成平台动作。每 conversation 一个缓冲。"""

    platform: Platform
    now_ms: Callable[[], int]
    #: 读一个附件的字节。`None` 表示本 Channel 拿不到（没有 `fs:read`、或读失败），
    #: 那时如实印一行而不是静默丢掉。默认恒 `None`：注入才有上传能力。
    read_attachment: AttachmentReader | None = None
    edit_interval_ms: int = DEFAULT_EDIT_INTERVAL_MS
    streaming: bool = True
    max_len: int = MAX_MESSAGE_LENGTH
    _buffers: dict[str, _Buffer] = field(default_factory=dict)

    def active(self) -> int:
        """当前有缓冲的 conversation 数。诊断用，也是「没有泄漏」的可断言量。"""
        return len(self._buffers)

    async def handle(self, message: OutboundMessage) -> None:
        """处理一条出站消息。**约定不抛**由调用方（`channel.py`）负责。"""
        if message.stream_state is StreamState.STARTED:
            # 只登记，不发任何东西——空消息在 Discord 上是 400，在用户眼里是噪声。
            self._buffers[message.conversation_id] = _Buffer(turn_id=str(message.turn_id))
            return
        if message.stream_state is StreamState.DELTA:
            await self._absorb(message)
            return
        await self._finish(message)

    # ------------------------------------------------------------------ 内部

    def _buffer_for(self, message: OutboundMessage) -> _Buffer:
        """取（或换）这个 conversation 的缓冲。

        `turn_id` 不同即换一个：上一条 turn 的 wire 消息原样留在频道里——它自己的终态
        消息已经带过 `EDG-304` 标记了，在这里再补一条等于把同一件事说两遍。
        """
        buffer = self._buffers.get(message.conversation_id)
        if buffer is None or buffer.turn_id != str(message.turn_id):
            buffer = _Buffer(turn_id=str(message.turn_id))
            self._buffers[message.conversation_id] = buffer
        return buffer

    async def _absorb(self, message: OutboundMessage) -> None:
        buffer = self._buffer_for(message)
        buffer.text += message.content
        if not self.streaming:
            # 关掉流式就只累积，终态时一次发完（`MSG-005` 的降级）。
            return
        if buffer.wire is None:
            if not buffer.text.strip():
                # 首片全是空白：现在上线会发出一条看起来坏掉的空消息。
                return
            buffer.wire = await self.platform.send(
                message.conversation_id, self._head(buffer.text), reply_to=message.reply_to
            )
            buffer.last_edit_ms = self.now_ms()
            return
        now = self.now_ms()
        if now - buffer.last_edit_ms < self.edit_interval_ms:
            # 被节流跳过的文本**不丢**：它留在 buffer.text 里，下次编辑或收束带上。
            return
        await buffer.wire.edit(self._head(buffer.text))
        buffer.last_edit_ms = now

    async def _finish(self, message: OutboundMessage) -> None:
        buffer = self._buffers.pop(message.conversation_id, None)
        # 终态消息带的是完整正文；只有它为空时才回退到累积的 delta。
        body = message.content or (buffer.text if buffer else "")
        # `URL` 附件成行让 Discord 自己 embed；拿不到字节的来源如实说一句。
        # `WORKSPACE` 不在这里——它走下面的真上传（`D47`）。
        extra = attachment_lines(message.attachments)
        if extra:
            body = "\n\n".join([part for part in (body, *extra) if part])
        marker = marker_for(message.stream_state)
        if marker:
            body = f"{body}\n\n{marker}" if body else marker
        chunks = split_message(body, self.max_len)
        wire = buffer.wire if buffer else None
        if wire is None:
            await self._send_all(message, chunks)
        elif chunks:
            await wire.edit(chunks[0])
            await self._send_all(message, chunks[1:])
        # else: 流式已经上线但终态什么都没有——把已经显示的内容留着，不要编成空消息。
        await self._upload(message)

    async def _upload(self, message: OutboundMessage) -> None:
        """把 `WORKSPACE` 附件真的传上去（`D47`）。

        **在正文之后**：先看到答案再看到图，和人说话的顺序一致；而且正文那条消息才是
        流式编辑的落点，附件插在中间会让编辑目标不再是最后一条。

        **读不出来就印一行，不抛**（`EDG-204`）：一个读不到的附件不该把一次成功的投递
        变成失败。`deliver()` 照约定抛的只有**正文**发不出去那一种，见 `channel.py`。
        """
        pending = [
            item for item in message.attachments if item.source is AttachmentSource.WORKSPACE
        ]
        if not pending:
            return
        files: list[tuple[str, bytes]] = []
        missing: list[str] = []
        for item in pending:
            data = None if self.read_attachment is None else await self.read_attachment(item)
            if data is None:
                missing.append(unsendable_line(item))
                continue
            files.append((item.filename or item.locator.rsplit("/", 1)[-1], data))
        if files:
            await self.platform.send_files(message.conversation_id, files, reply_to=None)
        for line in missing:
            await self.platform.send(message.conversation_id, line, reply_to=None)

    async def _send_all(self, message: OutboundMessage, chunks: Sequence[str]) -> None:
        for index, chunk in enumerate(chunks):
            await self.platform.send(
                message.conversation_id,
                chunk,
                # 只有第一块带引用：每块都引用会刷出一串重复的引用条。
                reply_to=message.reply_to if index == 0 else None,
            )

    def _head(self, text: str) -> str:
        """流式期间只显示第一块。

        超出上限的部分留到收束时补发——**流式期间不补发**：那会让用户看着一条消息在
        增长的同时下面又冒出新的一条，而且每次编辑都要重算切点。
        """
        chunks = split_message(text, self.max_len)
        return chunks[0] if chunks else ""
