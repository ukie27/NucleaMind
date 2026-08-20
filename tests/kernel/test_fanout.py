"""`kernel/routing/fanout.py` 的验收（开发方案 `D33`）。

| 验收项 | 测试 |
| --- | --- |
| 同 conversation 严格按到达顺序串行（`EDG-202`） | `TestOrdering` |
| 跨 conversation 并发 | `TestConcurrency` |
| lane 排空即回收、不超并发上界 | `TestLaneLifecycle` |
| 队列满 / 并发满时明确拒绝而不是静默丢弃 | `TestBackpressure` |
| 一条消息炸掉不带走 lane，一条 lane 不带走泵 | `TestFailureIsolation` |
| `drain()` 取消在途、丢弃排队 | `TestDrain` |

**并发一律用 `asyncio.Barrier` / `asyncio.Event` 制造确定的重叠窗口，全程不用 `sleep`**：
串行化会让 barrier 直接超时死锁（是一个确定的失败），而看耗时的断言在慢机器上会假阳性。
这是 `tests/kernel/test_engine.py` 与 `test_context_builder.py` 的既有做法。
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Final

import pytest

from nucleamind.contracts import (
    ErrorCode,
    InboundMessage,
    InstanceId,
    NucleaError,
    Sender,
)
from nucleamind.kernel.routing import (
    DEFAULT_CHANNEL_CONCURRENCY,
    DEFAULT_CHANNEL_QUEUE_MAX_SIZE,
    ConversationFanout,
)

INSTANCE: Final = InstanceId("test")
CHANNEL: Final = "chan"


def message(conversation: str, text: str, *, index: int = 0) -> InboundMessage:
    return InboundMessage(
        message_id=f"{conversation}-{index}-{text}",
        instance_id=INSTANCE,
        channel_id=CHANNEL,
        conversation_id=conversation,
        sender=Sender(user_id="u1"),
        content=text,
        timestamp=datetime.now(UTC),
    )


async def stream(*messages: InboundMessage) -> AsyncIterator[InboundMessage]:
    for item in messages:
        yield item


async def never_ends(*messages: InboundMessage, gate: asyncio.Event) -> AsyncIterator[InboundMessage]:
    """吐完给定消息后卡住，让泵保持活着——模拟一条真实的、还连着的 Channel。"""
    for item in messages:
        yield item
    await gate.wait()


class Recorder:
    """记录处理顺序的 handler，可选在每条上让出若干次事件循环。"""

    def __init__(self, *, yields: int = 0) -> None:
        self.handled: list[str] = []
        self.failures: list[Exception] = []
        self.dropped: list[tuple[str, NucleaError]] = []
        self._yields = yields

    async def handle(self, item: InboundMessage) -> None:
        for _ in range(self._yields):
            await asyncio.sleep(0)
        self.handled.append(item.content)

    def on_failure(self, exc: Exception) -> None:
        self.failures.append(exc)

    async def on_dropped(self, item: InboundMessage, error: NucleaError) -> None:
        self.dropped.append((item.content, error))

    def fanout(self, **kwargs: int) -> ConversationFanout:
        return ConversationFanout(
            self.handle, on_failure=self.on_failure, on_dropped=self.on_dropped, **kwargs
        )


# ------------------------------------------------------------------------------ 顺序


class TestOrdering:
    async def test_one_conversation_is_strictly_fifo(self) -> None:
        """`EDG-202` 的机制层断言：同 conversation 到达顺序即处理顺序。

        每条消息中途让出 3 次事件循环——如果实现改成「每条消息 create_task」，
        这里就有充分的机会乱序。
        """
        recorder = Recorder(yields=3)
        fanout = recorder.fanout()
        await fanout.run(stream(*(message("c1", str(i), index=i) for i in range(20))))
        await fanout.drain(cancel=False)
        assert recorder.handled == [str(i) for i in range(20)]

    async def test_interleaved_conversations_each_keep_their_own_order(self) -> None:
        recorder = Recorder(yields=2)
        fanout = recorder.fanout()
        items = [
            message("a" if i % 2 == 0 else "b", str(i), index=i) for i in range(10)
        ]
        await fanout.run(stream(*items))
        await fanout.drain(cancel=False)
        evens = [text for text in recorder.handled if int(text) % 2 == 0]
        odds = [text for text in recorder.handled if int(text) % 2 == 1]
        assert evens == ["0", "2", "4", "6", "8"]
        assert odds == ["1", "3", "5", "7", "9"]


# ------------------------------------------------------------------------------ 并发


class TestConcurrency:
    async def test_two_conversations_run_at_the_same_time(self) -> None:
        """本模块存在的全部理由。**串行化会让 barrier 超时**，那是一个确定的失败。"""
        barrier = asyncio.Barrier(2)
        seen: list[str] = []

        async def handle(item: InboundMessage) -> None:
            await asyncio.wait_for(barrier.wait(), timeout=2)
            seen.append(item.conversation_id)

        fanout = ConversationFanout(
            handle, on_failure=lambda exc: None, on_dropped=_never_dropped
        )
        await fanout.run(stream(message("a", "1"), message("b", "1")))
        await fanout.drain(cancel=False)
        assert sorted(seen) == ["a", "b"]

    async def test_one_slow_conversation_does_not_block_another(self) -> None:
        """「一个用户的慢 turn 卡住同一个 bot 上所有人」的反面断言。"""
        blocked = asyncio.Event()
        fast_done = asyncio.Event()

        async def handle(item: InboundMessage) -> None:
            if item.conversation_id == "slow":
                await blocked.wait()
                return
            fast_done.set()

        fanout = ConversationFanout(
            handle, on_failure=lambda exc: None, on_dropped=_never_dropped
        )
        gate = asyncio.Event()
        pump = asyncio.create_task(
            fanout.run(never_ends(message("slow", "1"), message("fast", "1"), gate=gate))
        )
        # 慢 lane 还卡着，快 lane 必须已经跑完。
        await asyncio.wait_for(fast_done.wait(), timeout=2)
        blocked.set()
        gate.set()
        await asyncio.wait_for(pump, timeout=2)
        await fanout.drain(cancel=False)


# ------------------------------------------------------------------------------ lane 生命周期


class TestLaneLifecycle:
    async def test_a_lane_is_reclaimed_when_it_drains(self) -> None:
        """队列空即退出，没有 idle TTL——因此 `lanes()` 恒等于「此刻有活儿的会话数」。"""
        recorder = Recorder()
        fanout = recorder.fanout()
        await fanout.run(stream(message("c1", "x")))
        await fanout.drain(cancel=False)
        assert fanout.lanes() == 0

    async def test_lane_count_never_exceeds_concurrency(self) -> None:
        """超出上界的会话被拒（`TestBackpressure` 验它的理由），lane 数因此有硬上限。"""
        recorder = Recorder()
        blocked = asyncio.Event()

        async def handle(item: InboundMessage) -> None:
            await blocked.wait()

        fanout = ConversationFanout(
            handle,
            on_failure=recorder.on_failure,
            on_dropped=recorder.on_dropped,
            concurrency=3,
        )
        gate = asyncio.Event()
        pump = asyncio.create_task(
            fanout.run(
                never_ends(*(message(f"c{i}", "x") for i in range(10)), gate=gate)
            )
        )
        await _settle()
        assert fanout.lanes() == 3
        assert len(recorder.dropped) == 7
        blocked.set()
        gate.set()
        await asyncio.wait_for(pump, timeout=2)
        await fanout.drain(cancel=True)

    async def test_waiting_reports_the_queue_depth(self) -> None:
        blocked = asyncio.Event()
        entered = asyncio.Event()

        async def handle(item: InboundMessage) -> None:
            entered.set()
            await blocked.wait()

        fanout = ConversationFanout(
            handle, on_failure=lambda exc: None, on_dropped=_never_dropped
        )
        gate = asyncio.Event()
        pump = asyncio.create_task(
            fanout.run(never_ends(*(message("c1", str(i), index=i) for i in range(4)), gate=gate))
        )
        await asyncio.wait_for(entered.wait(), timeout=2)
        # 一条在跑，其余在排队。
        assert fanout.waiting("c1") == 3
        assert fanout.waiting("absent") == 0
        blocked.set()
        gate.set()
        await asyncio.wait_for(pump, timeout=2)
        await fanout.drain(cancel=True)


# ------------------------------------------------------------------------------ 背压


class TestBackpressure:
    async def test_a_full_lane_queue_rejects_the_newest(self) -> None:
        """拒绝**最新**的那条而不是挤掉最老的：丢一条已排上队的消息等于静默吃掉输入。"""
        recorder = Recorder()
        blocked = asyncio.Event()

        async def handle(item: InboundMessage) -> None:
            await blocked.wait()
            recorder.handled.append(item.content)

        fanout = ConversationFanout(
            handle,
            on_failure=recorder.on_failure,
            on_dropped=recorder.on_dropped,
            queue_max_size=2,
        )
        gate = asyncio.Event()
        pump = asyncio.create_task(
            fanout.run(never_ends(*(message("c1", str(i), index=i) for i in range(5)), gate=gate))
        )
        await asyncio.sleep(0)
        blocked.set()
        gate.set()
        await asyncio.wait_for(pump, timeout=2)
        await fanout.drain(cancel=False)
        rejected = [text for text, _ in recorder.dropped]
        assert rejected, "队列满时必须有消息被明确拒绝"
        # 被拒的是靠后到达的那些，最早的几条留在队列里跑完了。
        assert rejected == sorted(rejected, key=int)
        assert int(rejected[0]) > int(recorder.handled[0])
        error = recorder.dropped[0][1]
        assert error.code is ErrorCode.INPUT_SESSION_BUSY
        assert error.detail["reason"] == "lane_queue_full"
        assert error.detail["limit"] == 2

    async def test_channel_saturation_is_a_distinct_reason(self) -> None:
        """两种背压的补救动作不同（等一会儿 vs 会话太多），因此 `reason` 必须分得开。"""
        recorder = Recorder()
        blocked = asyncio.Event()

        async def handle(item: InboundMessage) -> None:
            await blocked.wait()

        fanout = ConversationFanout(
            handle,
            on_failure=recorder.on_failure,
            on_dropped=recorder.on_dropped,
            concurrency=2,
        )
        gate = asyncio.Event()
        pump = asyncio.create_task(
            fanout.run(never_ends(*(message(f"c{i}", "x") for i in range(5)), gate=gate))
        )
        await asyncio.sleep(0)
        blocked.set()
        gate.set()
        await asyncio.wait_for(pump, timeout=2)
        await fanout.drain(cancel=True)
        assert recorder.dropped
        error = recorder.dropped[0][1]
        assert error.detail["reason"] == "channel_saturated"
        assert error.detail["limit"] == 2

    @pytest.mark.parametrize("kwargs", [{"concurrency": 0}, {"queue_max_size": 0}])
    def test_non_positive_bounds_are_rejected(self, kwargs: dict[str, int]) -> None:
        """0 会让扇出静默退化成「一条也不收」，那不是任何人想要的。"""
        recorder = Recorder()
        with pytest.raises(NucleaError) as excinfo:
            recorder.fanout(**kwargs)
        assert excinfo.value.code is ErrorCode.KERNEL_INVARIANT_VIOLATED


# ------------------------------------------------------------------------------ 失败隔离


class TestFailureIsolation:
    async def test_one_exploding_message_does_not_kill_the_lane(self) -> None:
        recorder = Recorder()

        async def handle(item: InboundMessage) -> None:
            if item.content == "boom":
                raise RuntimeError("boom")
            recorder.handled.append(item.content)

        fanout = ConversationFanout(
            handle, on_failure=recorder.on_failure, on_dropped=recorder.on_dropped
        )
        await fanout.run(
            stream(message("c1", "a"), message("c1", "boom"), message("c1", "b"))
        )
        await fanout.drain(cancel=False)
        assert recorder.handled == ["a", "b"]
        assert len(recorder.failures) == 1

    async def test_one_exploding_lane_does_not_kill_the_pump(self) -> None:
        recorder = Recorder()

        async def handle(item: InboundMessage) -> None:
            if item.conversation_id == "bad":
                raise RuntimeError("boom")
            recorder.handled.append(item.conversation_id)

        fanout = ConversationFanout(
            handle, on_failure=recorder.on_failure, on_dropped=recorder.on_dropped
        )
        await fanout.run(stream(message("bad", "x"), message("good", "x")))
        await fanout.drain(cancel=False)
        assert recorder.handled == ["good"]


# ------------------------------------------------------------------------------ 排干


class TestDrain:
    async def test_pending_messages_can_be_discarded_while_current_work_finishes(self) -> None:
        recorder = Recorder()
        entered = asyncio.Event()
        release = asyncio.Event()

        async def handle(item: InboundMessage) -> None:
            entered.set()
            await release.wait()
            recorder.handled.append(item.content)

        fanout = ConversationFanout(
            handle, on_failure=recorder.on_failure, on_dropped=recorder.on_dropped
        )
        await fanout.run(stream(*(message("c1", str(i), index=i) for i in range(3))))
        await asyncio.wait_for(entered.wait(), timeout=1)
        assert fanout.discard_pending() == 2
        release.set()
        await fanout.drain(cancel=False)
        assert recorder.handled == ["0"]

    async def test_drain_cancels_in_flight_and_discards_queued(self) -> None:
        """与串行泵时代的 `pump.cancel()` 语义逐字相同，只是从 1 个协程变成 N 个。"""
        recorder = Recorder()
        blocked = asyncio.Event()

        async def handle(item: InboundMessage) -> None:
            await blocked.wait()
            recorder.handled.append(item.content)

        fanout = ConversationFanout(
            handle, on_failure=recorder.on_failure, on_dropped=recorder.on_dropped
        )
        gate = asyncio.Event()
        pump = asyncio.create_task(
            fanout.run(never_ends(*(message("c1", str(i), index=i) for i in range(3)), gate=gate))
        )
        await asyncio.sleep(0)
        await fanout.drain(cancel=True)
        assert fanout.lanes() == 0
        assert recorder.handled == []
        gate.set()
        pump.cancel()
        await asyncio.gather(pump, return_exceptions=True)

    async def test_drain_is_safe_to_call_twice(self) -> None:
        recorder = Recorder()
        fanout = recorder.fanout()
        await fanout.run(stream(message("c1", "x")))
        await fanout.drain(cancel=True)
        await fanout.drain(cancel=True)
        assert fanout.lanes() == 0


# ------------------------------------------------------------------------------ 默认值


def test_lane_queue_default_matches_the_scheduler_bound() -> None:
    """两个数相等不是巧合：lane 队列**接替**而不是叠加 scheduler 的界（见模块 docstring）。"""
    from nucleamind.kernel.routing import DEFAULT_QUEUE_MAX_SIZE

    assert DEFAULT_CHANNEL_QUEUE_MAX_SIZE == DEFAULT_QUEUE_MAX_SIZE
    assert DEFAULT_CHANNEL_CONCURRENCY > 0


async def _settle(rounds: int = 5) -> None:
    """让事件循环把已就绪的回调排空。

    `sleep(0)` 只让出一次，而「泵取一条 → worker 被派出去 → worker 真的开始跑」跨了好几
    次调度。多让几次比 `sleep(0.01)` 确定：它不依赖时间，只依赖没有待跑的就绪回调。
    """
    for _ in range(rounds):
        await asyncio.sleep(0)


async def _never_dropped(item: InboundMessage, error: NucleaError) -> None:
    raise AssertionError(f"不应有消息被拒：{item.content} / {error.code.value}")
