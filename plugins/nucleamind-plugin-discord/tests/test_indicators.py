"""typing 指示器与反应 emoji 的验收（开发方案 `D33`）。

| 验收项 | 测试 |
| --- | --- |
| 已读反应立刻打、工作中反应延迟打 | `TestLifecycle` |
| **一条 DELTA 不能拆掉指示器** | `TestLifecycle`（legacy `runtime.py:479` 那条坑的新家） |
| 平台失败不冒泡 | `TestFailuresAreSwallowed` |

**注入 sleep，不真的等 2 秒**：延迟 emoji 与 typing 循环是本模块仅有的两处时间语义。
"""

from __future__ import annotations

import asyncio

from _fakes import CONVERSATION, FakeReactions, FakeSleep, outbound
from nucleamind_plugin_discord import Indicators

from nucleamind.contracts import StreamState


def indicators(reactions: FakeReactions, sleep: FakeSleep, **kwargs: object) -> Indicators:
    return Indicators(reactions=reactions, sleep=sleep, **kwargs)  # type: ignore[arg-type]


async def _settle(rounds: int = 5) -> None:
    """让事件循环把已就绪的回调排空。不依赖时间，只依赖没有待跑的就绪回调。"""
    for _ in range(rounds):
        await asyncio.sleep(0)


class TestLifecycle:
    async def test_the_read_receipt_lands_immediately(self) -> None:
        reactions, sleep = FakeReactions(), FakeSleep()
        panel = indicators(reactions, sleep)
        await panel.start(CONVERSATION, "1001")
        assert reactions.added[0] == (CONVERSATION, "1001", "👀")
        await panel.stop(CONVERSATION)

    async def test_the_working_emoji_waits_for_its_delay(self) -> None:
        """延迟的意义是只对慢 turn 显示——秒回的消息不该留下两个反应。"""
        reactions, sleep = FakeReactions(), FakeSleep()
        panel = indicators(reactions, sleep, working_delay_ms=2000)
        await panel.start(CONVERSATION, "1001")
        await _settle()
        assert ("🔧" in [emoji for _, _, emoji in reactions.added]) is True
        # 注入的 sleep 立刻返回，但它被真的调用过、参数是配置的那个值。
        assert 2.0 in sleep.calls
        await panel.stop(CONVERSATION)

    async def test_a_delta_does_not_tear_down_the_indicators(self) -> None:
        """legacy `runtime.py:479` 那条坑的新家。

        判断「什么算说完了」在 `channel.py`，本模块只认 `start()` / `stop()`。因此这条
        用例断言的是**调用方**的判定：一条 `DELTA` 走不到 `stop()`。
        """
        from nucleamind_plugin_discord.channel import _TERMINAL

        assert StreamState.DELTA not in _TERMINAL
        assert StreamState.STARTED not in _TERMINAL
        assert _TERMINAL == frozenset(
            {StreamState.FINAL, StreamState.CANCELLED, StreamState.FAILED}
        )

    async def test_stop_clears_what_was_shown(self) -> None:
        reactions, sleep = FakeReactions(), FakeSleep()
        panel = indicators(reactions, sleep)
        await panel.start(CONVERSATION, "1001")
        await _settle()
        await panel.stop(CONVERSATION)
        assert {emoji for _, _, emoji in reactions.cleared} == {"👀", "🔧"}
        assert panel.active() == 0

    async def test_a_fast_turn_never_shows_the_working_emoji(self) -> None:
        """终态先到时那个任务被取消，反应根本没出现——因此也不需要被清理。"""
        reactions = FakeReactions()

        async def slow_sleep(seconds: float) -> None:
            await asyncio.Event().wait()  # 永远不返回：模拟延迟还没到

        panel = Indicators(reactions=reactions, sleep=slow_sleep)
        await panel.start(CONVERSATION, "1001")
        await panel.stop(CONVERSATION)
        assert [emoji for _, _, emoji in reactions.added] == ["👀"]
        assert [emoji for _, _, emoji in reactions.cleared] == ["👀"]

    async def test_starting_twice_cleans_up_the_previous_round(self) -> None:
        """否则一条消息接一条消息会在频道里堆出一串没人清理的反应。"""
        reactions, sleep = FakeReactions(), FakeSleep()
        panel = indicators(reactions, sleep)
        await panel.start(CONVERSATION, "1001")
        await _settle()
        await panel.start(CONVERSATION, "1002")
        assert reactions.cleared  # 上一轮被清掉了
        assert panel.active() == 1
        await panel.stop(CONVERSATION)

    async def test_typing_is_reissued_periodically(self) -> None:
        """平台侧的 typing 只维持几秒，不续期就会消失。"""
        reactions, sleep = FakeReactions(), FakeSleep()
        panel = indicators(reactions, sleep, typing_interval_ms=8000)
        await panel.start(CONVERSATION, "1001")
        await _settle()
        assert reactions.typed.count(CONVERSATION) >= 2
        assert 8.0 in sleep.calls
        await panel.stop(CONVERSATION)

    async def test_shutdown_clears_every_conversation(self) -> None:
        reactions, sleep = FakeReactions(), FakeSleep()
        panel = indicators(reactions, sleep)
        await panel.start("a", "1")
        await panel.start("b", "2")
        assert panel.active() == 2
        await panel.shutdown()
        assert panel.active() == 0

    async def test_stopping_an_unknown_conversation_is_a_no_op(self) -> None:
        reactions, sleep = FakeReactions(), FakeSleep()
        panel = indicators(reactions, sleep)
        await panel.stop("never-started")
        assert reactions.cleared == []


class TestFailuresAreSwallowed:
    async def test_a_failing_platform_never_bubbles_up(self) -> None:
        """反应可能因为消息被删、权限不足或频道归档而失败——那是装饰不是内容。"""
        reactions, sleep = FakeReactions(fail=True), FakeSleep()
        panel = indicators(reactions, sleep)
        await panel.start(CONVERSATION, "1001")
        await _settle()
        await panel.stop(CONVERSATION)
        assert panel.active() == 0

    async def test_disabling_the_emojis_skips_them(self) -> None:
        reactions, sleep = FakeReactions(), FakeSleep()
        panel = indicators(reactions, sleep, read_receipt_emoji="", working_emoji="")
        await panel.start(CONVERSATION, "1001")
        await _settle()
        assert reactions.added == []
        await panel.stop(CONVERSATION)

    async def test_a_zero_typing_interval_disables_the_loop(self) -> None:
        reactions, sleep = FakeReactions(), FakeSleep()
        panel = indicators(reactions, sleep, typing_interval_ms=0)
        await panel.start(CONVERSATION, "1001")
        await _settle()
        assert reactions.typed == []
        await panel.stop(CONVERSATION)


def test_the_terminal_states_used_by_the_channel_match_the_contract() -> None:
    """`outbound.TERMINAL_MARKERS` 只覆盖两个终态，而清指示器要覆盖三个。

    差别是刻意的：`FINAL` 是完整答案，不需要标记但同样要收掉指示器。
    """
    from nucleamind_plugin_discord import TERMINAL_MARKERS
    from nucleamind_plugin_discord.channel import _TERMINAL

    assert set(TERMINAL_MARKERS) < _TERMINAL
    assert outbound("答案").stream_state in _TERMINAL
