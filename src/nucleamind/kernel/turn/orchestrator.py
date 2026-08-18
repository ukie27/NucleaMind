"""Turn 编排：准入、组装、事件发布与持久化（技术方案 §6.2 第二层、§10.2、§10.3）。

职责：把一条 `InboundMessage` 走完 §10.2 的 14 步——去重、并发准入、命令分流、会话加载、
检查点 1/4、context 组装、驱动 `run_turn`、把引擎事件翻译成 `RuntimeEvent` 与
`OutboundMessage`、持久化、发布终态与 `turn_end`。它是 **turn 事件的唯一发布点**
（`KER-010`、`OBS-002`）。
不负责：模型-工具循环本身（`engine.py`）、Hook 归并（`hooks.py`）、片段裁剪
（`context_builder.py`）、工具执行（`invoker.py`）、事件名翻译（`translation.py`）、
判断该不该排队（`routing/`）。

**准入顺序是 去重 → 并发 → 分流**（`routing/__init__.py` 写死）：重复投递的消息不该占
队列名额，更不该在 `MERGE` 下被并进下一批（`EDG-201`）。

**MERGE 下整批归一个 turn**：被吸收的消息不产生自己的事件流——同一次执行在事件流里出现
N 份会让 `OBS-002` 的按序重放重复计数。它们的 `message_id` 记进执行 turn 的 `turn.started`
载荷（`merged_from`），而提交方本人拿到的 `TurnReceipt` 就是执行 turn 的那一份，
因此「我的消息去哪了」不需要再查一张映射表。

**命令类 turn 不写会话历史**：`/help` 的输出不是模型对话的一部分，写进去只会在下一轮占
预算。命令影响 turn 的正规路径是 `CommandResult.fragments`（`CMD-004`）。
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Sequence
from dataclasses import replace

from nucleamind.contracts import (
    CancelReason,
    Correlation,
    Disposition,
    ErrorCode,
    EventName,
    HookAction,
    HookContext,
    HookName,
    InboundMessage,
    ModelRequest,
    NucleaError,
    OutboundMessage,
    SessionKey,
    StreamState,
    TurnId,
    TurnOutcome,
)
from nucleamind.kernel.routing import SubmitStatus

from .cancel import CancelToken, Checkpoint
from .compaction import compact_once
from .context_builder import assemble
from .engine import run_turn
from .events import (
    ModelReasoningDelta,
    ModelResponseCompleted,
    ModelTextDelta,
    TerminalEvent,
    ToolCallCompleted,
    ToolCallStarted,
    TurnCompleted,
    TurnEvent,
    TurnStoppedByLimit,
)
from .finalization import finish_turn
from .limits import BudgetLedger
from .orchestration import OrchestratorDeps, TurnReceipt, emit_outbound, engine_deps
from .transcript import Transcript, TurnState
from .translation import (
    as_nuclea,
    outcome_for_error,
    outcome_from,
    outcome_without_engine,
    tool_event_name,
)

__all__ = ["TurnOrchestrator"]


class TurnOrchestrator:
    """§10.2 的执行者。一个实例一个，`handle()` 可被并发调用。"""

    def __init__(self, deps: OrchestratorDeps) -> None:
        self._deps = deps
        self._live: dict[TurnId, CancelToken] = {}

    @property
    def live_turns(self) -> tuple[TurnId, ...]:
        """当前在跑的 turn，`/cancel` 与实例停止时用。"""
        return tuple(self._live)

    def cancel(self, turn_id: TurnId, reason: CancelReason = CancelReason.USER) -> bool:
        """请求取消一个在跑的 turn（§10.3 的入口）。返回它是否还在跑。

        幂等：`CancelToken.request()` 第一次的原因胜出（`EDG-206`）。
        """
        token = self._live.get(turn_id)
        if token is None:
            return False
        token.request(reason)
        return True

    async def handle(self, message: InboundMessage) -> TurnReceipt:
        """走完一条入站消息的全流程。

        **异常约定**：turn 内部的异常一律折成 `TurnReceipt` 里的终态或错误（`CMD-003`：
        会话保持可用，进程不退出）；`BaseException` 穿透。
        **取消语义**：本次 turn 的令牌登记在 `live_turns`，由 `cancel()` 触发。
        """
        deps = self._deps
        key = message.session_key(deps.scope)
        turn_id = TurnId(uuid.uuid4().hex)

        hit = deps.dedup.remember(message.channel_id, message.message_id, turn_id)
        if hit is not None:
            deps.bus.publish(
                EventName.TURN_REJECTED,
                payload={
                    "reason": "duplicate",
                    "message_id": message.message_id,
                    "duplicate_of": hit.turn_id,
                },
            )
            return TurnReceipt(turn_id=hit.turn_id, admitted=False, duplicate_of=hit.turn_id)

        async def run(batch: tuple[InboundMessage, ...]) -> TurnReceipt:
            return await self._run(batch, key, turn_id)

        submitted = await deps.scheduler.submit(key, message, run, turn_id=turn_id)
        if submitted.status is SubmitStatus.REJECTED or submitted.result is None:
            error = submitted.error or NucleaError(
                ErrorCode.KERNEL_INVARIANT_VIOLATED, "调度器既没有结果也没有拒绝原因。"
            )
            deps.bus.publish(
                EventName.TURN_REJECTED,
                payload={"reason": "session_busy", "message_id": message.message_id},
                error=error,
            )
            return TurnReceipt(turn_id=turn_id, admitted=False, error=error)
        return submitted.result

    # ------------------------------------------------------------------ 一次 turn

    async def _run(
        self, batch: Sequence[InboundMessage], key: SessionKey, turn_id: TurnId
    ) -> TurnReceipt:
        """持有 session 槽位期间的全部工作。会话写入只发生在这里（单一写者）。"""
        deps = self._deps
        correlation = Correlation(instance_id=deps.instance_id, session_key=key, turn_id=turn_id)
        started_at = deps.clock()
        state = TurnState(
            correlation=correlation,
            started_at=started_at,
            transcript=Transcript(turn_id=turn_id, created_at=started_at, limits=deps.limits),
        )
        token = CancelToken()
        self._live[turn_id] = token
        try:
            deps.bus.publish(
                EventName.TURN_STARTED,
                correlation=correlation,
                payload={
                    "message_id": batch[0].message_id,
                    "channel_id": batch[0].channel_id,
                    "merged_from": [item.message_id for item in batch[1:]],
                },
            )
            return await self._execute(batch, key, state, token)
        # 捕 Exception 而不是 BaseException：`CancelledError` 是任务本身被杀，不是 turn
        # 被取消（engine 同一条理由）。检查点 1/4 抛出的取消也从这里落地——`outcome_for_error`
        # 按 `ErrorCategory` 把它翻成 `CANCELLED` 而不是 `FAILED`。
        except Exception as error:
            return await finish_turn(
                deps,
                state,
                outcome_for_error(
                    error,
                    correlation=correlation,
                    started_at=started_at,
                    finished_at=deps.clock(),
                    iterations=state.iterations,
                    tool_calls=state.tool_calls,
                ),
            )
        finally:
            self._live.pop(turn_id, None)

    async def _execute(
        self,
        batch: Sequence[InboundMessage],
        key: SessionKey,
        state: TurnState,
        token: CancelToken,
    ) -> TurnReceipt:
        """turn_start → 分流 → 会话 → context → engine → 终态。"""
        deps = self._deps
        rejected = await self._turn_start(batch[0], state)
        if rejected is not None:
            return rejected
        routed = await self._route(batch, state, token)
        if routed is not None:
            return routed
        if not state.model_inputs:
            # 命令类 turn：不进模型，但事件流与终态一个都不少（`KER-010`）。
            return await finish_turn(deps, state, self._outcome(state))

        snapshot = await deps.sessions.load(key)
        deps.bus.publish(
            EventName.SESSION_LOADED if snapshot.messages else EventName.SESSION_STARTED,
            correlation=state.correlation,
            payload={"messages": len(snapshot.messages)},
        )

        token.checkpoint(Checkpoint.BEFORE_CONTEXT)  # 检查点 1
        user_input = "\n\n".join(state.model_inputs)
        context = await assemble(
            snapshot=snapshot,
            user_input=user_input,
            correlation=state.correlation,
            cancel=token,
            limits=deps.limits,
            bindings=deps.context_providers,
            extra_fragments=state.fragments,
            memory=deps.memory,
            hooks=deps.hooks,
            model_info=deps.model_info,
            now=deps.clock(),
            provider_timeout_ms=deps.context_provider_timeout_ms,
            on_failure=lambda error: self._report(state, error),
        )
        compacted = await compact_once(
            snapshot=snapshot,
            assembled=context,
            user_input=user_input,
            correlation=state.correlation,
            cancel=token,
            sessions=deps.sessions,
            policy=deps.compactor,
            now=deps.clock(),
            on_failure=lambda error: self._report(state, error),
        )
        if compacted is not None:
            deps.bus.publish(
                EventName.SESSION_COMPACTED,
                correlation=state.correlation,
                payload={
                    "through": compacted.through,
                    "messages": len(compacted.snapshot.messages),
                    "compactor": deps.compactor.name if deps.compactor is not None else None,
                },
            )
            context = await assemble(
                snapshot=compacted.snapshot,
                user_input=user_input,
                correlation=state.correlation,
                cancel=token,
                limits=deps.limits,
                bindings=deps.context_providers,
                extra_fragments=state.fragments,
                memory=deps.memory,
                hooks=deps.hooks,
                model_info=deps.model_info,
                now=deps.clock(),
                provider_timeout_ms=deps.context_provider_timeout_ms,
                on_failure=lambda error: self._report(state, error),
            )
        state.transcript.add_inputs(batch)

        request = ModelRequest(
            model_id=deps.model_id,
            messages=context.messages,
            correlation=state.correlation,
            tools=deps.tool_specs,
            stream=deps.stream,
            timeout_ms=deps.limits.turn_timeout_ms,
        )
        terminal = await self._drive(request, state, token)
        if isinstance(terminal, TurnCompleted) and terminal.truncated:
            state.truncated = True
        if isinstance(terminal, TurnStoppedByLimit):
            await self._wrap_up(request, state, token, terminal)
        return await finish_turn(
            deps,
            state,
            outcome_from(
                terminal,
                correlation=state.correlation,
                started_at=state.started_at,
                finished_at=deps.clock(),
            ),
        )

    async def _turn_start(self, message: InboundMessage, state: TurnState) -> TurnReceipt | None:
        """`turn_start` 拦截器。`REJECT` 即本 turn 到此为止（§6.6）。"""
        outcome = await self._deps.hooks.dispatch(
            HookContext(HookName.TURN_START, correlation=state.correlation, message=message)
        )
        if outcome.action is not HookAction.REJECT:
            return None
        error = NucleaError(
            ErrorCode.PERMISSION_TURN_REJECTED,
            outcome.reason,
            detail={"hook": HookName.TURN_START.value},
        )
        self._deps.bus.publish(
            EventName.TURN_REJECTED,
            correlation=state.correlation,
            payload={"reason": "hook"},
            error=error,
        )
        return await finish_turn(self._deps, state, self._outcome(state, error))

    async def _route(
        self, batch: Sequence[InboundMessage], state: TurnState, token: CancelToken
    ) -> TurnReceipt | None:
        """逐条分流（§6.3）。返回非 `None` 表示这一批到此为止。

        **逐条而不是只看第一条**：`MERGE` 下的第二条消息也可能是命令，只看第一条会让它
        静默变成模型输入。被拒的那条让整批终止——`CMD-003` 要的是可诊断。
        """
        for message in batch:
            outcome = await self._deps.dispatcher.dispatch(message, state.correlation, token)
            if outcome.disposition is Disposition.REJECTED:
                error = outcome.error or NucleaError(
                    ErrorCode.KERNEL_INVARIANT_VIOLATED, "分流拒绝了输入却没有给出原因。"
                )
                self._deps.bus.publish(
                    EventName.TURN_REJECTED,
                    correlation=state.correlation,
                    payload={"reason": "command", "message_id": message.message_id},
                    error=error,
                )
                return await finish_turn(self._deps, state, self._outcome(state, error))
            if outcome.result is not None:
                state.fragments.extend(outcome.result.fragments)
                if outcome.result.content:
                    state.text.append(outcome.result.content)
            if outcome.disposition is not Disposition.COMMAND_HANDLED and outcome.model_input:
                state.model_inputs.append(outcome.model_input)
        return None

    # ------------------------------------------------------------------ engine

    async def _drive(
        self, request: ModelRequest, state: TurnState, token: CancelToken
    ) -> TerminalEvent:
        """驱动 engine 并翻译事件流，返回终态事件。"""
        deps = self._deps
        state.ledger = BudgetLedger(deps.limits)
        engine = engine_deps(deps, state.ledger)
        watchdog = asyncio.ensure_future(self._watchdog(token, deps.limits.turn_timeout_ms))
        terminal: TurnEvent | None = None
        try:
            async for event in run_turn(request, engine, token, ledger=state.ledger):
                terminal = event
                await self._on_event(event, state, token)
        finally:
            watchdog.cancel()
            await asyncio.gather(watchdog, return_exceptions=True)
        if not isinstance(terminal, TerminalEvent):
            raise NucleaError(
                ErrorCode.KERNEL_INVARIANT_VIOLATED,
                "引擎事件流没有以终态事件结尾。",
                detail={"event": type(terminal).__name__},
            )
        return terminal

    async def _on_event(self, event: TurnEvent, state: TurnState, token: CancelToken) -> None:
        """一个引擎事件的全部去向：出站、事件、待持久化内容。"""
        deps = self._deps
        match event:
            case ModelTextDelta():
                state.text.append(event.text)
                state.pending.append(event.text)
                await self._emit(state, event.text, StreamState.DELTA)
            case ModelReasoningDelta():
                await self._emit(state, event.text, StreamState.DELTA, reasoning=True)
            case ModelResponseCompleted():
                token.checkpoint(Checkpoint.AFTER_MODEL_RESPONSE)  # 检查点 4
                deps.bus.publish(
                    EventName.MODEL_RESPONSE_RECEIVED,
                    correlation=state.correlation,
                    payload={
                        "iteration": event.iteration,
                        "stop_reason": event.response.stop_reason.value,
                        "tool_calls": len(event.response.tool_calls),
                        # 用量的唯一公开出口（`TurnOutcome` / `TurnReceipt` 都不带它）。
                        # 复数键名让脱敏的整词规则原样放行（`D02`）。
                        "input_tokens": event.response.usage.input_tokens,
                        "output_tokens": event.response.usage.output_tokens,
                    },
                )
                # 这一轮的正文已由响应对象权威记过一次，分片账本清零；剩下的就是
                # 「最后一次完整响应之后又流出来的半句」，取消时靠它落库（`KER-007`）。
                state.pending.clear()
                state.transcript.declare(event.response.tool_calls)
                if event.response.tool_calls:
                    state.transcript.add_assistant(event.response.content)
                else:
                    # 多次续写属于同一份回答；终帧与会话历史保留拼接后的正文。
                    state.final += event.response.content
            case ToolCallStarted():
                deps.bus.publish(
                    EventName.TOOL_CALL_STARTED,
                    correlation=state.correlation,
                    payload={"tool": event.call.name, "call_id": event.call.call_id},
                )
            case ToolCallCompleted():
                state.transcript.add_tool_result(event.result)
                state.collect_attachments(event.result)
                deps.bus.publish(
                    tool_event_name(event),
                    correlation=state.correlation,
                    payload={
                        "tool": event.call.name,
                        "call_id": event.call.call_id,
                        "disposition": event.disposition.value,
                        "side_effect": event.result.side_effect.value,
                        "truncated": event.result.truncated,
                    },
                    error=event.result.error,
                )
            case _:
                pass  # 终态事件由 `_drive` 的返回值承担，不在这里重复处理

    async def _watchdog(self, token: CancelToken, timeout_ms: int) -> None:
        """turn 总超时（§6.4）。engine 只在迭代边界查预算，挂住的模型调用要外部叫停。"""
        await asyncio.sleep(timeout_ms / 1000)
        token.request(CancelReason.TIMEOUT)

    async def _wrap_up(
        self,
        request: ModelRequest,
        state: TurnState,
        token: CancelToken,
        terminal: TurnStoppedByLimit,
    ) -> None:
        """预算用尽后的收尾请求：同一批消息、**不带 tools**、不流式。

        engine 撞上限即停、不替模型收尾（§6.2.1），但让用户面对一张空卡片同样不可接受
        （基线 `test_budget_exhaustion_is_pushed_through_the_stream`）。收尾失败就算了：
        终态已经是 `STOPPED_BY_LIMIT`，再失败一次不改变结论，只多一条诊断。

        **它走的是没包重试的 `deps.model`**（`D48`）：终态已经定了，为一条注定不改变结论
        的请求重试只会把一个已经确定的 turn 再拖几秒。
        """
        try:
            response = await self._deps.model.complete(
                replace(request, tools=(), stream=False), token
            )
        except Exception as error:
            self._report(state, as_nuclea(error))
            response = None
        if response is not None and response.content:
            state.final = response.content
        if not state.final and not state.text:
            state.final = terminal.breach.describe()

    async def _emit(
        self,
        state: TurnState,
        content: str,
        stream_state: StreamState,
        *,
        reasoning: bool = False,
        final: bool = False,
    ) -> OutboundMessage | None:
        """`emit_outbound` 的唯一调用点。存在的理由只有一个：注入 `deps.deliver`。"""
        return await emit_outbound(
            state, content, stream_state, self._deps.deliver, reasoning=reasoning, final=final
        )

    def _report(self, state: TurnState, error: NucleaError) -> None:
        """非致命失败的统一去向：一条 `plugin.failed`，turn 继续（`NFR-204`）。"""
        self._deps.bus.publish(
            EventName.PLUGIN_FAILED, correlation=state.correlation, error=error
        )

    def _outcome(self, state: TurnState, error: NucleaError | None = None) -> TurnOutcome:
        return outcome_without_engine(
            correlation=state.correlation,
            started_at=state.started_at,
            finished_at=self._deps.clock(),
            error=error,
        )
