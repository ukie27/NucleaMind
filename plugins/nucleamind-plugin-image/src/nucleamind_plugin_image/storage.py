"""产物落盘：把图像字节写进磁盘并交出 `ArtifactRef` + `AttachmentRef`。

职责：决定落点、原子写入、构造产物与附件引用。
不负责：拿到那些字节（`tool.py` / `wire.py`）、决定目录来自哪个配置键（`settings.py`）。

**默认落点是 workspace，因此走 `ctx.fs`**（`D47` 改的）。原来图落在插件自己的
state_dir，理由记着「`ctx.fs` 的根是 workspace，那是两个目录树，不是缺个方法」——那句话
当时是对的，但它回避了真正的问题：**生成的图是用户的交付物**，而交付物属于用户的工作区，
不属于插件的私有状态。落在 workspace 里之后三件事同时成立：`ctx.fs.write_bytes()` 用得上、
`fs.read` 这类内建工具能接着处理它、
`AttachmentRef(source=WORKSPACE)` 拿得到一个**相对**路径——契约禁止附件依赖绝对路径，
那正是 `D47` 之前这些图发不出去的直接原因。

**运维仍然可以把 `dir` 配成绝对路径**，那时走 `LocalImageStore`（`pathlib`，与原来逐字
相同）。代价如实记着：**那样存下的图发不出去**，因为它给不出 workspace 相对 locator。
两个类而不是一个带分支的类：它们的写入机制、错误来源与「能不能当附件」三件事全都不同。

**文件名是内容寻址的**（`image-<sha256 前 16 位>.<ext>`）。两条好处都是真的：同样的字节
永远落在同一个文件上（重跑不会堆出一堆一模一样的图），而文件名里不含 prompt——
prompt 可能很长、可能带路径分隔符、也可能包含用户不想留在文件系统上的内容。
它顺带让 `TurnState.collect_attachments` 的按 locator 去重真的有东西可去。

**`LocalImageStore` 的写走「同目录临时文件 → `fsync` → `os.replace`」**
（`builtins/tools_fs/writers.py` 的同一条路径）：替换成功之后没有可失败的步骤，因此调用方
敢把成功标成 `SideEffect.OCCURRED`、把落盘之前的失败标成 `NONE`。`ctx.fs.write_bytes()`
在门面里做的是同一件事，因此两条路的副作用语义一致。
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Final, Protocol, runtime_checkable

from nucleamind.contracts import (
    ArtifactRef,
    AttachmentRef,
    AttachmentSource,
    ErrorCode,
    NucleaError,
)

from .wire import extension_for

__all__ = [
    "FileWriter",
    "ImageStore",
    "LocalImageStore",
    "SavedImage",
    "WorkspaceImageStore",
    "digest_name",
]

#: 文件名里保留的摘要位数。16 个十六进制位 = 64 bit，对一台机器上的图像数量来说，
#: 碰撞概率远低于「两次生成恰好产出同样的字节」这件事本身。
_DIGEST_CHARS: Final = 16

_WRITE_FAILED: Final = "图像写入失败。"


@runtime_checkable
class FileWriter(Protocol):
    """`ctx.fs` 里本插件用得到的那一个方法。

    **不直接标注 `sdk.FileAccess`**：用例要一个可注入的替身，而
    `FakePluginContext.fs` 按设计抛 `NotImplementedError`（`sdk.testing` 是冻结表面，
    为一个插件的方便去改它的语义不划算）。窄到只有一个方法，替身因此是三行。
    """

    async def write_bytes(self, path: str, data: bytes) -> None: ...


class SavedImage:
    """一张已经落盘的图。

    `locator` 是**给人和模型看的那个字符串**：workspace 模式下是相对路径，
    绝对路径模式下是绝对路径。`attachment` 只在前者有值——见模块 docstring。
    """

    __slots__ = ("artifact", "attachment", "locator", "size_bytes")

    def __init__(
        self,
        locator: str,
        media_type: str,
        size_bytes: int,
        *,
        attachment: AttachmentRef | None,
    ) -> None:
        self.locator = locator
        self.size_bytes = size_bytes
        self.attachment = attachment
        self.artifact = ArtifactRef(
            locator=locator,
            media_type=media_type,
            description="生成的图像",
            size_bytes=size_bytes,
        )


class ImageStore(Protocol):
    """落盘器。两个实现见模块 docstring。"""

    @property
    def location(self) -> str:
        """落点的可读形态，只用于诊断与文档，不参与任何判定。"""
        ...

    async def save(self, data: bytes, media_type: str) -> SavedImage: ...


def digest_name(data: bytes, media_type: str) -> str:
    """内容寻址的文件名。同样的字节恒得到同一个名字。"""
    digest = hashlib.sha256(data).hexdigest()[:_DIGEST_CHARS]
    return f"image-{digest}{extension_for(media_type)}"


class WorkspaceImageStore:
    """写进 workspace 的一个子目录（默认落点）。

    路径一律用 `/` 拼：`ctx.fs` 收的是 POSIX 形态的相对路径，而
    `AttachmentRef(source=WORKSPACE)` 的 locator 也是同一个字符串——**两者必须是同一个**，
    否则 Channel 读的和用户看到的会是两个东西。
    """

    __slots__ = ("_directory", "_files")

    def __init__(self, files: FileWriter, directory: str) -> None:
        self._files = files
        self._directory = directory.strip("/")

    @property
    def location(self) -> str:
        return f"<workspace>/{self._directory}"

    async def save(self, data: bytes, media_type: str) -> SavedImage:
        """写一张图。

        **异常约定**：门面自己抛 `PERSISTENCE_WRITE_FAILED` 或 Workspace 越界错误，
        这里**原样放行**——它们的 `detail` 比这里能补的更准确（哪个插件、哪条路径），
        再包一层只会把位置信息埋掉。
        """
        name = digest_name(data, media_type)
        path = f"{self._directory}/{name}" if self._directory else name
        await self._files.write_bytes(path, data)
        return SavedImage(
            path,
            media_type,
            len(data),
            attachment=AttachmentRef(
                source=AttachmentSource.WORKSPACE,
                locator=path,
                media_type=media_type,
                size_bytes=len(data),
                filename=name,
            ),
        )


class LocalImageStore:
    """写进一个绝对路径目录（运维显式配置 `dir` 时）。

    **它交不出附件**：`AttachmentRef` 按契约拒绝绝对路径与上跳段，而这里除了绝对路径
    什么都没有。这不是遗漏——把宿主机绝对路径交给一个聊天平台 Channel 去读，正是那条
    契约要挡的事。用户配了它就意味着接受「图只在磁盘上」。
    """

    __slots__ = ("_root",)

    def __init__(self, root: Path) -> None:
        self._root = root

    @property
    def location(self) -> str:
        return self._root.as_posix()

    @property
    def root(self) -> Path:
        return self._root

    async def save(self, data: bytes, media_type: str) -> SavedImage:
        """原子写入一张图。

        **异常约定**：写失败抛 `PERSISTENCE_WRITE_FAILED`。目录不存在时**创建它**——
        运维指定的落点是他的资产，为一个必然要建的目录报错没有意义。
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
        return SavedImage(target.as_posix(), media_type, len(data), attachment=None)


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
