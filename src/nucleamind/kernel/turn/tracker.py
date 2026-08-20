"""Turn 准入与在途执行跟踪。

职责：在实例停机时同时覆盖两类工作：已经拿到 Session 槽位、拥有业务取消令牌的 Turn，
以及已经准入但仍在等待槽位的提交。它不决定调度策略，也不负责把取消写成业务终态；后者
仍由 Orchestrator 与 Engine 完成。

不负责：Session 排队策略、业务终态构造或插件资源清理。

正常停止先请求 `CancelReason.SHUTDOWN` 并等待所有已准入提交退出。只有宽限期耗尽时才取消
承载提交的 asyncio Task；这是进程退出边界的最后手段，不应被普通业务取消复用。
"""

from __future__ import annotations

import asyncio

from nucleamind.contracts import CancelReason, ErrorCode, NucleaError, TurnId

from .cancel import CancelToken

__all__ = ["TurnTracker"]


class TurnTracker:
    """记录准入提交和实际运行的 Turn，并协调有界停止。"""

    def __init__(self) -> None:
        self._accepting = True
        self._submissions: set[asyncio.Task[object]] = set()
        self._live: dict[TurnId, CancelToken] = {}
        self._idle = asyncio.Event()
        self._idle.set()

    @property
    def accepting(self) -> bool:
        return self._accepting

    @property
    def live_turns(self) -> tuple[TurnId, ...]:
        return tuple(self._live)

    def enter_submission(self) -> asyncio.Task[object]:
        """登记一次已通过停机门槛的 `handle()` 调用。"""
        task = asyncio.current_task()
        if task is None:
            raise NucleaError(
                ErrorCode.KERNEL_INVARIANT_VIOLATED,
                "Turn 必须运行在受管理的 asyncio Task 中。",
            )
        self._submissions.add(task)
        self._idle.clear()
        return task

    def leave_submission(self, task: asyncio.Task[object]) -> None:
        self._submissions.discard(task)
        if not self._submissions:
            self._idle.set()

    def activate(self, turn_id: TurnId, token: CancelToken) -> None:
        """登记已经取得 Session 槽位、可接受业务取消的 Turn。"""
        self._live[turn_id] = token
        if not self._accepting:
            token.request(CancelReason.SHUTDOWN)

    def finish(self, turn_id: TurnId) -> None:
        self._live.pop(turn_id, None)

    def cancel(self, turn_id: TurnId, reason: CancelReason) -> bool:
        token = self._live.get(turn_id)
        if token is None:
            return False
        token.request(reason)
        return True

    def begin_shutdown(self) -> None:
        self._accepting = False
        for token in tuple(self._live.values()):
            token.request(CancelReason.SHUTDOWN)

    async def finish_shutdown(self, *, timeout_ms: int) -> tuple[TurnId, ...] | None:
        """正常退出返回 `None`；超时则取消提交任务并返回当时仍在运行的 Turn。"""
        self.begin_shutdown()
        try:
            await asyncio.wait_for(self._idle.wait(), timeout=timeout_ms / 1000)
        except TimeoutError:
            forced = tuple(self._live)
        else:
            return None

        tasks = tuple(self._submissions)
        for task in tasks:
            task.cancel()
        # 不等待可能吞掉 CancelledError 的第三方实现；让本事件循环轮转一次完成正常清理。
        if tasks:
            await asyncio.sleep(0)
        return forced
