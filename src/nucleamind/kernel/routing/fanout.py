"""Channel 入站的按 conversation 扇出（需求 `EDG-202`、`KER-008`）。

职责：把一条 Channel 的入站消息流按 `conversation_id` 分成互不相干的 lane，同一 lane 内
严格按到达顺序串行、跨 lane 并发；lane 空即回收；队列或并发上界满时明确拒绝。
不负责：执行 turn（`handle` 由调用方给）、去重与并发策略（`dedup.py` / `session_lock.py`
在 `handle` 里面）、发布事件（`R2` 禁止 kernel import bus，失败与丢弃走注入的回调）。

**为什么不是「每条消息 `create_task`」。** 那样两条同会话消息进入 `SessionScheduler` 的
顺序不再确定。表面上 CPython 的 ready 队列是 FIFO、`submit()` 在第一个 `await` 之前就把
票据同步入队，因此**在 CPython 上**确实能保住 FIFO——但这正是 `session_lock.py` 明文拒绝
依赖的那类事实（「`Lock` 的唤醒顺序是 CPython 的实现细节而不是文档保证，而 `EDG-202` 要
断言的恰好是严格 FIFO」）。在泵这一层反过来依赖它，就是把刚拆掉的东西又装回去。
**有界队列 + 一个 worker** 是同一份设计的延伸：显式、可读、可断言。

**为什么按 conversation 分而不是按别的。** `InboundMessage.session_key(scope)` 的 `scope`
是实例级常量，一条 Channel 上 `channel_id` 也是常量，因此在一条 Channel 内
`conversation_id ↔ SessionKey` 是**双射**——「每 conversation 一个 worker」与「每 session
一个 worker」是同一句话，`EDG-202` 的严格 FIFO 因此逐字成立。

**`MERGE` 策略在这条路上仍然不可达**，而且这是**今天已有的行为**不是本模块引入的回退：
lane 串行意味着同 session 的第二条消息要等第一条跑完才提交，`SessionSlot.pending` 永远只有
一条。合并只在「多个并发提交方投到同一 session」时可达（`embed.submit()`、HTTP handler）。
**不要**让 lane 一次排空队列再整批提交——那是在第二处重写一遍 `_take_batch`。

**两处上界不会串联成 `min()` 陷阱**（`D28` 踩过同类）：因为 lane 串行，同一 session 在
`SessionScheduler` 里同一时刻至多有 1 个来自本模块的等待者，`queue_max_size` 对 Channel
流量永远达不到。lane 队列是 Channel 流量**唯一生效**的界。
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Final

from nucleamind.contracts import ErrorCode, InboundMessage, NucleaError

__all__ = [
    "DEFAULT_CHANNEL_CONCURRENCY",
    "DEFAULT_CHANNEL_QUEUE_MAX_SIZE",
    "ConversationFanout",
]

#: 一条 Channel 上同时活跃的 conversation 上限。它是**饱和护栏**而不是调优旋钮——撞上它
#: 意味着出事了（平台在灌消息、或每条 turn 都卡住），因此没有「不限」哨兵。
DEFAULT_CHANNEL_CONCURRENCY: Final = 64

#: 单个 conversation 的等待上限。取值与 `session_lock.DEFAULT_QUEUE_MAX_SIZE` **相同**，
#: 因为它接替（而不是叠加）那个界成为 Channel 流量的唯一上限——用户可见的积压容量因此
#: 与串行泵时代一个字没变。
DEFAULT_CHANNEL_QUEUE_MAX_SIZE: Final = 32

#: 一条消息的处理体。它不返回任何东西：投递回音与事件都由调用方在里面做完。
Handler = Callable[[InboundMessage], Awaitable[None]]

#: 处理体逸出异常时的回调。**不接受它抛**——它是最后一道记账。
FailureHook = Callable[[Exception], None]

#: 消息在进入 lane 之前就被拒时的回调（队列满 / 并发上界满）。
DropHook = Callable[[InboundMessage, NucleaError], Awaitable[None]]

_LANE_QUEUE_FULL: Final = "该会话的等待队列已满，请稍后重试。"
_CHANNEL_SATURATED: Final = "这条 Channel 上同时活跃的会话已达上限，请稍后重试。"


class _Lane:
    """一个 conversation 的队列与它的 worker。"""

    __slots__ = ("queue", "worker")

    def __init__(self, maxsize: int) -> None:
        self.queue: asyncio.Queue[InboundMessage] = asyncio.Queue(maxsize=maxsize)
        self.worker: asyncio.Task[None] | None = None


class ConversationFanout:
    """一条 Channel 的入站扇出。

    非线程安全，只在事件循环内使用——`_offer` 的判定、建 lane 与入队之间没有 `await`，
    这是「不加锁也不会漏判」的前提，与 `SessionScheduler.submit` 同一条。
    """

    __slots__ = ("_concurrency", "_handle", "_lanes", "_on_dropped", "_on_failure", "_queue_max_size")

    def __init__(
        self,
        handle: Handler,
        *,
        on_failure: FailureHook,
        on_dropped: DropHook,
        concurrency: int = DEFAULT_CHANNEL_CONCURRENCY,
        queue_max_size: int = DEFAULT_CHANNEL_QUEUE_MAX_SIZE,
    ) -> None:
        """**异常约定**：两个上界非正抛 `KERNEL_INVARIANT_VIOLATED`——0 会让扇出静默退化
        成「一条也不收」，而那与串行泵不是同一件事，更不是任何人想要的。"""
        for name, value in (("concurrency", concurrency), ("queue_max_size", queue_max_size)):
            if value <= 0:
                raise NucleaError(
                    ErrorCode.KERNEL_INVARIANT_VIOLATED,
                    "扇出的上界必须为正。",
                    detail={name: value},
                )
        self._handle = handle
        self._on_failure = on_failure
        self._on_dropped = on_dropped
        self._concurrency = concurrency
        self._queue_max_size = queue_max_size
        self._lanes: dict[str, _Lane] = {}

    def lanes(self) -> int:
        """此刻有活儿的 conversation 数。诊断用，也是「没有泄漏」的可断言量。"""
        return len(self._lanes)

    def waiting(self, conversation_id: str) -> int:
        """某个 conversation 的排队数（不含正在跑的那一条）。"""
        lane = self._lanes.get(conversation_id)
        return lane.queue.qsize() if lane is not None else 0

    def discard_pending(self) -> int:
        """丢弃所有尚未开始的消息，保留正在执行的 worker 让它正常收口。"""
        discarded = 0
        for lane in self._lanes.values():
            while True:
                try:
                    lane.queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                discarded += 1
        return discarded

    def force_cancel(self) -> None:
        """取消并摘除全部 worker，但不等待不合作的任务。仅供停机宽限耗尽后使用。"""
        workers = [lane.worker for lane in self._lanes.values() if lane.worker is not None]
        self._lanes.clear()
        for worker in workers:
            worker.cancel()
            worker.add_done_callback(_consume_task_result)

    async def run(self, messages: AsyncIterator[InboundMessage]) -> None:
        """泵的正文：把入站流分派进 lane。`messages` 结束即返回。

        **它自己几乎不 await**——只在取下一条消息与拒绝回音时。真正的工作在 worker 里，
        因此一条慢 turn 不会挡住后面的消息进入别的 lane。
        """
        async for message in messages:
            rejection = self._offer(message)
            if rejection is not None:
                await self._on_dropped(message, rejection)

    async def drain(self, *, cancel: bool) -> None:
        """停止时排干。

        `cancel=True` 时取消在途 worker；调用方需要明确丢弃排队消息时先调用
        `discard_pending()`。强制取消路径仍与串行泵时代的
        `pump.cancel()` 语义逐字相同**，只是从 1 个协程变成 N 个。刻意不做「优雅排干 +
        新超时」：`D28` 的教训是两处各判一次会让「等了多久」取决于两个数的最小值，
        而插件停止已经有 `plugins.stop_timeout_ms`。
        """
        workers = [lane.worker for lane in self._lanes.values() if lane.worker is not None]
        if cancel:
            for worker in workers:
                worker.cancel()
        self._lanes.clear()
        if workers:
            await asyncio.gather(*workers, return_exceptions=True)

    # ------------------------------------------------------------------ 内部

    def _offer(self, message: InboundMessage) -> NucleaError | None:
        """把一条消息放进它的 lane。返回 `None` 表示接住了。

        **全程同步**：查 lane → 不存在则（未达并发上界时）建 lane 并派 worker →
        `put_nowait`。中间没有 `await`，因此不存在「两条消息各建一个 lane」的交错。
        """
        lane = self._lanes.get(message.conversation_id)
        if lane is None:
            if len(self._lanes) >= self._concurrency:
                return NucleaError(
                    ErrorCode.INPUT_SESSION_BUSY,
                    _CHANNEL_SATURATED,
                    detail={"reason": "channel_saturated", "limit": self._concurrency},
                )
            lane = _Lane(self._queue_max_size)
            self._lanes[message.conversation_id] = lane
            lane.worker = asyncio.create_task(
                self._drive(message.conversation_id, lane),
                name=f"lane:{message.conversation_id}",
            )
        try:
            lane.queue.put_nowait(message)
        except asyncio.QueueFull:
            # 拒绝**最新**的那条而不是挤掉最老的：与 `SessionScheduler._rejection_for`
            # 一致，也因为丢掉一条已经排上队的消息等于静默吃掉用户的输入。
            return NucleaError(
                ErrorCode.INPUT_SESSION_BUSY,
                _LANE_QUEUE_FULL,
                detail={"reason": "lane_queue_full", "limit": self._queue_max_size},
            )
        return None

    async def _drive(self, conversation_id: str, lane: _Lane) -> None:
        """一个 lane 的 worker：取一条、跑完、再取下一条。

        **退出与摘表在同一个同步块里**：`get_nowait()` 抛 `QueueEmpty` 到 `pop` 之间没有
        `await`，因此不可能与 `_offer` 的 get-or-create 交错出「往一个已经退出的 lane 里
        投消息」。**队列空即退出，没有 idle TTL**——项目对「`dict[key, state]` 随历史会话
        无界增长」已经有一个答案（`SessionScheduler._discard_if_idle`），再发明一个
        「空闲 N 秒回收」就是第二套机制加第二个要调的数。代价是突发之后重建一个 task
        （微秒级），换来的是没有后台计时器、没有泄漏。
        """
        while True:
            try:
                message = lane.queue.get_nowait()
            except asyncio.QueueEmpty:
                # 只有在这个 lane 仍然是表里那一个时才摘——`drain()` 可能已经清过表。
                if self._lanes.get(conversation_id) is lane:
                    del self._lanes[conversation_id]
                return
            try:
                await self._handle(message)
            except Exception as exc:  # noqa: BLE001 - 一条消息炸掉不带走 lane，更不带走泵
                self._on_failure(exc)


def _consume_task_result(task: asyncio.Task[None]) -> None:
    """取走被放弃 worker 的结果，避免稍后刷无人认领异常。"""
    if not task.cancelled():
        task.exception()
