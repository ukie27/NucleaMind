"""`D23` `AgentInstance`：Channel 泵、被拒 turn 的回音、停止顺序与 `Ctrl-C` 状态机。

职责：验运行期那几条容易被忽略的路径——重复投递怎么给用户交代、一条炸掉的消息会不会
把泵带走、`stop()` 会不会漏掉插件派生的任务、两次 `Ctrl-C` 各做什么。
不负责：验装配（`test_bootstrap.py`）、验渲染（`tests/builtins/test_cli_entry.py`）。

**`_Interrupts` 单独测**：`nm run` 的其余部分要一个真终端，而这个状态机恰好是那条命令
里唯一有分支的地方——第一次取消 turn、第二次退出，`§10.3` 的全部内容。
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from nucleamind.contracts import CancelReason, EventName, StreamState
from nucleamind.kernel.turn import CancelToken
from nucleamind.runtime.cli.commands.run import _Interrupts
from nucleamind.runtime.instance import AgentInstance

from ._support import SCRIPT, TEST_MANIFESTS, text_response, write_config
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
