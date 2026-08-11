"""Behavior baseline for ``legacy/agent/loop.py`` (D07).

``AgentLoop`` is the product layer around ``AgentRunner``: it decides the run
budget, the tool-error policy, and what happens to a turn's messages
afterwards. The runner baseline (``test_runner_behavior.py``) pins the loop
mechanics; this file pins the decisions the loop makes *about* that run, i.e.
the parts ``D14``'s orchestrator inherits rather than ``D09``'s engine.

Everything here is driven through ``AgentLoop._run_agent_loop`` — the same
entry ``_dispatch`` uses — so the assertions survive refactoring inside the
loop.
"""

from __future__ import annotations

from typing import Any

import pytest

from nucleamind.legacy.agent.loop import AgentLoop
from nucleamind.legacy.agent.runner import AgentRunResult, AgentRunSpec
from nucleamind.legacy.bus.queue import MessageBus
from nucleamind.legacy.config.schema import AgentDefaults

from ._support import (
    FakeTool,
    ScriptedProvider,
    call,
    error_result,
    make_registry,
    text_response,
    tool_messages,
    tool_response,
)


def make_loop(tmp_path, provider: ScriptedProvider, **kwargs: Any) -> AgentLoop:
    return AgentLoop(
        bus=MessageBus(),
        provider=provider,  # type: ignore[arg-type]
        workspace=tmp_path,
        model="test-model",
        **kwargs,
    )


# ---------------------------------------------------------------------------
# What the loop asks the runner for
# ---------------------------------------------------------------------------


async def test_loop_configures_the_run_from_its_own_limits(tmp_path):
    provider = ScriptedProvider([text_response("done")])
    loop = make_loop(tmp_path, provider, max_iterations=7, max_tool_result_chars=1234)
    captured: list[AgentRunSpec] = []

    async def capture(spec: AgentRunSpec) -> AgentRunResult:
        captured.append(spec)
        return AgentRunResult(final_content="done", messages=list(spec.initial_messages))

    loop.runner.run = capture  # type: ignore[method-assign]

    await loop._run_agent_loop([{"role": "user", "content": "hi"}], runtime=loop.llm_runtime())

    spec = captured[0]
    assert spec.max_iterations == 7
    assert spec.max_tool_result_chars == 1234
    # A user-facing turn always allows concurrent tool batches...
    assert spec.concurrent_tools is True
    # ...and never aborts on a tool error, even though the configuration
    # default is the opposite. Only sub-agent runs honour that default.
    assert spec.fail_on_tool_error is False
    assert AgentDefaults().fail_on_tool_error is True
    assert loop.subagents.fail_on_tool_error is True
    assert spec.workspace == tmp_path
    assert spec.error_message == "Sorry, I encountered an error calling the AI model."


def test_loop_limits_default_to_the_configured_agent_defaults(tmp_path):
    defaults = AgentDefaults()
    loop = make_loop(tmp_path, ScriptedProvider([]))

    assert loop.max_iterations == defaults.max_tool_iterations == 200
    assert loop.max_tool_result_chars == defaults.max_tool_result_chars == 16_000


# ---------------------------------------------------------------------------
# What the loop returns
# ---------------------------------------------------------------------------


async def test_completed_tool_turn_reports_content_tools_and_transcript(tmp_path):
    provider = ScriptedProvider(
        [tool_response(call("echo", value="x")), text_response("all done")]
    )
    loop = make_loop(tmp_path, provider)
    tools = make_registry(FakeTool("echo"))

    final_content, tools_used, messages, stop_reason, had_injections = (
        await loop._run_agent_loop(
            [{"role": "user", "content": "please echo"}],
            runtime=loop.llm_runtime(),
            tools=tools,
        )
    )

    assert final_content == "all done"
    assert tools_used == ["echo"]
    assert stop_reason == "completed"
    assert had_injections is False
    assert [m["role"] for m in messages] == ["user", "assistant", "tool", "assistant"]


async def test_tool_failure_does_not_end_the_users_turn(tmp_path):
    """The loop's ``fail_on_tool_error=False`` choice, observed end to end."""
    provider = ScriptedProvider(
        [tool_response(call("broken")), text_response("recovered from that")]
    )
    loop = make_loop(tmp_path, provider)
    tools = make_registry(FakeTool("broken", result=error_result("Error: disk on fire")))

    final_content, tools_used, messages, stop_reason, _ = await loop._run_agent_loop(
        [{"role": "user", "content": "go"}],
        runtime=loop.llm_runtime(),
        tools=tools,
    )

    assert stop_reason == "completed"
    assert final_content == "recovered from that"
    assert tools_used == []
    assert "Error: disk on fire" in tool_messages(messages)[0]["content"]


async def test_budget_exhaustion_is_pushed_through_the_stream(tmp_path):
    """A streaming channel must not be left with an empty card."""
    provider = ScriptedProvider([], default=tool_response(call("echo")))
    loop = make_loop(tmp_path, provider, max_iterations=2)
    streamed: list[str] = []
    stream_ends: list[bool] = []

    async def on_stream(delta: str) -> None:
        streamed.append(delta)

    async def on_stream_end(*, resuming: bool = False, **_kwargs: Any) -> None:
        stream_ends.append(resuming)

    final_content, _, _, stop_reason, _ = await loop._run_agent_loop(
        [{"role": "user", "content": "loop forever"}],
        None,
        on_stream,
        on_stream_end,
        runtime=loop.llm_runtime(),
        tools=make_registry(FakeTool("echo")),
    )

    assert stop_reason == "max_iterations"
    assert final_content
    assert streamed[-1] == final_content
    assert stream_ends[-1] is False


async def test_model_error_is_surfaced_as_an_error_turn(tmp_path, monkeypatch):
    """The wall-clock cap comes from ``NANOBOT_LLM_TIMEOUT_S`` when unset per turn."""
    monkeypatch.setenv("NANOBOT_LLM_TIMEOUT_S", "0.05")
    provider = ScriptedProvider([text_response("nothing here")], delay_s=0.5)
    loop = make_loop(tmp_path, provider)

    final_content, _, _, stop_reason, _ = await loop._run_agent_loop(
        [{"role": "user", "content": "hi"}],
        runtime=loop.llm_runtime(),
        tools=make_registry(FakeTool("echo")),
    )

    assert stop_reason == "error"
    assert final_content == "Error calling LLM: timed out after 0.05s"


# ---------------------------------------------------------------------------
# What the loop persists
# ---------------------------------------------------------------------------


async def test_persisted_tool_results_are_truncated_again_on_save(tmp_path):
    """Truncation is enforced at the persistence boundary, not only in-flight."""
    loop = make_loop(tmp_path, ScriptedProvider([]), max_tool_result_chars=200)
    session = loop.sessions.get_or_create("cli:direct")
    payload = "x" * 1_000
    messages = [
        {"role": "user", "content": "go"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "dump", "arguments": "{}"},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "call_1", "name": "dump", "content": payload},
        {"role": "assistant", "content": "done"},
    ]

    loop._save_turn(session, messages, skip=0)

    saved = [m for m in session.messages if m.get("role") == "tool"]
    assert saved[0]["content"] == "x" * 200 + "\n... (truncated)"


async def test_orphan_tool_results_are_dropped_on_save(tmp_path):
    """A tool result with no declared call would corrupt later provider requests."""
    loop = make_loop(tmp_path, ScriptedProvider([]))
    session = loop.sessions.get_or_create("cli:direct")

    loop._save_turn(
        session,
        [
            {"role": "user", "content": "go"},
            {"role": "tool", "tool_call_id": "call_missing", "name": "dump", "content": "x"},
            {"role": "assistant", "content": "done"},
        ],
        skip=0,
    )

    assert [m["role"] for m in session.messages] == ["user", "assistant"]


@pytest.mark.parametrize(
    ("role", "content"),
    [("assistant", ""), ("assistant", None)],
)
async def test_empty_assistant_messages_never_enter_history(tmp_path, role, content):
    loop = make_loop(tmp_path, ScriptedProvider([]))
    session = loop.sessions.get_or_create("cli:direct")

    loop._save_turn(
        session,
        [
            {"role": "user", "content": "go"},
            {"role": role, "content": content},
        ],
        skip=0,
    )

    assert [m["role"] for m in session.messages] == ["user"]
