"""模型契约测试（`D03`，需求 §10.6、`MOD-001`、`MOD-005`、`EDG-303`–`EDG-305`）。

`provider_metadata` 拒收非 JSON 值是本文件的重点：这是「Provider 私有响应对象不得直接
越过 Provider 边界」在类型层唯一的强制点。
"""

from __future__ import annotations

import dataclasses

import pytest

from nucleamind.contracts import (
    ChunkKind,
    Correlation,
    ErrorCode,
    InstanceId,
    ModelCapability,
    ModelChunk,
    ModelInfo,
    ModelMessage,
    ModelRequest,
    ModelResponse,
    NucleaError,
    Role,
    SamplingParams,
    SessionKey,
    StopReason,
    TokenUsage,
    ToolCall,
    ToolSpec,
    TurnId,
)

CORRELATION = Correlation(InstanceId("default"), SessionKey("cli", "local"), TurnId("t-1"))
USER_MESSAGE = ModelMessage(Role.USER, "你好")


def request(**overrides: object) -> ModelRequest:
    base: dict[str, object] = {
        "model_id": "claude-fable-5",
        "messages": (USER_MESSAGE,),
        "correlation": CORRELATION,
    }
    base.update(overrides)
    return ModelRequest(**base)  # pyright: ignore[reportArgumentType]


def response(**overrides: object) -> ModelResponse:
    base: dict[str, object] = {
        "model_id": "claude-fable-5",
        "stop_reason": StopReason.END_TURN,
        "content": "你好",
    }
    base.update(overrides)
    return ModelResponse(**base)  # pyright: ignore[reportArgumentType]


def test_instances_are_frozen() -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        request().model_id = "x"
    with pytest.raises(dataclasses.FrozenInstanceError):
        response().content = "x"


# ------------------------------------------------------------------ ModelInfo / MOD-001


def test_capabilities_absent_means_unsupported() -> None:
    """`MOD-005`：不具备的能力必须缺席集合，不允许静默降级。"""
    info = ModelInfo("m", "fake", frozenset({ModelCapability.TOOL_CALLS}))
    assert info.supports(ModelCapability.TOOL_CALLS)
    assert not info.supports(ModelCapability.STREAMING)


def test_capability_values_are_complete() -> None:
    assert {cap.value for cap in ModelCapability} == {
        "tool_calls",
        "streaming",
        "image_input",
        "audio_input",
        "structured_output",
        "reasoning",
        "prompt_caching",
    }


def test_negative_window_is_rejected() -> None:
    with pytest.raises(NucleaError) as exc:
        ModelInfo("m", "fake", context_window_tokens=-1)
    assert exc.value.code is ErrorCode.CONFIG_INVALID


# ------------------------------------------------------------------ SamplingParams


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("temperature", -0.1),
        ("temperature", 2.1),
        ("top_p", 1.5),
        ("max_output_tokens", 0),
    ],
)
def test_out_of_range_params_are_rejected(field: str, value: float) -> None:
    with pytest.raises(NucleaError) as exc:
        SamplingParams(**{field: value})  # pyright: ignore[reportArgumentType]
    assert exc.value.code is ErrorCode.CONFIG_INVALID


def test_boundary_params_are_accepted() -> None:
    assert SamplingParams(temperature=0.0, top_p=1.0).top_p == 1.0


# ------------------------------------------------------------------ ModelMessage


def test_tool_calls_only_on_assistant() -> None:
    call = ToolCall("c-1", "fs.read")
    assert ModelMessage(Role.ASSISTANT, tool_calls=(call,)).tool_calls == (call,)
    with pytest.raises(NucleaError) as exc:
        ModelMessage(Role.USER, "x", tool_calls=(call,))
    assert exc.value.code is ErrorCode.KERNEL_INVARIANT_VIOLATED


def test_tool_call_id_only_on_tool_role() -> None:
    assert ModelMessage(Role.TOOL, "结果", tool_call_id="c-1").tool_call_id == "c-1"
    with pytest.raises(NucleaError):
        ModelMessage(Role.TOOL, "结果")


def test_empty_message_is_rejected() -> None:
    with pytest.raises(NucleaError) as exc:
        ModelMessage(Role.USER)
    assert exc.value.code is ErrorCode.INPUT_MALFORMED


# ------------------------------------------------------------------ ModelRequest


def test_request_requires_messages() -> None:
    with pytest.raises(NucleaError) as exc:
        request(messages=())
    assert exc.value.code is ErrorCode.INPUT_MALFORMED


def test_request_rejects_duplicate_tool_names() -> None:
    """同名工具会让模型无法确定调用哪一个，属于组装错误而非模型问题。"""
    duplicate = (
        ToolSpec("fs.read", "读", {}),
        ToolSpec("fs.read", "又一个读", {}),
    )
    with pytest.raises(NucleaError) as exc:
        request(tools=duplicate)
    assert exc.value.code is ErrorCode.KERNEL_INVARIANT_VIOLATED


def test_request_carries_correlation() -> None:
    """`KER-010`：请求、响应、工具调用与事件挂在同一个 turn_id 上。"""
    assert request().correlation.turn_id == "t-1"


# ------------------------------------------------------------------ ModelResponse


def test_tool_calls_stop_reason_requires_calls() -> None:
    with pytest.raises(NucleaError) as exc:
        response(stop_reason=StopReason.TOOL_CALLS)
    assert exc.value.code is ErrorCode.KERNEL_INVARIANT_VIOLATED


def test_duplicate_call_ids_are_rejected() -> None:
    """`EDG-303`：重复 Tool Call 必须受控终止，而不是让执行器按 id 覆盖结果。"""
    calls = (ToolCall("c-1", "fs.read"), ToolCall("c-1", "fs.list"))
    with pytest.raises(NucleaError) as exc:
        response(stop_reason=StopReason.TOOL_CALLS, tool_calls=calls)
    assert exc.value.code is ErrorCode.KERNEL_INVARIANT_VIOLATED


@pytest.mark.parametrize(
    ("reason", "complete"),
    [
        (StopReason.END_TURN, True),
        (StopReason.MAX_TOKENS, False),
        (StopReason.CONTENT_FILTER, False),
        (StopReason.CANCELLED, False),
        (StopReason.ERROR, False),
    ],
)
def test_only_end_turn_is_a_complete_answer(reason: StopReason, complete: bool) -> None:
    assert response(stop_reason=reason).is_complete_answer is complete


def test_provider_metadata_rejects_sdk_objects() -> None:
    """§10.6 末段：Provider 私有响应对象不得直接越过 Provider 边界。"""
    with pytest.raises(NucleaError):
        response(provider_metadata={"raw": object()})


def test_provider_metadata_is_frozen_snapshot() -> None:
    source = {"anthropic": {"stop_sequence": None}}
    normalized = response(provider_metadata=source)
    source["anthropic"] = {"stop_sequence": "x"}
    assert normalized.provider_metadata["anthropic"] == {"stop_sequence": None}


# ------------------------------------------------------------------ TokenUsage


def test_usage_field_names_survive_redaction() -> None:
    """脱敏按整词判定，`input_tokens` 这类统计字段必须能原样进事件与日志。"""
    from nucleamind.contracts import redact

    usage = TokenUsage(input_tokens=10, output_tokens=5)
    redacted, _ = redact(dataclasses.asdict(usage))
    assert redacted["input_tokens"] == 10
    assert redacted["output_tokens"] == 5


def test_total_tokens_sums_input_and_output() -> None:
    assert TokenUsage(input_tokens=10, output_tokens=5, cached_input_tokens=8).total_tokens == 15


def test_negative_usage_is_rejected() -> None:
    with pytest.raises(NucleaError) as exc:
        TokenUsage(input_tokens=-1)
    assert exc.value.code is ErrorCode.INPUT_MALFORMED


# ------------------------------------------------------------------ ModelChunk


@pytest.mark.parametrize(
    ("label", "chunk"),
    [
        ("text", {"kind": ChunkKind.TEXT, "text": "hi"}),
        ("reasoning", {"kind": ChunkKind.REASONING, "text": "思考"}),
        ("tool_call", {"kind": ChunkKind.TOOL_CALL, "tool_call": ToolCall("c-1", "fs.read")}),
        ("usage", {"kind": ChunkKind.USAGE, "usage": TokenUsage()}),
        ("done", {"kind": ChunkKind.DONE, "stop_reason": StopReason.END_TURN}),
    ],
)
def test_chunk_accepts_its_own_payload(label: str, chunk: dict[str, object]) -> None:
    assert ModelChunk(**chunk).kind is chunk["kind"]  # pyright: ignore[reportArgumentType]


@pytest.mark.parametrize(
    "kind", [ChunkKind.TEXT, ChunkKind.REASONING, ChunkKind.TOOL_CALL, ChunkKind.USAGE, ChunkKind.DONE]
)
def test_chunk_without_its_payload_is_rejected(kind: ChunkKind) -> None:
    """一个 chunk 同时带多种载荷，下游就得靠猜决定先处理哪个。"""
    with pytest.raises(NucleaError) as exc:
        ModelChunk(kind)
    assert exc.value.code is ErrorCode.KERNEL_INVARIANT_VIOLATED
