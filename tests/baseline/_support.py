"""Fakes shared by the legacy behavior baseline.

Deliberately self-contained: the baseline must stay readable as a
specification of behavior, so it does not reuse the wider legacy test support
(``tests/legacy/agent/runner_helpers.py``) and does not reach for production
config objects except where a default value is itself part of the baseline.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from copy import deepcopy
from dataclasses import dataclass
from typing import Any
from unittest.mock import MagicMock

from nucleamind.legacy.agent.hook import AgentHook, AgentHookContext, AgentRunHookContext
from nucleamind.legacy.agent.runner import AgentRunSpec
from nucleamind.legacy.agent.tools.base import Tool, ToolResult
from nucleamind.legacy.agent.tools.registry import ToolRegistry
from nucleamind.legacy.providers.base import (
    GenerationSettings,
    LLMProvider,
    LLMResponse,
    ToolCallRequest,
)
from nucleamind.legacy.utils.llm_runtime import LLMRuntime

# Mirrors ``AgentDefaults().max_tool_result_chars``; the loop baseline pins the
# production default, so the runner baseline runs at the same size.
BASELINE_MAX_TOOL_RESULT_CHARS = 16_000


@dataclass
class ScriptedTurn:
    """One scripted model reply, optionally delivered as stream deltas."""

    response: LLMResponse
    content_deltas: tuple[str, ...] = ()
    reasoning_deltas: tuple[str, ...] = ()


ScriptEntry = LLMResponse | ScriptedTurn


def text_response(content: str, **kwargs: Any) -> LLMResponse:
    """A plain final answer."""
    return LLMResponse(content=content, tool_calls=[], **kwargs)


def tool_response(*calls: ToolCallRequest, content: str = "") -> LLMResponse:
    """A reply that asks for tools."""
    return LLMResponse(content=content, tool_calls=list(calls), finish_reason="tool_calls")


def call(name: str, call_id: str | None = None, **arguments: Any) -> ToolCallRequest:
    return ToolCallRequest(id=call_id or f"call_{name}", name=name, arguments=arguments)


class ScriptedProvider:
    """Replay a fixed script of model replies and record every request.

    ``chat_with_retry`` and ``chat_stream_with_retry`` consume the same script,
    so a test can switch a run between streaming and non-streaming without
    rewriting the script.
    """

    def __init__(
        self,
        script: Sequence[ScriptEntry],
        *,
        default: ScriptEntry | None = None,
        delay_s: float = 0.0,
    ) -> None:
        self._script = [
            entry if isinstance(entry, ScriptedTurn) else ScriptedTurn(entry)
            for entry in script
        ]
        self._default = (
            default
            if isinstance(default, ScriptedTurn)
            else ScriptedTurn(default) if default is not None else None
        )
        self._delay_s = delay_s
        self.requests: list[dict[str, Any]] = []
        # Provider attributes the runner and the governance layer read.
        self.generation = GenerationSettings(temperature=0.1, max_tokens=4096)
        self.supports_progress_deltas = False

    # -- script -----------------------------------------------------------
    @property
    def call_count(self) -> int:
        return len(self.requests)

    def _next(self, kwargs: dict[str, Any]) -> ScriptedTurn:
        self.requests.append(kwargs)
        if self._script:
            turn = self._script.pop(0)
        elif self._default is not None:
            turn = self._default
        else:
            raise AssertionError(
                f"ScriptedProvider exhausted after {len(self.requests)} request(s)"
            )
        # The runner mutates ``response.content`` in place, so every request
        # must get its own object — otherwise a reused script entry would be
        # observed already-cleaned on the next iteration.
        return ScriptedTurn(
            response=deepcopy(turn.response),
            content_deltas=turn.content_deltas,
            reasoning_deltas=turn.reasoning_deltas,
        )

    # -- provider surface -------------------------------------------------
    def get_default_model(self) -> str:
        return "test-model"

    def estimate_prompt_tokens(self, *_args: Any, **_kwargs: Any) -> tuple[int, str]:
        return (10_000, "test")

    def can_resume_conversation_state(self, *_args: Any, **_kwargs: Any) -> bool:
        return False

    def supports_native_compaction(self, *_args: Any, **_kwargs: Any) -> bool:
        return False

    async def chat_with_retry(self, **kwargs: Any) -> LLMResponse:
        turn = self._next(kwargs)
        if self._delay_s:
            await asyncio.sleep(self._delay_s)
        return turn.response

    async def chat_stream_with_retry(
        self,
        *,
        on_content_delta: Callable[[str], Awaitable[None]] | None = None,
        on_thinking_delta: Callable[[str], Awaitable[None]] | None = None,
        on_tool_call_delta: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
        on_stream_recover: Callable[[], Awaitable[None]] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        turn = self._next(kwargs)
        if self._delay_s:
            await asyncio.sleep(self._delay_s)
        for delta in turn.reasoning_deltas:
            if on_thinking_delta is not None:
                await on_thinking_delta(delta)
        for delta in turn.content_deltas:
            if on_content_delta is not None:
                await on_content_delta(delta)
        return turn.response


class FakeTool(Tool):
    """Tool whose result, failure mode and concurrency class are scripted."""

    def __init__(
        self,
        name: str,
        *,
        result: Any = "ok",
        raises: BaseException | None = None,
        trace: list[str] | None = None,
        read_only: bool = True,
        exclusive: bool = False,
        parameters: dict[str, Any] | None = None,
    ) -> None:
        self._name = name
        self._result = result
        self._raises = raises
        self._read_only = read_only
        self._exclusive = exclusive
        self._parameters = parameters or {"type": "object", "properties": {}}
        self.trace = trace if trace is not None else []
        self.calls: list[dict[str, Any]] = []

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return f"fake tool {self._name}"

    @property
    def parameters(self) -> dict[str, Any]:
        return self._parameters

    @property
    def read_only(self) -> bool:
        return self._read_only

    @property
    def exclusive(self) -> bool:
        return self._exclusive

    async def execute(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        self.trace.append(f"start:{self._name}")
        # One suspension point so concurrent batches can interleave here and
        # serial batches cannot.
        await asyncio.sleep(0)
        self.trace.append(f"end:{self._name}")
        if self._raises is not None:
            raise self._raises
        return self._result


def make_registry(*tools: Tool) -> ToolRegistry:
    registry = ToolRegistry()
    for tool in tools:
        registry.register(tool)
    return registry


def loose_tools(execute: Callable[..., Awaitable[Any]]) -> MagicMock:
    """A tools object without ``prepare_call``/``get``, routed to *execute*.

    Mirrors non-registry tool holders: the runner falls through to
    ``tools.execute(name, params)`` and tool exceptions reach the runner
    unwrapped.
    """
    tools = MagicMock()
    tools.get_definitions.return_value = []
    tools.prepare_call = None
    tools.get = None
    tools.execute = execute
    return tools


class RecordingHook(AgentHook):
    """Record the hook callbacks the baseline cares about, in order."""

    def __init__(self, *, streaming: bool = False) -> None:
        super().__init__()
        self._streaming = streaming
        self.events: list[tuple[str, Any]] = []

    def wants_streaming(self) -> bool:
        return self._streaming

    @property
    def stream_deltas(self) -> list[str]:
        return [value for name, value in self.events if name == "stream"]

    @property
    def reasoning_deltas(self) -> list[str]:
        return [value for name, value in self.events if name == "reasoning"]

    async def before_iteration(self, context: AgentHookContext) -> None:
        self.events.append(("iteration", context.iteration))

    async def on_stream(self, context: AgentHookContext, delta: str) -> None:
        self.events.append(("stream", delta))

    async def on_stream_end(self, context: AgentHookContext, *, resuming: bool) -> None:
        self.events.append(("stream_end", resuming))

    async def emit_reasoning(self, reasoning_content: str | None) -> None:
        self.events.append(("reasoning", reasoning_content))

    async def emit_reasoning_end(self) -> None:
        self.events.append(("reasoning_end", None))

    async def after_run(self, context: AgentRunHookContext) -> None:
        self.events.append(("after_run", context.stop_reason))


def make_spec(
    provider: ScriptedProvider,
    tools: Any,
    *,
    initial_messages: list[dict[str, Any]] | None = None,
    max_iterations: int = 3,
    max_tool_result_chars: int = BASELINE_MAX_TOOL_RESULT_CHARS,
    model: str = "test-model",
    context_window_tokens: int = 128_000,
    **kwargs: Any,
) -> AgentRunSpec:
    """Build an ``AgentRunSpec`` with baseline-friendly defaults."""
    runtime = LLMRuntime(
        provider=cast_provider(provider),
        model=model,
        generation=provider.generation,
        context_window_tokens=context_window_tokens,
    )
    return AgentRunSpec(
        initial_messages=initial_messages
        if initial_messages is not None
        else [{"role": "user", "content": "hi"}],
        tools=tools,
        runtime=runtime,
        max_iterations=max_iterations,
        max_tool_result_chars=max_tool_result_chars,
        **kwargs,
    )


def cast_provider(provider: ScriptedProvider) -> LLMProvider:
    """Hand the duck-typed provider to code annotated for ``LLMProvider``."""
    return provider  # type: ignore[return-value]


def tool_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [message for message in messages if message.get("role") == "tool"]


def error_result(text: str) -> ToolResult:
    return ToolResult.error(text)
