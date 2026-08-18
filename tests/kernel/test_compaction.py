"""D51 上下文压缩机制：触发、校验、持久化与失败回退。"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from nucleamind.contracts import (
    Builtin,
    CompactionRequest,
    CompactionResult,
    ErrorCode,
    NucleaError,
    Role,
    SessionMessage,
    SessionSnapshot,
)
from nucleamind.kernel.turn import (
    AssembledContext,
    CancelToken,
    CompactionPolicy,
    compact_once,
)

from ._engine_support import CORRELATION
from ._orchestrator_support import FakeSessionStore

NOW = datetime(2026, 8, 18, tzinfo=UTC)


def record(role: Role, content: str, index: int, *, tool_call_id: str | None = None) -> SessionMessage:
    return SessionMessage(
        message_id=f"m{index}",
        role=role,
        content=content,
        created_at=NOW,
        tool_call_id=tool_call_id,
    )


def assembled(history_dropped: int) -> AssembledContext:
    return AssembledContext(
        messages=(),
        fragments=(),
        dropped=(),
        estimated_tokens=8,
        budget=32,
        history_dropped=history_dropped,
    )


class RecordingCompactor:
    def __init__(
        self,
        result: CompactionResult | None = None,
        *,
        error: Exception | None = None,
        hang: bool = False,
    ) -> None:
        self.result = result
        self.error = error
        self.hang = hang
        self.requests: list[CompactionRequest] = []

    async def compact(self, request, cancel):  # noqa: ANN001, ANN202
        del cancel
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        if self.hang:
            await asyncio.Event().wait()
        return self.result


def policy(compactor: RecordingCompactor, *, timeout_ms: int = 3_000) -> CompactionPolicy:
    return CompactionPolicy(
        compactor=compactor,
        name="summary",
        owner=Builtin(),
        timeout_ms=timeout_ms,
    )


async def run(
    snapshot: SessionSnapshot,
    context: AssembledContext,
    compactor: CompactionPolicy | None,
    store: FakeSessionStore,
    failures: list[NucleaError] | None = None,
):
    return await compact_once(
        snapshot=snapshot,
        assembled=context,
        user_input="当前问题",
        correlation=CORRELATION,
        cancel=CancelToken(),
        sessions=store,  # type: ignore[arg-type]
        policy=compactor,
        now=NOW,
        on_failure=None if failures is None else failures.append,
    )


def history_snapshot(*messages: SessionMessage, compacted_through: int = 0) -> SessionSnapshot:
    return SessionSnapshot(
        session_key=CORRELATION.session_key,
        messages=messages,
        compacted_through=compacted_through,
    )


async def test_disabled_policy_and_untrimmed_history_do_not_call_plugin() -> None:
    snap = history_snapshot(record(Role.USER, "旧问题", 1))
    store = FakeSessionStore(snap.messages)
    compactor = RecordingCompactor(CompactionResult(through=1, content="摘要"))

    assert await run(snap, assembled(1), None, store) is None
    assert await run(snap, assembled(0), policy(compactor), store) is None
    assert compactor.requests == []


async def test_none_result_means_skip_without_persistence() -> None:
    snap = history_snapshot(record(Role.USER, "旧问题", 1))
    store = FakeSessionStore(snap.messages)
    compactor = RecordingCompactor()

    assert await run(snap, assembled(1), policy(compactor), store) is None
    assert len(compactor.requests) == 1
    assert store.compactions == []


@pytest.mark.parametrize(
    "result",
    [
        CompactionResult(through=1, content=" "),
        CompactionResult(through=0, content="摘要"),
        CompactionResult(through=4, content="摘要"),
        CompactionResult(through=2, content="摘要"),
    ],
)
async def test_invalid_result_is_reported_and_ignored(result: CompactionResult) -> None:
    snap = history_snapshot(
        record(Role.USER, "旧问题", 1),
        record(Role.ASSISTANT, "旧回答", 2),
        record(Role.USER, "新问题", 3),
        compacted_through=1,
    )
    store = FakeSessionStore(snap.messages)
    failures: list[NucleaError] = []

    applied = await run(
        snap,
        assembled(2),
        policy(RecordingCompactor(result)),
        store,
        failures,
    )

    assert applied is None
    assert store.compactions == []
    assert [error.code for error in failures] == [ErrorCode.PLUGIN_HOOK_FAILED]


async def test_tool_and_empty_records_are_skipped_when_mapping_watermark() -> None:
    snap = history_snapshot(
        record(Role.USER, "旧问题", 1),
        record(Role.TOOL, "工具输出", 2, tool_call_id="c1"),
        record(Role.ASSISTANT, "", 3),
        record(Role.ASSISTANT, "旧回答", 4),
    )
    store = FakeSessionStore(snap.messages)
    failures: list[NucleaError] = []

    too_low = await run(
        snap,
        assembled(2),
        policy(RecordingCompactor(CompactionResult(through=2, content="摘要"))),
        store,
        failures,
    )
    applied = await run(
        snap,
        assembled(2),
        policy(RecordingCompactor(CompactionResult(through=4, content="摘要"))),
        store,
    )

    assert too_low is None
    assert [error.code for error in failures] == [ErrorCode.PLUGIN_HOOK_FAILED]
    assert applied is not None
    assert applied.through == 4


@pytest.mark.parametrize(
    ("compactor", "code"),
    [
        (RecordingCompactor(error=RuntimeError("boom")), ErrorCode.PLUGIN_HOOK_FAILED),
        (RecordingCompactor(hang=True), ErrorCode.TIMEOUT_HOOK),
    ],
)
async def test_plugin_failure_falls_back(compactor: RecordingCompactor, code: ErrorCode) -> None:
    snap = history_snapshot(record(Role.USER, "旧问题", 1))
    store = FakeSessionStore(snap.messages)
    failures: list[NucleaError] = []

    applied = await run(
        snap,
        assembled(1),
        policy(compactor, timeout_ms=1),
        store,
        failures,
    )

    assert applied is None
    assert [error.code for error in failures] == [code]


async def test_success_persists_summary_and_reloads_snapshot() -> None:
    snap = history_snapshot(
        record(Role.USER, "旧问题", 1),
        record(Role.ASSISTANT, "旧回答", 2),
        record(Role.USER, "最近问题", 3),
    )
    store = FakeSessionStore(snap.messages)
    compactor = RecordingCompactor(CompactionResult(through=2, content="  对话摘要  "))

    applied = await run(snap, assembled(2), policy(compactor), store)

    assert applied is not None
    assert applied.through == 2
    assert len(store.compactions) == 1
    assert store.compactions[0][2].content == "对话摘要"
    assert applied.snapshot.live_messages[0].content == "对话摘要"
    assert compactor.requests[0].target_tokens == 32


async def test_persistence_failure_propagates() -> None:
    class CompactFailingStore(FakeSessionStore):
        async def compact(self, key, through, summary):  # noqa: ANN001, ANN202
            del key, through, summary
            raise NucleaError(ErrorCode.PERSISTENCE_WRITE_FAILED, "磁盘满了。")

    snap = history_snapshot(record(Role.USER, "旧问题", 1))
    store = CompactFailingStore(snap.messages)
    compactor = RecordingCompactor(CompactionResult(through=1, content="摘要"))

    with pytest.raises(NucleaError) as caught:
        await run(snap, assembled(1), policy(compactor), store)
    assert caught.value.code is ErrorCode.PERSISTENCE_WRITE_FAILED
