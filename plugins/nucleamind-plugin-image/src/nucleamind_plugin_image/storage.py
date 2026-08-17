"""产物落盘：把图像字节写进磁盘并交出 `ArtifactRef`。

职责：决定落点、原子写入、构造产物引用。
不负责：拿到那些字节（`tool.py` / `wire.py`）、决定目录来自哪个配置键（`settings.py`）。

**为什么不用 `ctx.fs`**：它的根是实例的 **workspace**，而图落在插件自己的 **state_dir**
（或运维配置的绝对路径）——`PathGuard` 对越界与绝对路径一律拒绝，这不是缺个方法，
是两个目录树。因此本模块直接用 `pathlib`，而 manifest **如实声明 `fs:write`**，
与 `builtins/session_jsonl/` 同一条先例：门面够不着的地方，诚实声明比绕道更符合
「应用级权限的价值是让越界意图可审计」。

`D42` 给 `FileAccess` 补了 `read_bytes` / `write_bytes`——**这个插件仍然用不上它们**。
原来这段话把原因记成「没有 `write_bytes`」，那只是当时最显眼的那一半；真正的原因是落点
不在 `ctx.fs` 的根里。补完方法之后重新看一遍，才把这条分清楚。

**文件名是内容寻址的**（`image-<sha256 前 16 位>.<ext>`）。两条好处都是真的：同样的字节
永远落在同一个文件上（重跑不会堆出一堆一模一样的图），而文件名里不含 prompt——
prompt 可能很长、可能带路径分隔符、也可能包含用户不想留在文件系统上的内容。

**写走「同目录临时文件 → `fsync` → `os.replace`」**（`builtins/tools_fs/writers.py` 的同一条
路径）：替换成功之后没有可失败的步骤，因此调用方敢把成功标成 `SideEffect.OCCURRED`、
把落盘之前的失败标成 `NONE`。
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Final

from nucleamind.contracts import ArtifactRef, ErrorCode, NucleaError

from .wire import extension_for

__all__ = ["ImageStore", "SavedImage", "digest_name"]

#: 文件名里保留的摘要位数。16 个十六进制位 = 64 bit，对一台机器上的图像数量来说，
#: 碰撞概率远低于「两次生成恰好产出同样的字节」这件事本身。
_DIGEST_CHARS: Final = 16

_WRITE_FAILED: Final = "图像写入失败。"


class SavedImage:
    """一张已经落盘的图。"""

    __slots__ = ("artifact", "path", "size_bytes")

    def __init__(self, path: Path, media_type: str, size_bytes: int) -> None:
        self.path = path
        self.size_bytes = size_bytes
        self.artifact = ArtifactRef(
            # 绝对路径：产物引用要能被后续工具与用户直接使用，而**这条路径就是交付物
            # 本身**。它与 `tools_fs` 那条「越界错误里不放宿主机绝对路径」不冲突——
            # 那说的是失败诊断，这说的是成功产出。
            locator=path.as_posix(),
            media_type=media_type,
            description="生成的图像",
            size_bytes=size_bytes,
        )


def digest_name(data: bytes, media_type: str) -> str:
    """内容寻址的文件名。同样的字节恒得到同一个名字。"""
    digest = hashlib.sha256(data).hexdigest()[:_DIGEST_CHARS]
    return f"image-{digest}{extension_for(media_type)}"


class ImageStore:
    """把图像写进一个固定目录。"""

    __slots__ = ("_root",)

    def __init__(self, root: Path) -> None:
        self._root = root

    @property
    def root(self) -> Path:
        return self._root

    def save(self, data: bytes, media_type: str) -> SavedImage:
        """原子写入一张图。

        **异常约定**：写失败抛 `PERSISTENCE_WRITE_FAILED`。目录不存在时**创建它**——
        插件自己的状态目录是它的资产，为一个必然要建的目录报错没有意义。
        """
        target = self._root / digest_name(data, media_type)
        try:
            self._root.mkdir(parents=True, exist_ok=True)
            _atomic_write(target, data)
        except OSError as error:
            raise NucleaError(
                ErrorCode.PERSISTENCE_WRITE_FAILED,
                _WRITE_FAILED,
                # 只放 errno 与异常类型名，不放路径——那是宿主机信息，而这条错误会被
                # 折进模型可见的工具结果里（`D20` 的先例）。
                detail={"errno": error.errno, "reason": type(error).__name__},
            ) from error
        return SavedImage(target, media_type, len(data))


def _atomic_write(target: Path, data: bytes) -> None:
    """同目录临时文件 → `fsync` → `os.replace`。

    临时文件必须与目标**同目录**：`os.replace` 跨文件系统会失败，而临时目录与状态目录
    落在不同卷上是很常见的部署形态。
    """
    temporary = target.with_name(f"{target.name}.tmp-{os.getpid()}")
    try:
        with open(temporary, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    except OSError:
        # 清理失败不覆盖原始错误：真正要报的是写失败，而不是「清理临时文件也没成」。
        temporary.unlink(missing_ok=True)
        raise
