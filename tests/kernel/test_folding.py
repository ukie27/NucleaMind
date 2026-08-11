"""流折叠与工具结果折叠的单元测试（`D09`：`folding.py`）。

分片级的异常形态在这里逐个钉住——`DONE(ERROR)`、缺 DONE、重复 call_id、空 TEXT——
因为它们是「模型供应商不守规矩」的入口，engine 的其余部分都建立在「折叠结果一定合法」
这个前提上。
"""

from __future__ import annotations

import pytest

from nucleamind.contracts import (
    ChunkKind,
    ErrorCategory,
    ErrorCode,
    ModelChunk,
    NucleaError,
    Role,
    SideEffect,
    StopReason,
    TokenUsage,
    ToolCall,
    ToolResult,
)
from nucleamind.kernel.turn import (
    EMPTY_TOOL_RESULT_TEXT,
    StreamFolder,
    TurnLimits,
    assistant_message,
    blocked_result,
    escaped_result,
    fold_tool_result,
    skipped_result,
    unknown_tool_result,
)

from ._engine_support import ok_result, tool_call

# --------------------------------------------------------------------------------------
# StreamFolder：正常路径
# --------------------------------------------------------------------------------------


def test_folds_text_and_done() -> None:
    folder = StreamFolder("m")
    folder.push(ModelChunk(kind=ChunkKind.TEXT, text="你"))
    folder.push(ModelChunk(kind=ChunkKind.TEXT, text="好"))
    folder.push(ModelChunk(kind=ChunkKind.DONE, stop_reason=StopReason.END_TURN))
    response = folder.finish()
    assert response.content == "你好"
    assert response.stop_reason is StopReason.END_TURN
    assert response.model_id == "m"
    assert response.tool_calls == ()


def test_reasoning_does_not_enter_content() -> None:
    """`ModelResponse` 没有 reasoning 槽：推理只作为增量事件出去，不进下一轮请求。"""
    folder = StreamFolder("m")
    folder.push(ModelChunk(kind=ChunkKind.REASONING, text="想一想"))
    folder.push(ModelChunk(kind=ChunkKind.TEXT, text="答案"))
    folder.push(ModelChunk(kind=ChunkKind.DONE, stop_reason=StopReason.END_TURN))
    assert folder.finish().content == "答案"


def test_folds_tool_calls_in_arrival_order() -> None:
    folder = StreamFolder("m")
    for name in ("a", "b"):
        folder.push(ModelChunk(kind=ChunkKind.TOOL_CALL, tool_call=tool_call(name)))
    folder.push(ModelChunk(kind=ChunkKind.DONE, stop_reason=StopReason.TOOL_CALLS))
    response = folder.finish()
    assert [call.name for call in response.tool_calls] == ["a", "b"]


def test_usage_chunk_is_carried_through() -> None:
    folder = StreamFolder("m")
    folder.push(ModelChunk(kind=ChunkKind.TEXT, text="x"))
    folder.push(
        ModelChunk(kind=ChunkKind.USAGE, usage=TokenUsage(input_tokens=7, output_tokens=3))
    )
    folder.push(ModelChunk(kind=ChunkKind.DONE, stop_reason=StopReason.END_TURN))
    assert folder.finish().usage.input_tokens == 7


# --------------------------------------------------------------------------------------
# StreamFolder：供应商不守规矩
# --------------------------------------------------------------------------------------


def test_done_error_becomes_retryable_provider_error() -> None:
    folder = StreamFolder("m")
    folder.push(ModelChunk(kind=ChunkKind.TEXT, text="半句"))
    folder.push(ModelChunk(kind=ChunkKind.DONE, stop_reason=StopReason.ERROR))
    with pytest.raises(NucleaError) as excinfo:
        folder.finish()
    error = excinfo.value
    assert error.code is ErrorCode.EXTERNAL_MODEL_PROVIDER
    assert error.retryable is True
    # 已折叠的字符数进 detail：`D14` 的续写要知道「断在哪」不是零产出。
    assert error.detail["folded_chars"] == 2


def test_done_cancelled_becomes_cancelled_error() -> None:
    folder = StreamFolder("m")
    folder.push(ModelChunk(kind=ChunkKind.DONE, stop_reason=StopReason.CANCELLED))
    with pytest.raises(NucleaError) as excinfo:
        folder.finish()
    assert excinfo.value.category is ErrorCategory.CANCELLED


def test_missing_done_is_recorded_not_raised() -> None:
    """流被截断但内容完整可用时不该丢掉它，只在元数据里留证据。"""
    folder = StreamFolder("m")
    folder.push(ModelChunk(kind=ChunkKind.TEXT, text="答案"))
    response = folder.finish()
    assert response.content == "答案"
    assert response.stop_reason is StopReason.END_TURN
    assert response.provider_metadata["missing_done_chunk"] is True


def test_missing_done_with_tool_calls_infers_tool_calls_stop() -> None:
    folder = StreamFolder("m")
    folder.push(ModelChunk(kind=ChunkKind.TOOL_CALL, tool_call=tool_call("a")))
    response = folder.finish()
    assert response.stop_reason is StopReason.TOOL_CALLS


def test_duplicate_call_id_keeps_last_and_counts() -> None:
    """同一 call_id 的多个分片是增量拼装的常见形态；静默丢弃会让参数残缺。"""
    folder = StreamFolder("m")
    first = ToolCall(call_id="c1", name="echo", arguments={"text": "半"})
    second = ToolCall(call_id="c1", name="echo", arguments={"text": "完整"})
    folder.push(ModelChunk(kind=ChunkKind.TOOL_CALL, tool_call=first))
    folder.push(ModelChunk(kind=ChunkKind.TOOL_CALL, tool_call=second))
    folder.push(ModelChunk(kind=ChunkKind.DONE, stop_reason=StopReason.TOOL_CALLS))
    response = folder.finish()
    assert len(response.tool_calls) == 1
    assert response.tool_calls[0].arguments == {"text": "完整"}
    assert response.provider_metadata["tool_call_fragments"] == 1


def test_tool_calls_stop_without_any_call_is_provider_error() -> None:
    """声明有工具调用却一个分片都没给：交给契约层报不变量违规不如在这里直接指名。"""
    folder = StreamFolder("m")
    folder.push(ModelChunk(kind=ChunkKind.DONE, stop_reason=StopReason.TOOL_CALLS))
    with pytest.raises(NucleaError) as excinfo:
        folder.finish()
    assert excinfo.value.code is ErrorCode.EXTERNAL_MODEL_PROVIDER


def test_finish_is_single_use() -> None:
    folder = StreamFolder("m")
    folder.push(ModelChunk(kind=ChunkKind.DONE, stop_reason=StopReason.END_TURN))
    folder.finish()
    with pytest.raises(NucleaError) as excinfo:
        folder.finish()
    assert excinfo.value.code is ErrorCode.KERNEL_INVARIANT_VIOLATED


def test_push_after_finish_is_rejected() -> None:
    folder = StreamFolder("m")
    folder.push(ModelChunk(kind=ChunkKind.DONE, stop_reason=StopReason.END_TURN))
    folder.finish()
    with pytest.raises(NucleaError):
        folder.push(ModelChunk(kind=ChunkKind.TEXT, text="迟到"))


# --------------------------------------------------------------------------------------
# 消息构造
# --------------------------------------------------------------------------------------


def test_assistant_message_carries_tool_calls() -> None:
    from ._engine_support import tool_response

    response = tool_response(tool_call("echo"))
    message = assistant_message(response)
    assert message.role is Role.ASSISTANT
    assert message.tool_calls == response.tool_calls


def test_fold_tool_result_truncates_and_marks() -> None:
    limits = TurnLimits(tool_result_max_bytes=16)
    call = tool_call("echo")
    long = ok_result("x" * 100)
    folded, message = fold_tool_result(call, long, limits)
    assert folded.truncated is True
    assert len(folded.content.encode()) == 16  # 按字节而不是字符，不追加后缀
    assert message.content == folded.content
    assert message.tool_call_id == call.call_id
    assert message.role is Role.TOOL


def test_fold_tool_result_leaves_short_content_alone() -> None:
    call = tool_call("echo")
    folded, message = fold_tool_result(call, ok_result("短"), TurnLimits())
    assert folded.truncated is False
    assert folded.content == "短"
    assert message.content == "短"


def test_fold_tool_result_replaces_empty_content_in_message_only() -> None:
    """占位符只进消息：`ToolResult` 是工具自己给的事实，不该被 Kernel 改写。"""
    call = tool_call("echo")
    empty = ToolResult(
        call_id=call.call_id, ok=True, content="   ", truncated=False, side_effect=SideEffect.NONE
    )
    folded, message = fold_tool_result(call, empty, TurnLimits())
    assert folded.content == "   "
    assert message.content == EMPTY_TOOL_RESULT_TEXT.format(tool="echo")


# --------------------------------------------------------------------------------------
# 未执行路径的合成结果
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("factory", "code"),
    [
        (lambda call: unknown_tool_result(call), ErrorCode.CAPABILITY_MISSING),
        (lambda call: blocked_result(call, "策略不允许"), ErrorCode.PERMISSION_DENIED),
    ],
)
def test_synthesised_results_are_not_ok_and_have_no_side_effect(
    factory: object, code: ErrorCode
) -> None:
    call = tool_call("echo")
    result = factory(call)  # type: ignore[operator]
    assert result.ok is False
    assert result.side_effect is SideEffect.NONE
    assert result.error is not None
    assert result.error.code is code
    assert result.content, "回给模型的内容不能为空——模型需要知道为什么没结果"


def test_skipped_result_uses_cancel_reason_code() -> None:
    from nucleamind.contracts import CancelReason

    result = skipped_result(tool_call("echo"), CancelReason.SHUTDOWN)
    assert result.side_effect is SideEffect.NONE
    assert result.error is not None
    assert result.error.code is ErrorCode.CANCELLED_BY_SHUTDOWN


def test_escaped_result_marks_side_effect_unknown() -> None:
    """能力实现抛了裸异常：副作用是否已发生**不可知**，谎报 NONE 比说不知道更危险。"""
    result = escaped_result(tool_call("echo"), RuntimeError("boom"))
    assert result.ok is False
    assert result.side_effect is SideEffect.UNKNOWN
    assert result.error is not None
    assert result.error.code is ErrorCode.KERNEL_UNEXPECTED
    assert "RuntimeError" in result.content


def test_escaped_result_keeps_nuclea_error_code() -> None:
    """执行器给出的码（超时、权限）比这里能猜的准，不要用 KERNEL_UNEXPECTED 盖掉它。"""
    original = NucleaError(ErrorCode.TIMEOUT_TOOL_CALL, "超时了")
    result = escaped_result(tool_call("echo"), original)
    assert result.error is original
    assert result.side_effect is SideEffect.UNKNOWN
