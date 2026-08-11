"""折叠：分片折成响应、结果折成消息（技术方案 §6.2、§10.6，需求 `EDG-303`、`EDG-403`）。

职责：把 `ModelChunk` 序列折叠成一个 `ModelResponse`（`StreamFolder`）；把 `ModelResponse` 与
`ToolResult` 折叠成下一轮请求要用的 `ModelMessage`（空结果占位、按 `tool_result_max_bytes`
截断）；为三条**未执行**路径（未知工具 / Hook 阻断 / 取消跳过）合成合法的 `ToolResult`。
不负责：发起请求、产出事件、判断 turn 是否结束、决定重试与续写——`_MAX_LENGTH_RECOVERIES`
与 `_MAX_EMPTY_RETRIES` 那类策略属于 `D14`；本模块是纯函数与纯状态机，不含 IO、不认识取消。

两处「为什么在这里」：

- **合成 `ToolResult` 与构造 `ModelMessage` 在同一个文件**：它们是同一件事的两半——未执行的
  调用也必须在下一轮请求里占一条 tool 消息，否则 `tool_calls` 会悬空，多数供应商直接报 400。
  拆开会让「怎样才是一条合法的 tool 消息」有两处实现。
- **`StreamFolder` 是推入式状态机而不是 `fold(chunks)`**：engine 必须在 `async for` 里边收边发
  delta 事件并做检查点 3。让折叠函数自己吃掉迭代器，就得多定义一个回调，或者让它产出
  `ModelChunk | ModelResponse` 的混合流——两种都比一个 6 行的 `push` 循环更绕。
"""

from __future__ import annotations

from dataclasses import replace

from nucleamind.contracts import (
    CancelReason,
    ChunkKind,
    ErrorCode,
    ModelChunk,
    ModelMessage,
    ModelResponse,
    NucleaError,
    Role,
    SideEffect,
    StopReason,
    TokenUsage,
    ToolCall,
    ToolResult,
)

from .cancel import CANCEL_REASON_CODES
from .limits import TurnLimits

__all__ = [
    "EMPTY_TOOL_RESULT_TEXT",
    "StreamFolder",
    "assistant_message",
    "blocked_result",
    "escaped_result",
    "fold_tool_result",
    "skipped_result",
    "unknown_tool_result",
]

#: 空结果占位。`ModelMessage` 拒绝「既无 content 又无 tool_calls」的消息，而工具**确实**可能
#: 什么都不返回（`rm` 成功、`grep` 无匹配）。给一句明确的说明，比让模型面对一条空消息去猜
#: 「是没执行还是没输出」要好——旧实现的 `empty_tool_result_message` 是同一个结论。
EMPTY_TOOL_RESULT_TEXT = "（{tool} 执行完成，没有输出。）"


class StreamFolder:
    """把一次流式请求的 `ModelChunk` 折叠成 `ModelResponse`。

    **不累积 reasoning**：`ModelResponse` 没有推理字段，推理只作为 `ModelReasoningDelta`
    事件流出，不进入答案也不进入下一轮请求。这是契约层的决定（推理属于过程不属于资产），
    这里只是不去违背它。
    """

    __slots__ = ("_calls", "_done", "_fragments", "_model_id", "_stop", "_text", "_usage")

    def __init__(self, model_id: str) -> None:
        self._model_id = model_id
        self._text: list[str] = []
        self._calls: dict[str, ToolCall] = {}
        self._fragments = 0
        self._usage: TokenUsage | None = None
        self._stop: StopReason | None = None
        self._done = False

    @property
    def text(self) -> str:
        """已收到的正文。取消时 orchestrator 要把它持久化并标记 `interrupted=True`。"""
        return "".join(self._text)

    def push(self, chunk: ModelChunk) -> None:
        """收下一个分片。只累积，不产出。

        **异常约定**：只在折叠已经结束后仍被推入时抛 `KERNEL_INVARIANT_VIOLATED`——
        一个已经交出响应的 folder 再收分片，说明调用方把两次请求的流搅在了一起。
        """
        self._require_open()
        if chunk.kind is ChunkKind.TEXT:
            self._text.append(chunk.text)
        elif chunk.kind is ChunkKind.TOOL_CALL and chunk.tool_call is not None:
            self._push_call(chunk.tool_call)
        elif chunk.kind is ChunkKind.USAGE:
            # 最后一个胜出。相加会让「每片都发累计用量」的供应商翻倍。
            self._usage = chunk.usage
        elif chunk.kind is ChunkKind.DONE and self._stop is None:
            # 第一个胜出。多个 DONE 是供应商的问题，不为它增加一条分支。
            self._stop = chunk.stop_reason

    def _push_call(self, call: ToolCall) -> None:
        """同 `call_id` 后到覆盖先到，保持首次出现的顺序。

        `ModelResponse` 构造时拒绝重复 `call_id`（`EDG-303`），所以必须去重。选覆盖而不是
        合并：`ModelChunk.tool_call` 携带的是**已解析**的 `ToolCall`（`arguments` 是映射不是
        JSON 片段），合并两个已解析的映射是猜测——增量拼装 JSON 是 Provider 边界的职责
        （§10.6「归一化在边界完成」）。覆盖次数记进 `provider_metadata`，让这件事仍然可观测。
        """
        if call.call_id in self._calls:
            self._fragments += 1
        self._calls[call.call_id] = call

    def finish(self) -> ModelResponse:
        """折叠成一个 `ModelResponse`。

        **异常约定**：供应商声明本次流是错误或已取消时抛 `NucleaError`，**不**折成一个
        看起来正常的响应——那会让主循环因为「没有 tool_calls」把它判成 `TurnCompleted`，
        把一次失败渲染成完整答案（`EDG-304`）。折叠只能做一次，重复调用抛
        `KERNEL_INVARIANT_VIOLATED`：状态机复用会让上一轮的文本混进下一轮。
        """
        self._require_open()
        self._done = True
        if self._stop is StopReason.ERROR:
            raise NucleaError(
                ErrorCode.EXTERNAL_MODEL_PROVIDER,
                "模型流式响应中途失败。",
                detail={"model_id": self._model_id, "folded_chars": len(self.text)},
                retryable=True,
            )
        if self._stop is StopReason.CANCELLED:
            raise NucleaError(
                CANCEL_REASON_CODES[CancelReason.USER],
                "模型流式响应被取消。",
                detail={"model_id": self._model_id, "folded_chars": len(self.text)},
            )
        if self._stop is StopReason.TOOL_CALLS and not self._calls:
            raise NucleaError(
                ErrorCode.EXTERNAL_MODEL_PROVIDER,
                "模型声明本轮有工具调用，却没有发出任何调用分片。",
                detail={"model_id": self._model_id},
                retryable=True,
            )

        metadata: dict[str, bool | int] = {}
        stop = self._stop
        if stop is None:
            # 全案唯一一处推断：流结束了但没有 DONE 分片。抛出会把一份**已完整收到**的答案
            # 变成 `TurnFailed`，对用户是净损失；但 `MOD-005` 要求不静默降级，因此把推断
            # 记进 `provider_metadata`，让它在事件与日志里可见，并有测试盯着这个标记。
            stop = StopReason.TOOL_CALLS if self._calls else StopReason.END_TURN
            metadata["missing_done_chunk"] = True
        if self._fragments:
            metadata["tool_call_fragments"] = self._fragments

        return ModelResponse(
            model_id=self._model_id,
            stop_reason=stop,
            content=self.text,
            tool_calls=tuple(self._calls.values()),
            usage=self._usage or TokenUsage(),
            provider_metadata=metadata,
        )

    def _require_open(self) -> None:
        if self._done:
            raise NucleaError(
                ErrorCode.KERNEL_INVARIANT_VIOLATED,
                "StreamFolder 已经完成折叠，不能重复使用。",
                detail={"model_id": self._model_id},
            )


def assistant_message(response: ModelResponse) -> ModelMessage:
    """把本轮响应折成下一轮请求里的 assistant 消息。

    只在「有工具调用、要继续下一轮」时被调用，因此 `ModelMessage` 的「content 与 tool_calls
    不得同时为空」必然满足——这条约束不是靠校验绕过的，是靠调用点结构消除的。
    """
    return ModelMessage(
        role=Role.ASSISTANT,
        content=response.content,
        tool_calls=response.tool_calls,
    )


def fold_tool_result(
    call: ToolCall, result: ToolResult, limits: TurnLimits
) -> tuple[ToolResult, ModelMessage]:
    """按预算截断结果，并折出对应的 tool 消息。返回**截断后**的结果与消息。

    返回截断后的结果而不只是消息：事件里带着 `truncated=False` 的结果、消息里却是截断过的
    文本，两者会在持久化与重放时对不上。截断是预算施加在这次调用上的事实，结果对象要如实
    反映它。

    占位只作用于**消息**：工具确实返回了空，`ToolResult.content` 保持空才是真话；而模型那边
    必须收到一条非空消息。
    """
    content, truncated = limits.truncate_tool_result(result.content)
    folded = result if not truncated else replace(result, content=content, truncated=True)
    text = content if content.strip() else EMPTY_TOOL_RESULT_TEXT.format(tool=call.name)
    return folded, ModelMessage(role=Role.TOOL, content=text, tool_call_id=call.call_id)


def unknown_tool_result(call: ToolCall, available: tuple[str, ...] = ()) -> ToolResult:
    """模型报了一个本次请求里没有的工具名（`EDG-303`）。

    对话式回复而不是终止 turn：模型完全可能在下一轮改用正确的名字，而这条错误对它是可读、
    可纠正的。旧实现也是这个结论，`D09` 保留。
    """
    names = "、".join(available) if available else "（本轮没有可用工具）"
    return ToolResult(
        call_id=call.call_id,
        ok=False,
        content=f"错误：工具 {call.name} 不存在。本轮可用的工具：{names}。",
        truncated=False,
        side_effect=SideEffect.NONE,
        error=NucleaError(
            ErrorCode.CAPABILITY_MISSING,
            "模型请求了一个本轮不可用的工具。",
            detail={"tool": call.name, "call_id": call.call_id},
        ),
    )


def blocked_result(call: ToolCall, reason: str) -> ToolResult:
    """`before_tool_call` Hook 返回 `BLOCK`：不执行，`side_effect=NONE`。"""
    return ToolResult(
        call_id=call.call_id,
        ok=False,
        content=f"错误：工具 {call.name} 的本次调用被策略阻止。原因：{reason}",
        truncated=False,
        side_effect=SideEffect.NONE,
        error=NucleaError(
            ErrorCode.PERMISSION_DENIED,
            "工具调用被 Hook 阻止。",
            detail={"tool": call.name, "call_id": call.call_id, "reason": reason},
        ),
    )


def skipped_result(call: ToolCall, reason: CancelReason) -> ToolResult:
    """取消发生时尚未轮到执行的调用（技术方案 §6.4 检查点 5）。

    `side_effect=NONE` 是这里的全部意义：turn 被中断后，用户必须能判定哪些副作用**没有**
    发生。合成一条结果而不是干脆不给，是因为 `tool_calls` 悬空会让这段历史无法重放。
    """
    return ToolResult(
        call_id=call.call_id,
        ok=False,
        content=f"错误：turn 已被取消，工具 {call.name} 未执行。",
        truncated=False,
        side_effect=SideEffect.NONE,
        error=NucleaError(
            CANCEL_REASON_CODES[reason],
            "turn 取消，工具未执行。",
            detail={"tool": call.name, "call_id": call.call_id, "reason": reason.value},
        ),
    )


def escaped_result(call: ToolCall, error: Exception) -> ToolResult:
    """`ToolInvoker.invoke` 逸出了异常——契约说它不该抛（`protocols.py` 的异常约定）。

    `side_effect=UNKNOWN` 而不是 `NONE`：异常从执行器里逃出来，说明它已经开始做事了，
    做到哪一步没人知道（`EDG-401`）。假设「什么都没发生」是这里最危险的选项。

    **工具失败不升级为 `TurnFailed`**：这条错误以一条 tool 消息回给模型，本轮继续——
    模型完全可能换个参数重试，或者绕开这个工具。旧实现同一结论。
    """
    # 抛出的已经是 `NucleaError` 时原样保留：执行器给出的码（超时、权限）比这里能猜的准。
    wrapped = (
        error
        if isinstance(error, NucleaError)
        else NucleaError(
            ErrorCode.KERNEL_UNEXPECTED,
            "工具执行器抛出了未预期的异常。",
            detail={
                "tool": call.name,
                "call_id": call.call_id,
                "exception": type(error).__name__,
                "message": str(error),
            },
        )
    )
    return ToolResult(
        call_id=call.call_id,
        ok=False,
        content=f"错误：工具 {call.name} 执行失败（{type(error).__name__}）：{error}",
        truncated=False,
        side_effect=SideEffect.UNKNOWN,
        error=wrapped,
    )
