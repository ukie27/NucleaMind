"""Slash command routing and built-in handlers."""

from nucleamind.legacy.command.builtin import register_builtin_commands
from nucleamind.legacy.command.router import CommandContext, CommandRouter

__all__ = ["CommandContext", "CommandRouter", "register_builtin_commands"]
