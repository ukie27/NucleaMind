"""运行时事件契约测试（`D02`，需求 `OBS-001`–`OBS-003`）。"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime

import pytest

from nucleamind.contracts import (
    Correlation,
    ErrorCategory,
    ErrorCode,
    EventFamily,
    EventName,
    NucleaError,
    RuntimeEvent,
    SessionKey,
)
from nucleamind.contracts.errors import MASK
from nucleamind.contracts.ids import InstanceId, TurnId

INSTANCE = InstanceId("default")
NOW = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)
CORRELATION = Correlation(
    instance_id=INSTANCE,
    session_key=SessionKey("cli", "local"),
    turn_id=TurnId("t-1"),
)


def _event(**overrides: object) -> RuntimeEvent:
    base: dict[str, object] = {
        "name": EventName.TURN_STARTED,
        "sequence": 1,
        "occurred_at": NOW,
        "instance_id": INSTANCE,
        "correlation": CORRELATION,
    }
    base.update(overrides)
    return RuntimeEvent(**base)  # pyright: ignore[reportArgumentType]


# ------------------------------------------------------------------ 事件名与事件族


def test_every_event_name_belongs_to_a_declared_family() -> None:
    for name in EventName:
        assert name.family in EventFamily
        assert name.value.startswith(f"{name.family.value}.")


def test_every_family_has_at_least_one_event() -> None:
    assert {name.family for name in EventName} == set(EventFamily)


def test_event_names_are_unique() -> None:
    values = [name.value for name in EventName]
    assert len(set(values)) == len(values)


def test_event_exposes_family() -> None:
    assert _event(name=EventName.TOOL_CALL_FAILED).family is EventFamily.TOOL


# ------------------------------------------------------------------ 不变量


def test_sequence_must_be_non_negative() -> None:
    with pytest.raises(NucleaError) as excinfo:
        _event(sequence=-1)
    assert excinfo.value.category is ErrorCategory.KERNEL_INTERNAL


def test_timestamp_must_be_timezone_aware() -> None:
    with pytest.raises(NucleaError) as excinfo:
        _event(occurred_at=datetime(2026, 8, 10, 12, 0))  # noqa: DTZ001
    assert excinfo.value.category is ErrorCategory.KERNEL_INTERNAL


def test_correlation_instance_must_match_event_instance() -> None:
    with pytest.raises(NucleaError) as excinfo:
        _event(instance_id=InstanceId("other"))
    assert excinfo.value.category is ErrorCategory.KERNEL_INTERNAL


def test_instance_level_events_may_omit_correlation() -> None:
    """实例启动阶段还没有会话与 turn，此时 correlation 必须允许为空（`OBS-001`）。"""
    event = _event(name=EventName.INSTANCE_STARTING, correlation=None)
    assert event.correlation is None
    assert event.instance_id == INSTANCE


def test_event_is_frozen() -> None:
    event = _event()
    with pytest.raises(dataclasses.FrozenInstanceError):
        event.sequence = 2  # pyright: ignore[reportAttributeAccessIssue]


# ------------------------------------------------------------------ payload


def test_payload_defaults_to_empty_and_is_read_only() -> None:
    event = _event()
    assert dict(event.payload) == {}
    with pytest.raises(TypeError):
        event.payload["x"] = 1  # pyright: ignore[reportIndexIssue]


def test_payload_is_redacted_at_construction() -> None:
    """脱敏不依赖 sink：事件一旦存在就已经是安全的（`OBS-003`）。"""
    event = _event(payload={"api_key": "S3NT1NEL-value", "model": "claude-fable-5"})
    assert event.payload["api_key"] == MASK
    assert event.payload["model"] == "claude-fable-5"
    assert "S3NT1NEL-value" not in repr(event.payload)


def test_payload_snapshot_is_detached_from_caller() -> None:
    """调用方事后改自己的 dict 不能反向影响已发布的事件。"""
    payload: dict[str, object] = {"tokens": 10}
    event = _event(payload=payload)
    payload["tokens"] = 999
    assert event.payload["tokens"] == 10


def test_event_can_carry_an_error() -> None:
    error = NucleaError(ErrorCode.TIMEOUT_MODEL_REQUEST, "模型请求超时", retryable=True)
    event = _event(name=EventName.MODEL_REQUEST_FAILED, error=error)
    assert event.error is error
    assert event.family is EventFamily.MODEL
