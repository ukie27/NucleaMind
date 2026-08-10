"""Agent core module."""

from nucleamind.legacy.agent.context import ContextBuilder
from nucleamind.legacy.agent.hook import (
    AgentHook,
    AgentHookContext,
    AgentRunHookContext,
    AgentTurnHookContext,
    AgentTurnHookFactory,
    CompositeHook,
)
from nucleamind.legacy.agent.loop import AgentLoop
from nucleamind.legacy.agent.memory import MemoryStore
from nucleamind.legacy.agent.skills import SkillsLoader
from nucleamind.legacy.agent.subagent import SubagentManager

__all__ = [
    "AgentHook",
    "AgentHookContext",
    "AgentRunHookContext",
    "AgentTurnHookContext",
    "AgentTurnHookFactory",
    "AgentLoop",
    "CompositeHook",
    "ContextBuilder",
    "MemoryStore",
    "SkillsLoader",
    "SubagentManager",
]
