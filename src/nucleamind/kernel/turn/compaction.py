"""插件化上下文压缩的触发、校验、持久化与回退（D51）。

职责：在历史被请求级裁剪后调用显式选中的 Compactor，校验结果并原子推进 Session 水位。
不负责：组装模型上下文、选择 Compactor、重载后再次组装或发布运行时事件。
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from nucleamind.contracts import (
    CancelSignal,
    CapabilityKind,
    CapabilityRef,
    CompactionRequest,
    CompactionResult,
    ContextCompactor,
    Correlation,
    ErrorCode,
    NucleaError,
    ProviderId,
    Role,
    SessionMessage,
    SessionSnapshot,
    SessionStore,
)

from .context_builder import AssembledContext

__all__ = [
    "DEFAULT_COMPACTOR_TIMEOUT_MS",
    "CompactionApplied",
    "CompactionPolicy",
    "compact_once",
]

DEFAULT_COMPACTOR_TIMEOUT_MS: Final = 3_000


@dataclass(frozen=True, slots=True)
class CompactionPolicy:
    """显式选中的压缩能力及其调用预算。"""

    compactor: ContextCompactor
    name: str
    owner: ProviderId
    timeout_ms: int = DEFAULT_COMPACTOR_TIMEOUT_MS

    @property
    def ref(self) -> CapabilityRef:
        return CapabilityRef(kind=CapabilityKind.COMPACTOR, name=self.name, provider=self.owner)


@dataclass(frozen=True, slots=True)
class CompactionApplied:
    """一次成功持久化后的新快照与水位。"""

    snapshot: SessionSnapshot
    through: int


async def compact_once(
    *,
    snapshot: SessionSnapshot,
    assembled: AssembledContext,
    user_input: str,
    correlation: Correlation,
    cancel: CancelSignal,
    sessions: SessionStore,
    policy: CompactionPolicy | None,
    now: datetime,
    on_failure: Callable[[NucleaError], None] | None = None,
) -> CompactionApplied | None:
    """历史被裁时至多尝试一次持久化压缩；任何插件侧失败都回退到首次组装结果。"""
    if policy is None or assembled.history_dropped == 0:
        return None
    request = CompactionRequest(
        snapshot=snapshot,
        target_tokens=assembled.budget,
        correlation=correlation,
        user_input=user_input,
    )
    try:
        result = await asyncio.wait_for(
            policy.compactor.compact(request, cancel),
            timeout=policy.timeout_ms / 1000,
        )
    except Exception as error:
        _report(on_failure, _compactor_error(policy, error))
        return None
    if result is None:
        return None
    problem = _validate_result(snapshot, assembled.history_dropped, result, policy)
    if problem is not None:
        _report(on_failure, problem)
        return None

    summary = SessionMessage(
        message_id=f"compaction-{correlation.turn_id}",
        role=Role.SYSTEM,
        content=result.content.strip(),
        created_at=now,
        turn_id=correlation.turn_id,
        metadata={"compactor": policy.name, "provider": str(policy.owner)},
    )
    await sessions.compact(snapshot.session_key, result.through, summary)
    return CompactionApplied(snapshot=await sessions.load(snapshot.session_key), through=result.through)


def _validate_result(
    snapshot: SessionSnapshot,
    history_dropped: int,
    result: CompactionResult,
    policy: CompactionPolicy,
) -> NucleaError | None:
    minimum = _minimum_through(snapshot, history_dropped)
    if (
        result.through <= snapshot.compacted_through
        or result.through > len(snapshot.messages)
        or result.through < minimum
        or not result.content.strip()
    ):
        return NucleaError(
            ErrorCode.PLUGIN_HOOK_FAILED,
            "Context Compactor 返回了非法结果。",
            detail={
                "through": result.through,
                "minimum_through": minimum,
                "compacted_through": snapshot.compacted_through,
                "messages": len(snapshot.messages),
                "empty_content": not bool(result.content.strip()),
            },
            capability=policy.ref,
        )
    return None


def _minimum_through(snapshot: SessionSnapshot, history_dropped: int) -> int:
    """把被裁掉的可重放消息数映射回 SessionStore 使用的绝对记录水位。"""
    remaining = history_dropped
    for index in range(snapshot.compacted_through, len(snapshot.messages)):
        message = snapshot.messages[index]
        if message.role is not Role.TOOL and message.content:
            remaining -= 1
            if remaining == 0:
                return index + 1
    return len(snapshot.messages) + 1


def _compactor_error(policy: CompactionPolicy, error: Exception) -> NucleaError:
    if isinstance(error, TimeoutError):
        return NucleaError(
            ErrorCode.TIMEOUT_HOOK,
            "Context Compactor 超时。",
            detail={"timeout_ms": policy.timeout_ms},
            capability=policy.ref,
        )
    return NucleaError(
        ErrorCode.PLUGIN_HOOK_FAILED,
        "Context Compactor 抛出了异常。",
        detail={"exception": type(error).__name__},
        capability=policy.ref,
    )


def _report(callback: Callable[[NucleaError], None] | None, error: NucleaError) -> None:
    if callback is not None:
        callback(error)
