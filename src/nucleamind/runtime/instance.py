"""`AgentInstance`：一个已装好的实例的运行与停止（技术方案 §10.1 步骤 9–10、§10.3）。

职责：启动长生命周期服务（Channel + 每个 Channel 的入站泵）、把出站消息路由回对应
Channel、跑 CLI 入口、按相反顺序停止一切并释放实例锁。
不负责：装配它（`bootstrap.py`）、解析配置（`kernel/config/`）、执行 turn
（`kernel/turn/`）、解析 argv（`runtime/cli/`）。

**Channel 泵是「CLI 也是 Channel」这条设计的兑现点**：入站消息从
`channel.receive()` 来、经 `orchestrator.handle()`、出站经 `deliver` 路由回
`channel.deliver()`。CLI 与未来任何平台走的是同一段代码，没有第二条路径（`MSG-007`）。

**泵按 conversation 扇出**（`D33`）：机制在 `kernel/routing/fanout.py`，这里只负责接线。
同一 conversation 内严格按到达顺序串行（`EDG-202` 因此逐字成立——在一条 Channel 上
`conversation_id ↔ SessionKey` 是双射），跨 conversation 并发。在此之前一条 Channel
同时只跑一条 turn，一个用户的慢 turn 会卡住同一个 bot 上所有人。

**被拒的 turn 也要有回音**：去重命中或队列拒绝时 `TurnReceipt.admitted=False`，
orchestrator 不会发终态出站消息（那条 turn 从未开始）。泵因此自己合成一条
`stream_state=FAILED` 的出站消息——否则 CLI 会永远等一个不会到来的终态。
合成的仍是 `OutboundMessage`，不是绕过契约的旁路。**扇出层的拒绝走同一条合成路径**，
只是那条消息连 orchestrator 都没进过，因此发的是 `instance.input_dropped` 而不是
turn 事件。
"""

from __future__ import annotations

import asyncio
import uuid
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
from nucleamind.kernel.plugins import (
    DEFAULT_STOP_TIMEOUT_MS,
    LoadOutcome,
    PluginLifecycle,
    PluginPhase,
    StopAction,
    stop_plugins,
    units_for,
)
from nucleamind.kernel.registry import CapabilityRegistry, ResolutionReport
from nucleamind.kernel.routing import (
    DEFAULT_CHANNEL_CONCURRENCY,
    DEFAULT_CHANNEL_QUEUE_MAX_SIZE,
    ConversationFanout,
)
from nucleamind.kernel.turn import (
    OrchestratorDeps,
    ToolExecutor,
    TurnOrchestrator,
    TurnReceipt,
)

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
    #: 每个提供方的生命周期，与 `contexts` 同序（`D28`）。装配根按加载结果把它们置于
    #: `LOADED` 或 `FAILED`；`start()` / `stop()` 在这里继续推进。
    lifecycles: tuple[PluginLifecycle, ...] = ()
    #: 单个插件的停止预算（配置 `plugins.stop_timeout_ms`，`EDG-104`）。
    stop_timeout_ms: int = DEFAULT_STOP_TIMEOUT_MS
    #: Channel 泵的扇出上界（配置 `routing.channel_*`，`D33`）。
    channel_concurrency: int = DEFAULT_CHANNEL_CONCURRENCY
    channel_queue_max_size: int = DEFAULT_CHANNEL_QUEUE_MAX_SIZE
    runtime: PluginRuntime = field(default_factory=PluginRuntime)
    lock: InstanceLock | None = None
    closers: tuple[Closer, ...] = ()
    _pumps: list[asyncio.Task[None]] = field(default_factory=list, init=False)
    _fanouts: list[ConversationFanout] = field(default_factory=list, init=False)
    _started: bool = field(default=False, init=False)
    _stopped: bool = field(default=False, init=False)

    # ------------------------------------------------------------------ 生命周期

    async def start(self) -> None:
        """阶段 D：启动 Channel 并派生入站泵，随后发 `instance.ready`（§10.1 步骤 9–10）。"""
        if self._started:
            return
        self._started = True
        for lifecycle in self.lifecycles:
            # 加载失败的提供方留在 `FAILED`——它没有被启动，说它 `STARTED` 会让停止流程
            # 与诊断都相信有东西在跑。
            if lifecycle.phase is PluginPhase.LOADED:
                lifecycle.advance(PluginPhase.STARTED)
        for channel_id, channel in self.channels:
            await channel.start()
            fanout = self._fanout_for(channel)
            self._fanouts.append(fanout)
            self._pumps.append(
                asyncio.create_task(fanout.run(channel.receive()), name=f"pump:{channel_id}")
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
        self._report_orphans()
        await self._safe(self.deps.hooks.dispatch(HookContext(HookName.INSTANCE_SHUTDOWN)))

        for _, channel in self.channels:
            await self._safe(channel.stop())
        for pump in self._pumps:
            pump.cancel()
        if self._pumps:
            await asyncio.gather(*self._pumps, return_exceptions=True)
        self._pumps.clear()
        # 顺序不能反：先停泵再排干 lane。反过来泵会在 lane 已经被清掉之后再建一条新的。
        for fanout in self._fanouts:
            await fanout.drain(cancel=True)
        self._fanouts.clear()

        # 插件的停止（`D28`）：逆加载序、逐个、各有独立超时（`PLG-005`、`EDG-104`）。
        await self._stop_plugins()

        self.bus.publish(EventName.INSTANCE_STOPPED)
        for closer in self.closers:
            await self._safe(closer())
        if self.lock is not None:
            self.lock.release()

    # ------------------------------------------------------------------ 内部

    async def _stop_plugins(self) -> None:
        """按逆加载序停掉每个提供方，并把结果发成事件（`D28`）。

        **停止顺序不在这里算**（`PLG-005`）：`contexts` 是装配根按 `wire_all()` 的
        manifest 顺序追加的，而那个顺序对外部插件就是 `LoadPlan.order`（内建在前）。
        `units_for()` 把它翻过来，因此「被依赖者后停」与「被依赖者先起」共用同一个序，
        没有第二次拓扑排序。

        每个插件各有独立超时：一个停不下来的插件只让自己记一条
        `TIMEOUT_PLUGIN_STOP`，不会连累后面的插件或扣住进程退出（`EDG-104`）。
        """
        actions: dict[str, StopAction] = {ctx.plugin_id: ctx.shutdown for ctx in self.contexts}
        units = units_for(
            tuple(ctx.plugin_id for ctx in self.contexts),
            actions,
            {lifecycle.plugin_id: lifecycle for lifecycle in self.lifecycles},
        )
        for outcome in await stop_plugins(units, timeout_ms=self.stop_timeout_ms):
            if outcome.error is None:
                self.bus.publish(
                    EventName.PLUGIN_DEACTIVATED, payload={"plugin": outcome.plugin_id}
                )
                continue
            self.bus.publish(
                EventName.PLUGIN_FAILED,
                payload={"plugin": outcome.plugin_id, "timed_out": outcome.timed_out},
                error=outcome.error,
            )

    def _report_orphans(self) -> None:
        """停止时报告孤儿工具任务（`EDG-104`，`D14` 留下的那条）。

        孤儿是「超时后连宽限期都没等回来」的工具调用，它的副作用是 `UNKNOWN`。实例正在
        关闭，这是最后一个能说出「有几次调用可能还在改外部世界」的时刻——不说，那条信息
        就随进程一起没了。**没有孤儿时不发事件**：一条恒定出现的 `0` 只会让真正有孤儿的
        那次淹在噪声里。

        `dropped` 一并报出：「表里没有」与「被挤掉了」是两个不同的结论（`invoker.py`）。

        **`isinstance` 是必要的**：`OrchestratorDeps.tools` 的类型是 `ToolInvoker`，而孤儿表
        不在那个协议里——第三方执行器可以完全没有这个概念。给协议加一个成员会逼每个实现
        都编一张空表出来，那比这里少报一次更糟。
        """
        executor = self.deps.tools
        if not isinstance(executor, ToolExecutor):
            return
        orphans = executor.orphans
        dropped = executor.orphans_dropped
        if not orphans and not dropped:
            return
        self.bus.publish(
            EventName.PLUGIN_FAILED,
            payload={
                "reason": "tool_orphans",
                "count": len(orphans),
                "dropped": dropped,
                "orphans": [
                    {
                        "tool": task.tool,
                        "call_id": task.call_id,
                        "turn_id": task.turn_id,
                        "grace_ms": task.grace_ms,
                    }
                    for task in orphans
                ],
            },
        )

    def _fanout_for(self, channel: Channel) -> ConversationFanout:
        """给一条 Channel 建扇出。

        `handle` 做的事与串行泵时代的循环体**逐字相同**——那是这次改动没有顺手改别的
        东西的证据；变的只是「谁在什么时候调它」。
        """

        async def handle(message: InboundMessage) -> None:
            receipt = await self.orchestrator.handle(message)
            if not receipt.admitted:
                await self._safe(channel.deliver(_rejection(message, receipt)))

        async def dropped(message: InboundMessage, error: NucleaError) -> None:
            await self._dropped(channel, message, error)

        return ConversationFanout(
            handle,
            on_failure=self._pump_failure,
            on_dropped=dropped,
            concurrency=self.channel_concurrency,
            queue_max_size=self.channel_queue_max_size,
        )

    def _pump_failure(self, exc: Exception) -> None:
        """一条消息在 lane 里炸掉。只记不抛——泵与 lane 都不能因为一条消息而死掉。"""
        self.bus.publish(EventName.PLUGIN_FAILED, error=_as_nuclea(exc))

    async def _dropped(
        self, channel: Channel, message: InboundMessage, error: NucleaError
    ) -> None:
        """一条消息在**进 orchestrator 之前**就被扇出拒了（lane 队列或并发上界满）。

        给它铸一个 `turn_id` 再走 `_rejection()`：`orchestrator.handle()` 被 scheduler
        拒绝时做的正是同一件事，用户拿到的因此仍是 `[未受理：…]` + `FAILED`，两条背压
        路径在 Channel 侧长得一模一样。

        **发的是 `instance.input_dropped` 而不是 `turn.rejected`**：这条消息从未进过
        orchestrator，而 turn 事件只有那一个发布点。理由写在 `contracts/events.py`。
        """
        receipt = TurnReceipt(turn_id=TurnId(uuid.uuid4().hex), admitted=False, error=error)
        await self._safe(channel.deliver(_rejection(message, receipt)))
        self.bus.publish(
            EventName.INSTANCE_INPUT_DROPPED,
            payload={
                "channel": message.channel_id,
                "conversation": message.conversation_id,
            },
            error=error,
        )

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
