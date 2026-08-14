"""`D23` `AgentInstance`：Channel 泵、被拒 turn 的回音、停止顺序与 `Ctrl-C` 状态机。

职责：验运行期那几条容易被忽略的路径——重复投递怎么给用户交代、一条炸掉的消息会不会
把泵带走、`stop()` 会不会漏掉插件派生的任务、两次 `Ctrl-C` 各做什么。
不负责：验装配（`test_bootstrap.py`）、验渲染（`tests/builtins/test_cli_entry.py`）。

**`_Interrupts` 单独测**：`nm run` 的其余部分要一个真终端，而这个状态机恰好是那条命令
里唯一有分支的地方——第一次取消 turn、第二次退出，`§10.3` 的全部内容。
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path

import pytest

from nucleamind.contracts import (
    CancelReason,
    CapabilityKind,
    ErrorCode,
    EventName,
    NucleaError,
    StreamState,
)
from nucleamind.kernel.plugins import PluginPhase
from nucleamind.kernel.turn import CancelToken
from nucleamind.runtime.cli.commands.run import _Interrupts
from nucleamind.runtime.instance import AgentInstance

from ._support import (
    MULTI_CHANNEL_ID,
    SCRIPT,
    TEST_MANIFESTS,
    ScriptedChannel,
    inbound,
    manifests_with_multi_channel,
    text_response,
    write_config,
)
from .test_bootstrap import _boot


@pytest.fixture(autouse=True)
def _script() -> None:
    SCRIPT[:] = [text_response("好的。"), text_response("好的。")]


def console_of(instance: AgentInstance) -> object:
    channel = dict(instance.channels)["cli"]
    return channel._console  # noqa: SLF001 - 断言渲染结果需要它


async def test_a_duplicate_message_gets_an_explicit_echo(tmp_path: Path) -> None:
    """`EDG-201`：重复投递不产生第二次副作用，但用户要知道发生了什么。

    被去重的消息没有终态事件（那条 turn 从未开始），泵因此自己合成一条出站消息——
    否则 CLI 会永远等一个不会到来的终态。
    """
    write_config(tmp_path)
    instance = await _boot(tmp_path, manifests=TEST_MANIFESTS)
    try:
        await instance.start()
        console = console_of(instance)
        first = console.submit("在吗")  # type: ignore[attr-defined]
        await asyncio.wait_for(console.wait_for_turn(), timeout=2)  # type: ignore[attr-defined]

        # 同一个 message_id 再投一次：去重命中。
        console._counter -= 1  # type: ignore[attr-defined] # noqa: SLF001 - 复现同一个 id
        again = console.submit("在吗")  # type: ignore[attr-defined]
        assert again.message_id == first.message_id
        await asyncio.wait_for(console.wait_for_turn(), timeout=2)  # type: ignore[attr-defined]
        assert "重复投递" in console.rendered[-1]  # type: ignore[attr-defined]
        assert console.last_state is StreamState.FAILED  # type: ignore[attr-defined]
    finally:
        await instance.stop()


async def test_stop_is_idempotent_and_publishes_both_events(tmp_path: Path) -> None:
    write_config(tmp_path)
    instance = await _boot(tmp_path, manifests=TEST_MANIFESTS)
    await instance.start()
    await instance.stop()
    await instance.stop()
    names = [event.name for event in instance.diagnostics.events.events()]
    assert names.count(EventName.INSTANCE_STOPPED) == 1
    assert names.count(EventName.INSTANCE_STOPPING) == 1


async def test_stop_cancels_plugin_tasks(tmp_path: Path) -> None:
    """`EDG-104`/`EDG-105`：插件派生的后台任务在停止时被收走。"""
    write_config(tmp_path)
    instance = await _boot(tmp_path, manifests=TEST_MANIFESTS)
    await instance.start()
    ctx = instance.contexts[0]

    async def forever() -> None:
        await asyncio.sleep(3600)

    ctx.spawn_task(forever(), name="probe")
    task = next(iter(ctx.tasks))
    await instance.stop()
    assert task.cancelled()


# ---------------------------------------------------------------- D28 生命周期


async def test_stop_walks_the_lifecycle_in_reverse_load_order(tmp_path: Path) -> None:
    """`PLG-005`：停止顺序是加载顺序的逆序，且每个提供方都走完状态机。"""
    write_config(tmp_path)
    instance = await _boot(tmp_path, manifests=TEST_MANIFESTS)
    loaded = [lifecycle.plugin_id for lifecycle in instance.lifecycles]
    assert loaded == [ctx.plugin_id for ctx in instance.contexts]
    assert all(item.phase is PluginPhase.LOADED for item in instance.lifecycles)

    await instance.start()
    assert all(item.phase is PluginPhase.STARTED for item in instance.lifecycles)

    await instance.stop()
    assert all(item.phase is PluginPhase.STOPPED for item in instance.lifecycles)
    deactivated = [
        event.payload["plugin"]
        for event in instance.diagnostics.events.events()
        if event.name is EventName.PLUGIN_DEACTIVATED
    ]
    assert deactivated == list(reversed(loaded))


async def test_stop_unsubscribes_the_plugin_event_bridge(tmp_path: Path) -> None:
    """`EDG-105` 第二项：停止后事件订阅失效，handler 不再收到投递。"""
    write_config(tmp_path)
    instance = await _boot(tmp_path, manifests=TEST_MANIFESTS)
    await instance.start()
    ctx = instance.contexts[0]
    seen: list[str] = []

    async def observe(event: object) -> None:
        seen.append(type(event).__name__)

    ctx.events.subscribe(EventName.INSTANCE_STOPPING, observe)
    assert any(sub.name == f"plugin:{ctx.plugin_id}" for sub in instance.bus.subscribers())

    await instance.stop()
    assert not any(sub.name == f"plugin:{ctx.plugin_id}" for sub in instance.bus.subscribers())
    before = len(seen)
    instance.bus.publish(EventName.INSTANCE_STOPPING)
    await asyncio.sleep(0)
    assert len(seen) == before


async def test_a_stopped_plugin_cannot_spawn_new_tasks(tmp_path: Path) -> None:
    """`EDG-105` 第三项的另一半：停止之后派生的任务不在任何一轮取消的覆盖范围里。"""
    write_config(tmp_path)
    instance = await _boot(tmp_path, manifests=TEST_MANIFESTS)
    await instance.start()
    ctx = instance.contexts[0]
    await instance.stop()

    async def late() -> None:  # pragma: no cover - 它就不该被跑
        await asyncio.sleep(0)

    with pytest.raises(NucleaError) as caught:
        ctx.spawn_task(late(), name="late")
    assert caught.value.code is ErrorCode.KERNEL_INVARIANT_VIOLATED
    assert ctx.tasks == set()


async def test_a_disabled_plugin_leaves_no_capability_behind(tmp_path: Path) -> None:
    """`EDG-105` 第一项：被禁用的提供方在这次实例里一项能力都查不到。

    首版不热更新（技术方案 §10.4）：禁用在**下一次启动**生效，因此「注销能力」的兑现
    形态是「它的 `setup()` 根本没跑过」——registry 解析后只读（`NFR-403`），运行期没有
    第二条把已冻结的能力摘掉的路径。
    """
    write_config(tmp_path, plugins={"disable": ["tools-shell"]})
    instance = await _boot(tmp_path, manifests=TEST_MANIFESTS)
    try:
        assert "tools-shell" not in [ctx.plugin_id for ctx in instance.contexts]
        # 内建全部以 `Builtin()` 身份注册，因此「谁不在了」只能按能力名看。
        active = [item.ref.name for item in instance.registry.of_kind(CapabilityKind.TOOL)]
        assert "shell.exec" not in active
        assert "shell.exec" not in [tool.name for tool in instance.deps.tool_specs]
    finally:
        await instance.stop()


async def test_a_hanging_plugin_does_not_hold_up_the_instance(tmp_path: Path) -> None:
    """`EDG-104`：吞掉取消的后台任务不能扣住实例退出。"""
    write_config(tmp_path, plugins={"stop_timeout_ms": 50})
    instance = await _boot(tmp_path, manifests=TEST_MANIFESTS)
    await instance.start()
    ctx = instance.contexts[0]
    assert instance.stop_timeout_ms == 50

    async def stubborn() -> None:
        """吞掉停止流程那一次取消。`release` 之后才肯死，否则用例自己也收不了场。"""
        while True:
            try:
                await asyncio.sleep(3600)
            except asyncio.CancelledError:
                if release.is_set():
                    raise
                continue

    release = asyncio.Event()

    ctx.spawn_task(stubborn(), name="stubborn")
    task = next(iter(ctx.tasks))
    await asyncio.wait_for(instance.stop(), timeout=5)
    # 用例自己收尾：被放弃的任务在生产里随进程一起没了，而这里事件循环还要继续用。
    release.set()
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)

    failures = [
        event
        for event in instance.diagnostics.events.events()
        if event.name is EventName.PLUGIN_FAILED and event.payload.get("timed_out")
    ]
    assert [event.payload["plugin"] for event in failures] == [ctx.plugin_id]
    assert failures[0].error is not None
    assert failures[0].error.code is ErrorCode.TIMEOUT_PLUGIN_STOP
    lifecycle = next(item for item in instance.lifecycles if item.plugin_id == ctx.plugin_id)
    assert lifecycle.phase is PluginPhase.FAILED


# ---------------------------------------------------------------- Ctrl-C 状态机


class _FakeOrchestrator:
    """只提供 `_Interrupts` 要的两件事。"""

    def __init__(self, live: tuple[str, ...]) -> None:
        self.live_turns = live
        self.cancelled: list[tuple[str, CancelReason]] = []

    def cancel(self, turn_id: str, reason: CancelReason) -> bool:
        self.cancelled.append((turn_id, reason))
        return True


def _interrupts(live: tuple[str, ...]) -> tuple[_Interrupts, _FakeOrchestrator, CancelToken]:
    orchestrator = _FakeOrchestrator(live)
    instance = type("_I", (), {"orchestrator": orchestrator})()
    cancel = CancelToken()
    return _Interrupts(instance, cancel), orchestrator, cancel  # type: ignore[arg-type]


def test_the_first_ctrl_c_cancels_the_live_turn(capsys: pytest.CaptureFixture[str]) -> None:
    """会话继续——中断的是这一轮，不是进程（§10.3、`CliEntry.run` 的取消语义）。"""
    interrupts, orchestrator, cancel = _interrupts(("turn-1",))
    interrupts()
    assert orchestrator.cancelled == [("turn-1", CancelReason.USER)]
    assert not cancel.requested
    assert "再按一次" in capsys.readouterr().err


def test_ctrl_c_with_nothing_running_is_a_quit() -> None:
    """没有 turn 在跑时，`Ctrl-C` 的唯一合理含义是「退出」。"""
    interrupts, orchestrator, cancel = _interrupts(())
    # **本用例刻意是同步的**：退出路径会 `await stop()` 之后 `os._exit`，在测试进程里跑到
    # 那一步会直接把 pytest 打死。没有运行中的循环时 `create_task` 抛 `RuntimeError`，
    # 恰好让断言停在「令牌已被请求」这一步——退出动作是异步的，这条顺带钉住了。
    with pytest.raises(RuntimeError):
        interrupts()
    assert cancel.requested
    assert orchestrator.cancelled == []


# ---------------------------------------------------------- 泵的按 conversation 扇出（`D33`）


def multi_channel(instance: AgentInstance) -> ScriptedChannel:
    channel = dict(instance.channels)[MULTI_CHANNEL_ID]
    assert isinstance(channel, ScriptedChannel)
    return channel


def _answered(channel: ScriptedChannel, conversation: str) -> bool:
    """该会话是否已经拿到一条**完整答案**。

    不能只看「有没有出站消息」：流式的 `STARTED` / `DELTA` 也在 `delivered` 里，用它判
    会把「turn 刚开始」当成「turn 结束了」。
    """
    return any(
        m.conversation_id == conversation and m.is_complete_answer for m in channel.delivered
    )


async def _wait_for(predicate: Callable[[], bool], *, timeout: float = 3.0) -> None:
    """等一个条件成立。**不 `sleep` 固定时长**：断言的是「发生了」而不是「多久之内」。"""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while not predicate():
        if loop.time() > deadline:
            raise AssertionError("等待的条件在超时前没有成立")
        await asyncio.sleep(0)


async def test_two_conversations_on_one_channel_do_not_block_each_other(
    tmp_path: Path,
) -> None:
    """`D33` 的收益断言：一个用户的慢 turn 不再卡住同一个 bot 上所有人。

    在扇出之前，泵的 `await` 在 `async for` 里面——第二条消息要等第一条整条 turn 跑完才
    被取走，这条用例会超时。
    """
    write_config(tmp_path)
    SCRIPT[:] = [text_response("答案"), text_response("答案")]
    instance = await _boot(tmp_path, manifests=manifests_with_multi_channel())
    try:
        await instance.start()
        channel = multi_channel(instance)
        blocked = asyncio.Event()
        slow_entered = asyncio.Event()
        provider = instance.deps.model
        original_complete = provider.complete
        original_stream = provider.stream

        def is_slow(request: object) -> bool:
            return any("慢" in message.content for message in request.messages)  # type: ignore[attr-defined]

        async def gated_complete(request: object, cancel: object) -> object:
            if is_slow(request):
                slow_entered.set()
                await blocked.wait()
            return await original_complete(request, cancel)  # type: ignore[arg-type]

        def gated_stream(request: object, cancel: object) -> object:
            async def run() -> object:
                if is_slow(request):
                    slow_entered.set()
                    await blocked.wait()
                async for chunk in original_stream(request, cancel):  # type: ignore[arg-type]
                    yield chunk

            return run()

        # **两条路都要拦**：走 `complete` 还是 `stream` 由装配决定，只拦一条会让这条用例
        # 的结论取决于「谁先跑完」而不是「有没有被挡住」。
        provider.complete = gated_complete  # type: ignore[assignment, method-assign]
        provider.stream = gated_stream  # type: ignore[assignment, method-assign]

        channel.push(inbound("slow", "慢一点"))
        channel.push(inbound("fast", "快一点"))

        # 先确认慢会话真的卡在模型上，再断言快会话已经答完——否则断言的是时序巧合。
        await asyncio.wait_for(slow_entered.wait(), timeout=3)
        await _wait_for(lambda: _answered(channel, "fast"))
        assert not _answered(channel, "slow")
        blocked.set()
        await _wait_for(lambda: _answered(channel, "slow"))
    finally:
        await instance.stop()


async def test_the_same_conversation_still_enters_the_scheduler_in_arrival_order(
    tmp_path: Path,
) -> None:
    """`EDG-202` 的逐字断言：同 conversation 严格 FIFO、单写者。

    事件流里第二条 turn 的 `turn.started` 一定在第一条的终态之后——这就是「同一时刻至多
    一个写者」在事件层面的形状。扇出没有放松它，只是让**别的** conversation 不必等。
    """
    write_config(tmp_path)
    SCRIPT[:] = [text_response("一"), text_response("二")]
    instance = await _boot(tmp_path, manifests=manifests_with_multi_channel())
    seen: list[str] = []
    instance.bus.subscribe(lambda event: seen.append(event.name.value))
    try:
        await instance.start()
        channel = multi_channel(instance)
        channel.push(inbound("same", "一"))
        channel.push(inbound("same", "二"))
        await _wait_for(
            lambda: len([m for m in channel.delivered if m.is_complete_answer]) == 2
        )
    finally:
        await instance.stop()

    starts = [i for i, name in enumerate(seen) if name == EventName.TURN_STARTED.value]
    completions = [i for i, name in enumerate(seen) if name == EventName.TURN_COMPLETED.value]
    assert len(starts) == 2 and len(completions) == 2
    assert starts[0] < completions[0] < starts[1] < completions[1]


async def test_a_full_lane_echoes_session_busy_and_publishes_input_dropped(
    tmp_path: Path,
) -> None:
    """背压要**明确拒绝**而不是静默丢弃，而且回音与 scheduler 拒绝时长得一样。"""
    write_config(tmp_path, routing={"channel_queue_max_size": 1})
    SCRIPT[:] = [text_response("好") for _ in range(6)]
    instance = await _boot(tmp_path, manifests=manifests_with_multi_channel())
    dropped: list[str] = []

    def watch(event: object) -> None:
        if event.name is EventName.INSTANCE_INPUT_DROPPED:  # type: ignore[attr-defined]
            dropped.append(event.name.value)  # type: ignore[attr-defined]

    instance.bus.subscribe(watch)
    try:
        await instance.start()
        channel = multi_channel(instance)
        blocked = asyncio.Event()
        provider = instance.deps.model
        original = provider.complete  # type: ignore[union-attr]

        async def gated(request: object, cancel: object) -> object:
            await blocked.wait()
            return await original(request, cancel)  # type: ignore[arg-type]

        provider.complete = gated  # type: ignore[union-attr, assignment, method-assign]

        for index in range(5):
            channel.push(inbound("busy", str(index), message_id=f"m{index}"))
        await _wait_for(lambda: bool(dropped))
        rejected = [m for m in channel.delivered if m.stream_state is StreamState.FAILED]
        assert rejected, "被拒的消息必须有回音"
        assert "未受理" in rejected[0].content
        blocked.set()
    finally:
        await instance.stop()


async def test_stop_drains_every_lane(tmp_path: Path) -> None:
    """停止之后不能留下任何在跑的 lane——否则一次正常退出会挂着后台任务。"""
    write_config(tmp_path)
    SCRIPT[:] = [text_response("好") for _ in range(4)]
    instance = await _boot(tmp_path, manifests=manifests_with_multi_channel())
    await instance.start()
    channel = multi_channel(instance)
    for index in range(3):
        channel.push(inbound(f"c{index}", "在吗", message_id=f"s{index}"))
    await instance.stop()
    assert all(fanout.lanes() == 0 for fanout in instance._fanouts) or not instance._fanouts  # noqa: SLF001
