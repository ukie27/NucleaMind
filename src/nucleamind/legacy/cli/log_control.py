"""Runtime log visibility controls shared by CLI commands."""

from loguru import logger

__all__ = ["_set_nanobot_logs"]


def _set_nanobot_logs(enabled: bool) -> None:
    if enabled:
        logger.enable("nucleamind.legacy")
    else:
        logger.disable("nucleamind.legacy")
