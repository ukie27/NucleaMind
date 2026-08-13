"""`AgentInstance`：一个已装好的实例的运行与停止（技术方案 §10.1 步骤 9–10、§10.3）。

职责：启动长生命周期服务（Channel + 每个 Channel 的入站泵）、把出站消息路由回对应
Channel、跑 CLI 入口、按相反顺序停止一切并释放实例锁。
不负责：装配它（`bootstrap.py`）、解析配置（`kernel/config/`）、执行 turn
（`kernel/turn/`）、解析 argv（`runtime/cli/`）。

**Channel 泵是「CLI 也是 Channel」这条设计的兑现点**：入站消息从
`channel.receive()` 来、经 `orchestrator.handle()`、出站经 `deliver` 路由回
`channel.deliver()`。CLI 与未来任何平台走的是同一段代码，没有第二条路径（`MSG-007`）。

**被拒的 turn 也要有回音**：去重命中或队列拒绝时 `TurnReceipt.admitted=False`，
orchestrator 不会发终态出站消息（那条 turn 从未开始）。泵因此自己合成一条
`stream_state=FAILED` 的出站消息——否则 CLI 会永远等一个不会到来的终态。
合成的仍是 `OutboundMessage`，不是绕过契约的旁路。
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field

from nucleamind.contracts import (
    CancelSignal,
    Channel,
    CliEntry,
    ErrorCode,
    EventName,
    HookContext,
    HookName,
    InboundMessage,
    InstanceId,
    NucleaError,
    OutboundMessage,
    SessionKey,
    StreamState,
    TurnId,
)
from nucleamind.kernel.config import InstanceLayout, InstanceLock, LoadedConfig
from nucleamind.kernel.observability import Diagnostics, EventBus
from nucleamind.kernel.plugins import LoadOutcome
from nucleamind.kernel.registry import CapabilityRegistry, ResolutionReport
from nucleamind.kernel.turn import OrchestratorDeps, TurnOrchestrator, TurnReceipt

from .plugin_context import PluginRuntime, RuntimePluginContext

#: `TurnReceipt` 从这里再导出一次：`embed/` 只能 import `contracts/` 与 `runtime/`（`R5`），
#: 而一次 `submit()` 的返回值类型在 `kernel/turn/`。转发比让门面用 `object` 诚实得多。
__all__ = ["AgentInstance", "Closer", "TurnReceipt"]

#: 停止时要跑的一件收尾事。用 callable 而不是一张「谁要关」的类型表：
#: 模型的 `aclose()`、sink 的 `close()` 与锁的 `release()` 没有共同接口，
#: 为它们发明一个只会多出一层。
Closer = Callable[[], Awaitable[None]]


@dataclass(slots=True)
class AgentInstance:
    """一个装好的实例。`bootstrap()` 是它唯一的构造者。"""

    instance_id: InstanceId
    layout: InstanceLayout
    config: LoadedConfig
    bus: EventBus
    diagnostics: Diagnostics
    registry: CapabilityRegistry
    report: ResolutionReport
    deps: OrchestratorDeps
    orchestrator: TurnOrchestrator
    cli_entry: CliEntry
    channels: tuple[tuple[str, Channel], ...] = ()
    outcomes: tuple[LoadOutcome, ...] = ()
    contexts: tuple[RuntimePluginContext, ...] = ()
    runtime: PluginRuntime = field(default_factory=PluginRuntime)
    lock: InstanceLock | None = None
    closers: tuple[Closer, ...] = ()
    _pumps: list[asyncio.Task[None]] = field(default_factory=list, init=False)
    _started: bool = field(default=False, init=False)
    _stopped: bool = field(default=False, init=False)

    # ------------------------------------------------------------------ 生命周期

    async def start(self) -> None:
        """阶段 D：启动 Channel 并派生入站泵，随后发 `instance.ready`（§10.1 步骤 9–10）。"""
        if self._started:
            return
        self._started = True
        for channel_id, channel in self.channels:
            await channel.start()
            self._pumps.append(
                asyncio.create_task(self._pump(channel), name=f"pump:{channel_id}")
            )
        await self.deps.hooks.dispatch(HookContext(HookName.INSTANCE_READY))
        self.bus.publish(
            EventName.INSTANCE_READY,
            payload={
                "channels": [channel_id for channel_id, _ in self.channels],
                "capabilities": len(self.report.active),
            },
        )

    async def run_cli(self, argv: Sequence[str], cancel: CancelSignal) -> int:
        """跑内建（或覆盖了它的）CLI 入口。**它拥有进程**，返回值即退出码。"""
        if not self._started:
            await self.start()
        return await self.cli_entry.run(argv, cancel)

    async def submit(self, message: InboundMessage) -> TurnReceipt:
        """直接投一条入站消息（`embed/` 与测试用）。

        **不是绕过 Channel 的近路**：它走的是 `orchestrator.handle()`，与泵完全同一个
        入口，只是消息不从某个平台来。出站消息按同一条 `deliver` 路由。
        """
        return await self.orchestrator.handle(message)

    async def stop(self) -> None:
        """按相反顺序停止。**约定不抛**：一条失败的收尾不该盖住其余收尾。"""
        if self._stopped:
            return
        self._stopped = True
        self.bus.publish(EventName.INSTANCE_STOPPING)
        await self._safe(self.deps.hooks.dispatch(HookContext(HookName.INSTANCE_SHUTDOWN)))

        for _, channel in self.channels:
            await self._safe(channel.stop())
        for pump in self._pumps:
            pump.cancel()
        if self._pumps:
            await asyncio.gather(*self._pumps, return_exceptions=True)
        self._pumps.clear()

        # 插件派生的后台任务与事件桥（`EDG-104`、`EDG-105`）：先取消，再等一轮回收。
        pending: list[asyncio.Task[None]] = []
        for ctx in self.contexts:
            pending.extend(ctx.tasks)
            pending.extend(ctx.bridge.tasks)
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

        self.bus.publish(EventName.INSTANCE_STOPPED)
        for closer in self.closers:
            await self._safe(closer())
        if self.lock is not None:
            self.lock.release()

    # ------------------------------------------------------------------ 内部

    async def _pump(self, channel: Channel) -> None:
        """一条 Channel 的入站泵。`receive()` 结束即泵结束。"""
        async for message in channel.receive():
            try:
                receipt = await self.orchestrator.handle(message)
            except Exception as exc:  # noqa: BLE001 - 泵不能因为一条消息而死掉
                self.bus.publish(EventName.PLUGIN_FAILED, error=_as_nuclea(exc))
                continue
            if not receipt.admitted:
                await self._safe(channel.deliver(_rejection(message, receipt)))

    async def _safe(self, awaitable: Awaitable[object]) -> None:
        """跑一件收尾/投递，异常只记不抛（`NFR-204`）。`BaseException` 放行。"""
        try:
            await awaitable
        except Exception as exc:  # noqa: BLE001 - 见 docstring
            self.bus.publish(EventName.PLUGIN_FAILED, error=_as_nuclea(exc))


def _as_nuclea(exc: Exception) -> NucleaError:
    """折成 `NucleaError`。**只放类型名不放异常消息**——第三方实现的异常文本可能带凭据
    （`D13` 的先例）。"""
    if isinstance(exc, NucleaError):
        return exc
    return NucleaError(
        ErrorCode.KERNEL_UNEXPECTED,
        "实例运行期出现未预期异常。",
        detail={"exception": type(exc).__name__},
    )


def _rejection(message: InboundMessage, receipt: TurnReceipt) -> OutboundMessage:
    """给一条未被准入的消息合成回音。

    去重命中时说清楚指向哪个 turn——「什么也没发生」和「这条我上次已经答过了」是两个
    不同的结论（`EDG-201`）。
    """
    if receipt.duplicate_of is not None:
        content = f"[重复投递，已忽略；上一次是 turn {receipt.duplicate_of}]"
    elif receipt.error is not None:
        content = f"[未受理：{receipt.error.user_message}]"
    else:
        content = "[未受理]"
    key = SessionKey(
        channel_id=message.channel_id,
        conversation_id=message.conversation_id,
    )
    return OutboundMessage(
        session_key=key,
        channel_id=key.channel_id,
        conversation_id=key.conversation_id,
        turn_id=TurnId(str(receipt.turn_id)),
        content=content,
        stream_state=StreamState.FAILED,
    )
