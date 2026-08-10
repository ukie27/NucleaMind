"""Message bus module for decoupled channel-agent communication."""

from nucleamind.legacy.bus.events import InboundMessage, OutboundMessage
from nucleamind.legacy.bus.queue import MessageBus

__all__ = ["MessageBus", "InboundMessage", "OutboundMessage"]
