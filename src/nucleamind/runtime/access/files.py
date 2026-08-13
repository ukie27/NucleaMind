"""`ctx.fs` 的生产实现：读写分离的 workspace 文件门面（`sdk.FileAccess`、`NFR-302`）。

职责：`GuardedFileAccess`——按 `fs:read` / `fs:write` **分别**判定，把路径过 `PathGuard`，
再在线程里做实际 IO。
不负责：路径判定本身（`paths.py`）、判断门面本身能不能拿到（`RuntimePluginContext.fs`）、
给内建提供文件工具（那是 `builtins/tools_fs/`，它如实声明权限后直接用 `pathlib`）。

**读写是两条独立授权**（`NFR-302`「读写分离的 Workspace 能力边界」）：一个只声明 `fs:read`
的插件拿得到门面，但 `write_text()` 抛 `PERMISSION_DENIED`；两种权限的 `target` 也各自
收窄，因此「可以读整个 workspace、只能写 `cache/`」是表达得出来的。

**IO 全部经 `asyncio.to_thread`**：插件读的可能是几 MB 的文件，在事件循环里同步读它会卡住
同一实例的其他 turn（`D17` 的同一条理由）。

**写是原子的**：同目录临时文件 → `fsync` → `os.replace`。契约写死「不得留下半份文件」，
而替换成功之后没有可失败的步骤。
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from nucleamind.contracts import ErrorCode, NucleaError, PermissionKind
from nucleamind.kernel.plugins import PluginGrants

from .paths import PathGuard

__all__ = ["GuardedFileAccess"]


class GuardedFileAccess:
    """`FileAccess` 的生产实现。结构化满足契约，不继承任何宿主基类。"""

    __slots__ = ("_plugin_id", "_read", "_write")

    def __init__(self, root: Path, *, grants: PluginGrants, plugin_id: str) -> None:
        self._plugin_id = plugin_id
        self._read = (
            PathGuard(root, allowed=grants.targets(PermissionKind.FS_READ))
            if grants.allows(PermissionKind.FS_READ)
            else None
        )
        self._write = (
            PathGuard(root, allowed=grants.targets(PermissionKind.FS_WRITE))
            if grants.allows(PermissionKind.FS_WRITE)
            else None
        )

    async def read_text(self, path: str) -> str:
        target = self._guard(self._read, PermissionKind.FS_READ).resolve(path)
        return await asyncio.to_thread(self._read_sync, target, path)

    async def write_text(self, path: str, content: str) -> None:
        target = self._guard(self._write, PermissionKind.FS_WRITE).resolve(path)
        await asyncio.to_thread(self._write_sync, target, path, content)

    async def list_dir(self, path: str) -> tuple[str, ...]:
        target = self._guard(self._read, PermissionKind.FS_READ).resolve(path)
        return await asyncio.to_thread(self._list_sync, target, path)

    # ------------------------------------------------------------------ 同步体

    def _read_sync(self, target: Path, shown: str) -> str:
        try:
            return target.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            raise self._read_failed(shown, exc) from exc

    def _write_sync(self, target: Path, shown: str, content: str) -> None:
        temp = target.with_name(f"{target.name}.{os.getpid()}.tmp")
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            with open(temp, "wb") as handle:  # noqa: PTH123
                handle.write(content.encode("utf-8"))
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, target)
        except OSError as exc:
            temp.unlink(missing_ok=True)
            raise NucleaError(
                ErrorCode.PERSISTENCE_WRITE_FAILED,
                "写入失败。",
                detail={"plugin": self._plugin_id, "path": shown, "os_error": type(exc).__name__},
            ) from exc

    def _list_sync(self, target: Path, shown: str) -> tuple[str, ...]:
        try:
            return tuple(sorted(entry.name for entry in target.iterdir()))
        except OSError as exc:
            raise self._read_failed(shown, exc) from exc

    # ------------------------------------------------------------------ 判定

    def _guard(self, guard: PathGuard | None, kind: PermissionKind) -> PathGuard:
        if guard is None:
            raise NucleaError(
                ErrorCode.PERMISSION_DENIED,
                "插件未被授予该权限。",
                detail={"plugin": self._plugin_id, "permission": kind.value},
            )
        return guard

    def _read_failed(self, shown: str, exc: OSError) -> NucleaError:
        """`detail` 里只放**插件自己给的**那个相对串与异常类型名。

        宿主机的绝对路径与操作系统的错误文本都不进去：前者是布局泄漏，后者在某些平台上
        会把完整路径拼进消息里。
        """
        return NucleaError(
            ErrorCode.PERSISTENCE_READ_FAILED,
            "读取失败。",
            detail={"plugin": self._plugin_id, "path": shown, "os_error": type(exc).__name__},
        )
