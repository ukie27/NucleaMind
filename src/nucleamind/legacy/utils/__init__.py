"""Utility functions for nanobot."""

from __future__ import annotations

import sys
from importlib import import_module
from types import ModuleType

from nucleamind.legacy.utils.helpers import ensure_dir
from nucleamind.legacy.utils.path import abbreviate_path

__all__ = ["ensure_dir", "abbreviate_path"]


class _LazyModuleAlias(ModuleType):
    def __init__(self, name: str, target: str) -> None:
        super().__init__(name)
        self.__dict__["_target"] = target

    def _load(self) -> ModuleType:
        module = import_module(self.__dict__["_target"])
        sys.modules[self.__name__] = module
        return module

    def __getattr__(self, name: str) -> object:
        return getattr(self._load(), name)

    def __dir__(self) -> list[str]:
        return sorted(set(super().__dir__()) | set(dir(self._load())))


# `D31` 删掉 webui 后端与 session/webui_turns.py 之后，这张别名表里三条全部
# 指向不存在的模块，因此清空。保留这张表本身是为了下一个搬家的模块。
_LEGACY_MODULE_ALIASES: dict[str, str] = {}

for _legacy_name, _target_name in _LEGACY_MODULE_ALIASES.items():
    sys.modules.setdefault(
        f"{__name__}.{_legacy_name}",
        _LazyModuleAlias(f"{__name__}.{_legacy_name}", _target_name),
    )
