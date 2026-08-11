"""Behavior baseline for ``legacy/agent/runner.py`` (D07).

These tests pin the *observable* behavior of ``AgentRunner`` — not its
internals — so that ``D09``'s ``kernel/turn/engine.py`` can be compared against
a written record instead of against a reading of the old code. Five behaviors
are in scope (development plan D07):

* ``B1`` how the run terminates once the iteration budget is spent, and what it
  returns.
* ``B2`` what the model is shown when a tool fails, times out, or is called
  with invalid arguments.
* ``B3`` the order of streaming increments and their consistency with the final
  content.
* ``B4`` the real scheduling order of concurrent and serial tool batches.
* ``B5`` what happens to an oversized tool result.

Where the legacy behavior is a deliberate policy the new engine must keep,
the test says so in a comment. Where it is merely what the old code happens to
do, the assertion still stands — a difference in ``D09`` must be a decision,
not an accident.
"""

from __future__ import annotations

import asyncio

import pytest

from nucleamind.legacy.agent.runner import (
    _MAX_EMPTY_RETRIES,
    _MAX_LENGTH_RECOVERIES,
    AgentRunner,
)
from nucleamind.legacy.providers.base import LLMResponse
from nucleamind.legacy.utils.helpers import safe_filename
from nucleamind.legacy.utils.prompt_templates import render_template
from nucleamind.legacy.utils.runtime import (
    EMPTY_FINAL_RESPONSE_MESSAGE,
    FINALIZATION_RETRY_PROMPT,
    LENGTH_RECOVERY_PROMPT,
    empty_tool_result_message,
)

from ._support import (
    BASELINE_MAX_TOOL_RESULT_CHARS,
    FakeTool,
    RecordingHook,
    ScriptedProvider,
    ScriptedTurn,
    call,
    error_result,
    loose_tools,
    make_registry,
    make_spec,
    text_response,
    tool_messages,
    tool_response,
)

TOOL_ERROR_HINT = "\n\n[Analyze the error above and try a different approach.]"


# ---------------------------------------------------------------------------
# B1 — iteration budget
# ---------------------------------------------------------------------------


async def test_max_iterations_stops_and_finalizes_without_tools():
    """The budget is spent on tool iterations; one extra no-tools call finalizes."""
    provider = ScriptedProvider(
        [
            tool_response(call("echo")),
            tool_response(call("echo")),
            text_response("wrapping up"),
        ]
    )
    tools = make_registry(FakeTool("echo"))

    result = await AgentRunner().run(make_spec(provider, tools, max_iterations=2))

    assert result.stop_reason == "max_iterations"
    assert result.final_content == "wrapping up"
    assert result.error is None
    # Two tool iterations plus exactly one finalization request.
    assert provider.call_count == 3
    assert provider.requests[0]["tools"] is not None
    assert provider.requests[-1]["tools"] is None
    # The finalization request is a copy of the transcript plus one prompt; the
    # transcript itself never gains that prompt.
    assert provider.requests[-1]["messages"][-1]["role"] == "user"
    assert result.messages[-1] == {"role": "assistant", "content": "wrapping up"}
    assert all("tool_calls" not in m or not m["tool_calls"] for m in result.messages[-1:])


async def test_max_iterations_falls_back_to_template_when_finalization_unusable():
    """A finalization that errors, asks for tools, or is blank yields the template."""
    fallback = render_template(
        "agent/max_iterations_message.md",
        strip=True,
        max_iterations=1,
    )

    for finalization in (
        tool_response(call("echo"), content="still working"),
        LLMResponse(content="boom", finish_reason="error"),
        text_response("   "),
    ):
        provider = ScriptedProvider([tool_response(call("echo")), finalization])
        result = await AgentRunner().run(
            make_spec(provider, make_registry(FakeTool("echo")), max_iterations=1)
        )
        assert result.stop_reason == "max_iterations"
        assert result.final_content == fallback
        assert result.messages[-1]["content"] == fallback


async def test_max_iterations_without_finalization_makes_no_extra_request():
    provider = ScriptedProvider([tool_response(call("echo"))])

    result = await AgentRunner().run(
        make_spec(
            provider,
            make_registry(FakeTool("echo")),
            max_iterations=1,
            finalize_on_max_iterations=False,
            max_iterations_message="stopped after {max_iterations} steps",
        )
    )

    assert provider.call_count == 1
    assert result.stop_reason == "max_iterations"
    assert result.final_content == "stopped after 1 steps"


async def test_unbounded_tool_calls_terminate_within_the_budget():
    """A model that never stops asking for tools still terminates."""
    provider = ScriptedProvider([], default=tool_response(call("echo")))

    result = await AgentRunner().run(
        make_spec(
            provider,
            make_registry(FakeTool("echo")),
            max_iterations=5,
            finalize_on_max_iterations=False,
        )
    )

    assert result.stop_reason == "max_iterations"
    assert provider.call_count == 5
    assert len(tool_messages(result.messages)) == 5


# ---------------------------------------------------------------------------
# B2 — tool failure, timeout, invalid arguments
# ---------------------------------------------------------------------------


async def test_tool_exception_is_reported_to_the_model_and_the_run_continues():
    async def execute(_name, _params):
        raise RuntimeError("boom")

    provider = ScriptedProvider([tool_response(call("broken")), text_response("recovered")])

    result = await AgentRunner().run(make_spec(provider, loose_tools(execute)))

    assert tool_messages(result.messages)[0]["content"] == "Error: RuntimeError: boom"
    assert result.tool_events == [
        {"name": "broken", "status": "error", "detail": "boom"}
    ]
    # A failed call is not a used tool.
    assert result.tools_used == []
    assert result.stop_reason == "completed"
    assert result.final_content == "recovered"


async def test_fail_on_tool_error_aborts_the_run_with_the_same_text():
    async def execute(_name, _params):
        raise RuntimeError("boom")

    provider = ScriptedProvider([tool_response(call("broken"))])

    result = await AgentRunner().run(
        make_spec(provider, loose_tools(execute), fail_on_tool_error=True)
    )

    assert result.stop_reason == "tool_error"
    assert result.final_content == "Error: RuntimeError: boom"
    assert result.error == result.final_content
    # The model is not asked again after a fatal tool error.
    assert provider.call_count == 1
    # The tool result is still recorded before the run stops.
    assert tool_messages(result.messages)[0]["content"] == "Error: RuntimeError: boom"


async def test_tool_error_result_gets_a_retry_hint():
    """``ToolResult.error`` is recoverable: the model is nudged to try again."""
    provider = ScriptedProvider(
        [tool_response(call("failing")), text_response("ok")]
    )
    tools = make_registry(FakeTool("failing", result=error_result("Error: no such file")))

    result = await AgentRunner().run(make_spec(provider, tools))

    assert tool_messages(result.messages)[0]["content"] == (
        "Error: no such file" + TOOL_ERROR_HINT
    )
    assert result.tools_used == []


async def test_unknown_tool_and_invalid_arguments_are_answered_conversationally():
    """Neither an unknown name nor bad arguments raises; both reach the model."""
    provider = ScriptedProvider(
        [
            tool_response(call("nope"), call("echo", call_id="call_bad", value=1)),
            text_response("understood"),
        ]
    )
    echo = FakeTool(
        "echo",
        parameters={
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "required": ["needle"],
        },
    )

    result = await AgentRunner().run(make_spec(provider, make_registry(echo)))

    unknown, invalid = tool_messages(result.messages)
    assert unknown["content"].startswith("Error: Tool 'nope' not found.")
    assert "Available: echo" in unknown["content"]
    assert unknown["content"].endswith(TOOL_ERROR_HINT)
    assert invalid["content"].startswith("Error: Invalid parameters for tool 'echo':")
    assert invalid["content"].endswith(TOOL_ERROR_HINT)
    # The tool never ran.
    assert echo.calls == []
    assert result.stop_reason == "completed"


async def test_tool_timeout_reaches_the_model_as_a_tool_error():
    """The runner imposes no per-tool deadline; a tool's own timeout is text."""

    async def execute(_name, _params):
        raise asyncio.TimeoutError()

    provider = ScriptedProvider([tool_response(call("slow")), text_response("ok")])

    result = await AgentRunner().run(make_spec(provider, loose_tools(execute)))

    assert tool_messages(result.messages)[0]["content"] == "Error: TimeoutError: "
    assert result.stop_reason == "completed"


async def test_model_wall_clock_timeout_ends_the_run_as_an_error():
    provider = ScriptedProvider([text_response("never delivered")], delay_s=0.5)

    result = await AgentRunner().run(
        make_spec(provider, make_registry(FakeTool("echo")), llm_timeout_s=0.05)
    )

    assert result.stop_reason == "error"
    assert result.final_content == "Error calling LLM: timed out after 0.05s"
    assert result.error == result.final_content
    # History keeps a placeholder so the transcript stays well-formed.
    assert result.messages[-1] == {
        "role": "assistant",
        "content": "[Assistant reply unavailable due to model error.]",
    }


async def test_security_boundary_rejections_are_never_fatal():
    """SSRF blocks are non-retryable *for the model*, not fatal for the turn."""
    provider = ScriptedProvider([tool_response(call("fetch")), text_response("ok")])
    tools = make_registry(
        FakeTool(
            "fetch",
            result=error_result("Error: internal/private URL detected: http://127.0.0.1"),
        )
    )

    result = await AgentRunner().run(
        make_spec(provider, tools, fail_on_tool_error=True)
    )

    content = tool_messages(result.messages)[0]["content"]
    assert content.startswith("Error: internal/private URL detected")
    assert "non-bypassable security boundary" in content
    # No retry hint, and the run is not aborted even under fail_on_tool_error.
    assert TOOL_ERROR_HINT not in content
    assert result.stop_reason == "completed"
    assert result.tool_events[0]["detail"].startswith("ssrf_violation: ")


# ---------------------------------------------------------------------------
# B3 — streaming increments and final content
# ---------------------------------------------------------------------------


async def test_stream_deltas_arrive_in_order_and_match_the_final_content():
    hook = RecordingHook(streaming=True)
    provider = ScriptedProvider(
        [
            ScriptedTurn(
                text_response("Hello, world!"),
                content_deltas=("Hello", ", ", "world!"),
                reasoning_deltas=("think ", "harder"),
            )
        ]
    )

    result = await AgentRunner().run(
        make_spec(provider, make_registry(FakeTool("echo")), hook=hook)
    )

    assert hook.stream_deltas == ["Hello", ", ", "world!"]
    assert "".join(hook.stream_deltas) == result.final_content == "Hello, world!"
    # Reasoning is streamed separately, incrementally, and is not part of the
    # answer. Whitespace at a segment boundary may move between increments.
    assert "".join(hook.reasoning_deltas) == "think harder"
    assert [name for name, _ in hook.events] == [
        "iteration",
        "reasoning",
        "reasoning",
        "stream",
        "stream",
        "stream",
        "stream_end",
        "after_run",
    ]
    assert ("stream_end", False) in hook.events


async def test_length_truncated_output_is_recovered_and_concatenated_in_order():
    hook = RecordingHook(streaming=True)
    provider = ScriptedProvider(
        [
            LLMResponse(content="part1 ", finish_reason="length"),
            LLMResponse(content="part2 ", finish_reason="length"),
            text_response("part3"),
        ]
    )

    result = await AgentRunner().run(
        make_spec(provider, make_registry(FakeTool("echo")), hook=hook)
    )

    assert result.final_content == "part1 part2 part3"
    assert result.stop_reason == "completed"
    # Each recovery keeps the stream open; only the last segment closes it.
    assert [value for name, value in hook.events if name == "stream_end"] == [
        True,
        True,
        False,
    ]
    recovery_prompts = [
        m for m in result.messages
        if m.get("role") == "user" and LENGTH_RECOVERY_PROMPT in str(m.get("content"))
    ]
    assert len(recovery_prompts) == 2


async def test_length_recovery_is_capped():
    """After the cap, a further truncated reply is accepted as the final answer."""
    assert _MAX_LENGTH_RECOVERIES == 3
    provider = ScriptedProvider(
        [],
        default=LLMResponse(content="chunk ", finish_reason="length"),
    )

    result = await AgentRunner().run(
        make_spec(provider, make_registry(FakeTool("echo")), max_iterations=10)
    )

    assert provider.call_count == _MAX_LENGTH_RECOVERIES + 1
    assert result.final_content == "chunk chunk chunk chunk"
    assert result.stop_reason == "completed"


async def test_blank_replies_are_retried_then_finalized():
    assert _MAX_EMPTY_RETRIES == 2
    provider = ScriptedProvider(
        [text_response("   "), text_response(""), text_response("finally")]
    )

    result = await AgentRunner().run(
        make_spec(provider, make_registry(FakeTool("echo")), max_iterations=5)
    )

    assert provider.call_count == 3
    # The last request is the finalization retry, appended to a copy only.
    assert provider.requests[-1]["messages"][-1]["content"] == FINALIZATION_RETRY_PROMPT
    assert result.final_content == "finally"
    assert result.stop_reason == "completed"
    # Blank replies never enter the transcript.
    assert [m["role"] for m in result.messages] == ["user", "assistant"]


async def test_persistently_blank_replies_end_with_a_stable_message():
    provider = ScriptedProvider([], default=text_response(""))

    result = await AgentRunner().run(
        make_spec(provider, make_registry(FakeTool("echo")), max_iterations=5)
    )

    assert result.stop_reason == "empty_final_response"
    assert result.final_content == EMPTY_FINAL_RESPONSE_MESSAGE
    assert result.error == EMPTY_FINAL_RESPONSE_MESSAGE


# ---------------------------------------------------------------------------
# B4 — tool scheduling order
# ---------------------------------------------------------------------------


async def test_serial_mode_runs_tools_strictly_one_after_another():
    trace: list[str] = []
    tools = make_registry(
        FakeTool("a", trace=trace),
        FakeTool("b", trace=trace),
    )
    provider = ScriptedProvider(
        [tool_response(call("a"), call("b")), text_response("done")]
    )

    result = await AgentRunner().run(
        make_spec(provider, tools, concurrent_tools=False)
    )

    assert trace == ["start:a", "end:a", "start:b", "end:b"]
    assert [m["name"] for m in tool_messages(result.messages)] == ["a", "b"]
    assert result.tools_used == ["a", "b"]


async def test_concurrent_mode_overlaps_concurrency_safe_tools():
    trace: list[str] = []
    tools = make_registry(
        FakeTool("a", trace=trace),
        FakeTool("b", trace=trace),
    )
    provider = ScriptedProvider(
        [tool_response(call("a"), call("b")), text_response("done")]
    )

    result = await AgentRunner().run(
        make_spec(provider, tools, concurrent_tools=True)
    )

    assert trace == ["start:a", "start:b", "end:a", "end:b"]
    # Overlapping execution must not reorder the results the model sees.
    assert [m["name"] for m in tool_messages(result.messages)] == ["a", "b"]


async def test_unsafe_tools_split_the_batch_and_run_alone():
    """A write-capable or exclusive tool is a barrier; neighbours do not join it."""
    trace: list[str] = []
    tools = make_registry(
        FakeTool("safe1", trace=trace),
        FakeTool("writer", trace=trace, read_only=False),
        FakeTool("safe2", trace=trace),
        FakeTool("safe3", trace=trace),
    )
    provider = ScriptedProvider(
        [
            tool_response(call("safe1"), call("writer"), call("safe2"), call("safe3")),
            text_response("done"),
        ]
    )

    result = await AgentRunner().run(
        make_spec(provider, tools, concurrent_tools=True)
    )

    assert trace == [
        "start:safe1",
        "end:safe1",
        "start:writer",
        "end:writer",
        "start:safe2",
        "start:safe3",
        "end:safe2",
        "end:safe3",
    ]
    assert [m["name"] for m in tool_messages(result.messages)] == [
        "safe1",
        "writer",
        "safe2",
        "safe3",
    ]


def test_batch_partitioning_is_declarative():
    """The batching rule, stated without timing: contiguous safe runs group."""
    tools = make_registry(
        FakeTool("safe1"),
        FakeTool("writer", read_only=False),
        FakeTool("exclusive", exclusive=True),
        FakeTool("safe2"),
        FakeTool("safe3"),
    )
    calls = [
        call("safe1"),
        call("writer"),
        call("exclusive"),
        call("safe2"),
        call("safe3"),
    ]
    runner = AgentRunner()
    provider = ScriptedProvider([])

    concurrent = runner._partition_tool_batches(
        make_spec(provider, tools, concurrent_tools=True), calls
    )
    serial = runner._partition_tool_batches(
        make_spec(provider, tools, concurrent_tools=False), calls
    )

    assert [[c.name for c in batch] for batch in concurrent] == [
        ["safe1"],
        ["writer"],
        ["exclusive"],
        ["safe2", "safe3"],
    ]
    assert [[c.name for c in batch] for batch in serial] == [
        ["safe1"],
        ["writer"],
        ["exclusive"],
        ["safe2"],
        ["safe3"],
    ]


# ---------------------------------------------------------------------------
# B5 — oversized tool results
# ---------------------------------------------------------------------------


async def test_oversized_result_is_truncated_with_a_stable_suffix_without_workspace():
    payload = "x" * 1_000
    provider = ScriptedProvider([tool_response(call("dump")), text_response("ok")])

    result = await AgentRunner().run(
        make_spec(
            provider,
            make_registry(FakeTool("dump", result=payload)),
            max_tool_result_chars=200,
        )
    )

    content = tool_messages(result.messages)[0]["content"]
    assert content == "x" * 200 + "\n... (truncated)"
    # Truncation is applied to the transcript itself, not only to the request.
    assert len(content) < len(payload)


async def test_oversized_result_is_offloaded_to_a_file_when_a_workspace_exists(tmp_path):
    payload = "y" * (BASELINE_MAX_TOOL_RESULT_CHARS + 4_000)
    provider = ScriptedProvider(
        [tool_response(call("dump", call_id="call_1")), text_response("ok")]
    )

    result = await AgentRunner().run(
        make_spec(
            provider,
            make_registry(FakeTool("dump", result=payload)),
            workspace=tmp_path,
            session_key="cli:direct",
        )
    )

    content = tool_messages(result.messages)[0]["content"]
    assert content.startswith("[tool output persisted]")
    assert f"Original size: {len(payload)} chars" in content
    # The model keeps a preview and a path, not the payload.
    assert len(content) < len(payload)
    saved = tmp_path / ".nanobot" / "tool-results" / safe_filename("cli:direct") / "call_1.txt"
    assert saved.read_text(encoding="utf-8") == payload


async def test_read_file_results_are_exempt_from_offload_and_truncation(tmp_path):
    """The one tool whose full output the model is expected to keep."""
    payload = "z" * (BASELINE_MAX_TOOL_RESULT_CHARS + 4_000)
    provider = ScriptedProvider([tool_response(call("read_file")), text_response("ok")])

    result = await AgentRunner().run(
        make_spec(
            provider,
            make_registry(FakeTool("read_file", result=payload)),
            workspace=tmp_path,
            session_key="cli:direct",
        )
    )

    assert tool_messages(result.messages)[0]["content"] == payload


@pytest.mark.parametrize("empty", ["", "   ", None])
async def test_empty_tool_result_becomes_an_explicit_marker(empty):
    provider = ScriptedProvider([tool_response(call("quiet")), text_response("ok")])

    result = await AgentRunner().run(
        make_spec(provider, make_registry(FakeTool("quiet", result=empty)))
    )

    assert tool_messages(result.messages)[0]["content"] == empty_tool_result_message("quiet")
