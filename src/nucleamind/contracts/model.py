"""模型契约：请求、响应与流式增量（需求 §10.6、`MOD-001`–`MOD-005`）。

职责：定义模型能力声明 `ModelInfo`、采样参数、模型消息、`ModelRequest`、终止原因、
用量统计、`ModelResponse` 与流式 `ModelChunk`。
不负责：调用任何供应商 SDK、重试与限流、把错误映射成 `ErrorCode`——那些在
`kernel/model/`（`D13`）与各 Provider 实现；本模块不含任何 IO。

`ModelResponse.provider_metadata` 是 `Mapping[str, JsonValue]` 且走
`normalize_metadata()`，这就是「Provider 私有响应对象不得直接越过 Provider 边界」
（§10.6 末段）在类型层的强制：SDK 对象连塞进来的机会都没有，切换 Provider 时历史里
也不会残留只有旧 SDK 才认识的结构（`EDG-305`）。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Final

from .errors import ErrorCode, NucleaError
from .ids import Correlation, validate_identifier
from .metadata import EMPTY_METADATA, normalize_metadata
from .session import Role
from .tool import ToolCall, ToolSpec

if TYPE_CHECKING:  # pragma: no cover - 仅为注解，运行时不导入，避免与包根成环。
    from . import JsonValue

__all__ = [
    "ChunkKind",
    "ModelCapability",
    "ModelChunk",
    "ModelInfo",
    "ModelMessage",
    "ModelRequest",
    "ModelResponse",
    "SamplingParams",
    "StopReason",
    "TokenUsage",
]

#: 模型标识的长度上限。
_MAX_MODEL_ID_LENGTH: Final = 256


class ModelCapability(StrEnum):
    """可声明的模型能力（`MOD-001`）。

    不具备的能力必须缺席这个集合，由 Kernel 显式报「能力缺失」，不允许 Provider
    静默降级后假装支持（`MOD-005`）。
    """

    TOOL_CALLS = "tool_calls"
    STREAMING = "streaming"
    IMAGE_INPUT = "image_input"
    AUDIO_INPUT = "audio_input"
    STRUCTURED_OUTPUT = "structured_output"
    REASONING = "reasoning"
    PROMPT_CACHING = "prompt_caching"


class StopReason(StrEnum):
    """终止原因（§10.6「终止原因」）。

    `CONTENT_FILTER` 与 `ERROR` 必须与 `END_TURN` 可区分：前两者的输出不是完整答案，
    Channel 侧的呈现规则依赖这个区分（`EDG-304`）。
    """

    END_TURN = "end_turn"
    TOOL_CALLS = "tool_calls"
    MAX_TOKENS = "max_tokens"
    STOP_SEQUENCE = "stop_sequence"
    CONTENT_FILTER = "content_filter"
    CANCELLED = "cancelled"
    ERROR = "error"


class ChunkKind(StrEnum):
    """流式增量的种类（§10.6「流式增量」）。"""

    TEXT = "text"
    REASONING = "reasoning"
    TOOL_CALL = "tool_call"
    USAGE = "usage"
    DONE = "done"


@dataclass(frozen=True, slots=True)
class ModelInfo:
    """模型能力声明（`MOD-001`）。

    `context_window_tokens` 与 `max_output_tokens` 是 Context 预算推导的输入
    （`CTX-003`：不得生成超过模型限制的请求），因此必须由 Provider 如实声明，
    而不是让组装器去猜一个保守值。
    """

    model_id: str
    provider: str
    capabilities: frozenset[ModelCapability] = frozenset()
    context_window_tokens: int = 0
    max_output_tokens: int = 0

    def __post_init__(self) -> None:
        validate_identifier("model.model_id", self.model_id, max_length=_MAX_MODEL_ID_LENGTH)
        validate_identifier("model.provider", self.provider)
        if self.context_window_tokens < 0 or self.max_output_tokens < 0:
            raise NucleaError(
                ErrorCode.CONFIG_INVALID,
                "模型的窗口与最大输出声明不得为负。",
                detail={
                    "model_id": self.model_id,
                    "context_window_tokens": self.context_window_tokens,
                    "max_output_tokens": self.max_output_tokens,
                },
            )

    def supports(self, capability: ModelCapability) -> bool:
        """能力查询。缺席即不支持，不做任何推断。"""
        return capability in self.capabilities


@dataclass(frozen=True, slots=True)
class SamplingParams:
    """采样与输出参数（§10.6「采样、最大输出和超时等受支持参数」）。

    全部可选：Provider 不支持某项时按 `MOD-005` 显式报不支持，而不是悄悄忽略。
    """

    temperature: float | None = None
    top_p: float | None = None
    max_output_tokens: int | None = None
    stop_sequences: tuple[str, ...] = ()
    seed: int | None = None

    def __post_init__(self) -> None:
        if self.temperature is not None and not 0.0 <= self.temperature <= 2.0:
            raise NucleaError(
                ErrorCode.CONFIG_INVALID,
                "temperature 必须落在 [0, 2]。",
                detail={"temperature": self.temperature},
            )
        if self.top_p is not None and not 0.0 <= self.top_p <= 1.0:
            raise NucleaError(
                ErrorCode.CONFIG_INVALID,
                "top_p 必须落在 [0, 1]。",
                detail={"top_p": self.top_p},
            )
        if self.max_output_tokens is not None and self.max_output_tokens <= 0:
            raise NucleaError(
                ErrorCode.CONFIG_INVALID,
                "max_output_tokens 必须为正。",
                detail={"max_output_tokens": self.max_output_tokens},
            )


@dataclass(frozen=True, slots=True)
class ModelMessage:
    """送入模型的一条消息（§10.6「有序消息与 Context」）。

    与 `SessionMessage` 分开：前者是持久化资产，后者是本次请求的投影。同一段历史在
    不同 Provider 下可能投影成不同形状（`EDG-305`），持久化格式不该跟着变。
    """

    role: Role
    content: str = ""
    tool_calls: tuple[ToolCall, ...] = ()
    tool_call_id: str | None = None

    def __post_init__(self) -> None:
        if self.tool_calls and self.role is not Role.ASSISTANT:
            raise NucleaError(
                ErrorCode.KERNEL_INVARIANT_VIOLATED,
                "只有 assistant 消息可以携带 tool_calls。",
                detail={"role": self.role.value},
            )
        if (self.role is Role.TOOL) != (self.tool_call_id is not None):
            raise NucleaError(
                ErrorCode.KERNEL_INVARIANT_VIOLATED,
                "tool_call_id 必须且只能出现在 role=TOOL 的消息上。",
                detail={"role": self.role.value},
            )
        if not self.content and not self.tool_calls:
            raise NucleaError(
                ErrorCode.INPUT_MALFORMED,
                "模型消息的内容与 tool_calls 不能同时为空。",
                detail={"role": self.role.value},
            )


@dataclass(frozen=True, slots=True)
class ModelRequest:
    """一次模型请求（§10.6 请求五条）。

    `correlation` 让请求、响应、工具调用与事件挂在同一个 `turn_id` 上（`KER-010`）；
    `stream=True` 且模型不支持流式时由 Provider 报不支持，契约层不替它降级。
    """

    model_id: str
    messages: tuple[ModelMessage, ...]
    correlation: Correlation
    tools: tuple[ToolSpec, ...] = ()
    params: SamplingParams = SamplingParams()
    stream: bool = False
    timeout_ms: int = 0

    def __post_init__(self) -> None:
        validate_identifier("model.model_id", self.model_id, max_length=_MAX_MODEL_ID_LENGTH)
        if not self.messages:
            raise NucleaError(
                ErrorCode.INPUT_MALFORMED,
                "模型请求必须至少包含一条消息。",
                detail={"model_id": self.model_id},
            )
        if self.timeout_ms < 0:
            raise NucleaError(
                ErrorCode.CONFIG_INVALID,
                "模型请求超时不得为负。",
                detail={"timeout_ms": self.timeout_ms},
            )
        names = [spec.name for spec in self.tools]
        if len(names) != len(set(names)):
            raise NucleaError(
                ErrorCode.KERNEL_INVARIANT_VIOLATED,
                "同一请求内的工具名必须唯一，否则模型无法确定调用哪一个。",
                detail={"model_id": self.model_id, "tools": len(names)},
            )


@dataclass(frozen=True, slots=True)
class TokenUsage:
    """用量统计（§10.6「Token 或费用用量」）。

    字段名刻意含 `tokens` 而不是含 `token`：`contracts.errors` 的脱敏按整词判定，
    `input_tokens` 这类统计字段必须能原样出现在事件与日志里，那正是可观测性的主线索。
    """

    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0
    reasoning_tokens: int = 0
    cost_usd: float | None = None

    def __post_init__(self) -> None:
        negatives = {
            name: value
            for name, value in (
                ("input_tokens", self.input_tokens),
                ("output_tokens", self.output_tokens),
                ("cached_input_tokens", self.cached_input_tokens),
                ("reasoning_tokens", self.reasoning_tokens),
            )
            if value < 0
        }
        if negatives:
            raise NucleaError(
                ErrorCode.INPUT_MALFORMED,
                "用量统计不得为负。",
                detail=negatives,
            )

    @property
    def total_tokens(self) -> int:
        """输入与输出之和。缓存与推理 token 已分别计入两者，不重复相加。"""
        return self.input_tokens + self.output_tokens


@dataclass(frozen=True, slots=True)
class ModelResponse:
    """一次模型响应（§10.6 响应）。

    `provider_metadata` 是**已归一化**的供应商元数据；Provider 私有对象不得越过边界，
    构造时的 `normalize_metadata()` 会对非 JSON 值直接报错。
    """

    model_id: str
    stop_reason: StopReason
    content: str = ""
    tool_calls: tuple[ToolCall, ...] = ()
    usage: TokenUsage = TokenUsage()
    provider_metadata: Mapping[str, JsonValue] = EMPTY_METADATA

    def __post_init__(self) -> None:
        validate_identifier("model.model_id", self.model_id, max_length=_MAX_MODEL_ID_LENGTH)
        if self.stop_reason is StopReason.TOOL_CALLS and not self.tool_calls:
            raise NucleaError(
                ErrorCode.KERNEL_INVARIANT_VIOLATED,
                "stop_reason=TOOL_CALLS 的响应必须带 tool_calls。",
                detail={"model_id": self.model_id},
            )
        call_ids = [call.call_id for call in self.tool_calls]
        if len(call_ids) != len(set(call_ids)):
            raise NucleaError(
                ErrorCode.KERNEL_INVARIANT_VIOLATED,
                "同一响应内的 tool call id 必须唯一（EDG-303 重复 Tool Call）。",
                detail={"model_id": self.model_id, "tool_calls": len(call_ids)},
            )
        object.__setattr__(
            self,
            "provider_metadata",
            normalize_metadata(self.provider_metadata, field="model.provider_metadata"),
        )

    @property
    def is_complete_answer(self) -> bool:
        """只有 `END_TURN` 才是模型给出的完整答案（`EDG-304`、`EDG-303` 空响应）。"""
        return self.stop_reason is StopReason.END_TURN


@dataclass(frozen=True, slots=True)
class ModelChunk:
    """流式增量的一片（§10.6「流式增量」）。

    每种 `kind` 只允许携带自己那一份载荷，构造时校验。让一个 chunk 同时带文本、
    工具调用和用量，下游就得靠猜来决定先处理哪个。
    """

    kind: ChunkKind
    text: str = ""
    tool_call: ToolCall | None = None
    usage: TokenUsage | None = None
    stop_reason: StopReason | None = None

    def __post_init__(self) -> None:
        expectations = {
            ChunkKind.TEXT: bool(self.text),
            ChunkKind.REASONING: bool(self.text),
            ChunkKind.TOOL_CALL: self.tool_call is not None,
            ChunkKind.USAGE: self.usage is not None,
            ChunkKind.DONE: self.stop_reason is not None,
        }
        if not expectations[self.kind]:
            raise NucleaError(
                ErrorCode.KERNEL_INVARIANT_VIOLATED,
                "流式分片缺少其种类所要求的载荷。",
                detail={"kind": self.kind.value},
            )
