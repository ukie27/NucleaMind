"""编排的装配面与产物：`OrchestratorDeps`、`TurnReceipt`、`EventTap`（技术方案 §10.2）。

职责：声明 orchestrator 需要哪些协作者、一次 `handle()` 交回什么，以及把
`before_model_request` 的分发时刻翻译成 `model.request_started` 的包装器。
不负责：任何流程（`orchestrator.py`）、任何 IO。

**与流程分成两个模块**有两个理由，都不是「文件太长」：`orchestrator.py` 的 ≤500 行是
技术方案 §6.2 写死的硬约束，而装配方（`D23` 的 wiring）只需要这里的三样东西、用不到编排
细节——让它 import 一个不含流程的模块，「谁依赖谁」在 import 清单上就是可读的。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final

from nucleamind.contracts import (
    EventName,
    HookContext,
    HookName,
    HookOutcome,
    InstanceId,
    ModelInfo,
    ModelProvider,
    NucleaError,
    OutboundMessage,
    SessionStore,
    StreamState,
    ToolSpec,
    TurnId,
    TurnOutcome,
)
from nucleamind.kernel.observability import EventBus
from nucleamind.kernel.routing import DedupCache, Dispatcher, SessionScheduler

from .context_builder import DEFAULT_CONTEXT_PROVIDER_TIMEOUT_MS, ContextProviderBinding
from .deps import HookDispatcher, ToolInvoker
from .limits import TurnLimits
from .transcript import TurnState

__all__ = ["EventTap", "OrchestratorDeps", "TurnReceipt", "emit_outbound", "utc_now"]

#: 契约要求 `DELTA` / `FINAL` 有正文；`CANCELLED` / `FAILED` 允许空正文，由 Channel 按
#: `EDG-304` 附加标记后呈现。空正文的前两种直接不发，而不是硬塞一个占位符。
_NEEDS_CONTENT: Final = (StreamState.DELTA, StreamState.FINAL)


def utc_now() -> datetime:
    """默认时钟。注入可替换——测试与重放都不该依赖真实墙钟。"""
    return datetime.now(UTC)


async def emit_outbound(
    state: TurnState,
    content: str,
    stream_state: StreamState,
    deliver: Callable[[OutboundMessage], Awaitable[None]] | None,
    *,
    reasoning: bool = False,
    final: bool = False,
) -> OutboundMessage | None:
    """产出并投递一条出站消息，返回它（不该发时返回 `None`）。

    寻址三件套（`channel_id` / `conversation_id` / `turn_id`）从 `Correlation` 取，
    Channel 因此不必维护自己的 Session 映射（`MSG-006`）；契约会当场校验它们与
    `session_key` 一致。
    """
    if not content and stream_state in _NEEDS_CONTENT:
        return None
    key = state.correlation.session_key
    message = OutboundMessage(
        session_key=key,
        channel_id=key.channel_id,
        conversation_id=key.conversation_id,
        turn_id=state.correlation.turn_id,
        content=content,
        stream_state=stream_state,
        metadata={"reasoning": True} if reasoning else {},
    )
    if not final:
        state.emitted.append(message)
    if deliver is not None:
        await deliver(message)
    return message


@dataclass(frozen=True, slots=True)
class TurnReceipt:
    """一次 `handle()` 的结论。

    `admitted=False` 覆盖两种情形：去重命中（`duplicate_of` 有值）与调度器拒绝
    （`error` 有值）。两者都没有 turn 终态，因此 `outcome` 为 `None`——用一个
    `TurnStatus` 硬凑会让「这次到底跑没跑」变得不可判定。
    """

    turn_id: TurnId
    admitted: bool
    outcome: TurnOutcome | None = None
    error: NucleaError | None = None
    duplicate_of: TurnId | None = None
    content: str = ""
    messages: tuple[OutboundMessage, ...] = ()


@dataclass(frozen=True, slots=True)
class OrchestratorDeps:
    """装配一次实例所需的全部协作者（`D23` 的 wiring 按这张表接线）。

    槽位比 `EngineDeps` 的四个多得多，这是分层的直接结果：engine 之所以能只有四个槽，
    正是因为「有状态、有 IO 的部分」全在这一层。
    """

    instance_id: InstanceId
    bus: EventBus
    sessions: SessionStore
    model: ModelProvider
    tools: ToolInvoker
    hooks: HookDispatcher
    dispatcher: Dispatcher
    scheduler: SessionScheduler[TurnReceipt]
    dedup: DedupCache
    limits: TurnLimits
    model_id: str
    tool_specs: tuple[ToolSpec, ...] = ()
    context_providers: tuple[ContextProviderBinding, ...] = ()
    model_info: ModelInfo | None = None
    stream: bool = True
    scope: str = "default"
    context_provider_timeout_ms: int = DEFAULT_CONTEXT_PROVIDER_TIMEOUT_MS
    deliver: Callable[[OutboundMessage], Awaitable[None]] | None = None
    clock: Callable[[], datetime] = utc_now


class EventTap:
    """包住 `HookDispatcher`，在 `before_model_request` 分发时补一条 `model.request_started`。

    engine 不发 `RuntimeEvent`，而「又要发一次模型请求」这件事只有它知道；它每轮分发这个
    Hook，正好是 orchestrator 唯一能观察到该时刻的位置。做成包装器而不是让 engine 拿一个
    bus，是为了不给 engine 开第二条对外通道——`EngineDeps` 只有四个槽的意义就在这里。
    """

    def __init__(self, inner: HookDispatcher, bus: EventBus) -> None:
        self._inner = inner
        self._bus = bus

    async def dispatch(self, context: HookContext) -> HookOutcome:
        if context.hook is HookName.BEFORE_MODEL_REQUEST and context.request is not None:
            self._bus.publish(
                EventName.MODEL_REQUEST_STARTED,
                correlation=context.correlation,
                payload={
                    "model_id": context.request.model_id,
                    "messages": len(context.request.messages),
                    "tools": len(context.request.tools),
                },
            )
        return await self._inner.dispatch(context)
