"""nanobot 遗留隔离区的包根（`D31` 之后只剩版本号与两个仍在的再导出）。

`D31` 删掉 `legacy/{agent,cli,webui,gateway,api,sdk}` 与 `nanobot.py` 之后，
原来那张以 `Nanobot` SDK 门面为主的惰性导出表整体失效——嵌入式调用由
`nucleamind.embed` 取代（`D23`）。这里只保留仍有实现可指的两个名字。
"""

import tomllib
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .bus.runtime_events import SessionTurnPersisted
    from .runtime_context import RuntimeContextBlock, RuntimeContextProvider


def _read_pyproject_version() -> str | None:
    """Read the source-tree version when package metadata is unavailable."""
    pyproject = Path(__file__).resolve().parents[3] / "pyproject.toml"
    if not pyproject.exists():
        return None
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    return data.get("project", {}).get("version")


def _resolve_version() -> str:
    try:
        return _pkg_version("nucleamind")
    except PackageNotFoundError:
        # Source checkouts often import nanobot without installed dist-info.
        return _read_pyproject_version() or "0.3.0"


__version__ = _resolve_version()
__logo__ = "🐈"

_LAZY_EXPORTS = {
    "RuntimeContextBlock": ".runtime_context",
    "RuntimeContextProvider": ".runtime_context",
    "SessionTurnPersisted": ".bus.runtime_events",
}


def __getattr__(name: str) -> Any:
    module_path = _LAZY_EXPORTS.get(name)
    if module_path is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from importlib import import_module
    mod = import_module(module_path, __name__)
    val = getattr(mod, name)
    globals()[name] = val
    return val


__all__ = [
    "RuntimeContextBlock",
    "RuntimeContextProvider",
    "SessionTurnPersisted",
]
