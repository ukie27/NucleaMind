"""插件发现：两条显式来源产出候选清单（技术方案 §7.1，需求 `DST-002`、`NFR-401`）。

职责：枚举 entry point 组 `nucleamind.plugins` 与配置给出的搜索路径，产出**候选**
（id + 来源 + 位置）；并在调用方决定要它时，取回那份 manifest 的**原始数据**。
不负责：校验 manifest（`sdk/manifest.py`，且 `R2` 禁止 `kernel/` import `sdk/`）、
决定谁被启用（那是配置，由 `runtime/inventory.py` 判）、导入 `setup`、注册能力
（`builtin_loader.py` 与 `D27`）。

**发现与启用分离靠「id 先于 manifest 可知」成立**（§7.1）。三条来源的候选 id 分别是
entry point 的 name、目录名与 `.py` 文件名——都不需要读、更不需要导入 manifest。因此
「未启用的插件不被导入」不是一条要人遵守的纪律，而是**没有路径**：调用方在
`read_candidate()` 之前就能按 `plugins.enabled` 把候选筛掉。代价是 entry point 的 name
必须与 manifest 里的 `id` 相等，对不上即失败（由 `runtime/` 判）——静默以 manifest 为准
会让启用清单指不到东西。

**不做 site-packages 全量扫描、不做目录自动加载**（§7.1 的两条「不采用」）：启动开销
不可控，且 NucleaMind 要的是「安装 ≠ 启用」。

**也不扫描 `InstanceLayout.plugins_dir`**：那是插件的**状态**目录
（`<instance>/plugins/<id>/`），把它同时当成代码来源，会让一个只写了状态的子目录看起来
像一个装错了的插件。搜索路径只有 `plugins.search_paths` 一条来源。

**读一份 manifest 可能要 import 一个第三方模块**（entry point 与单文件两种来源）。
§7.2 的硬约束是「导入 manifest 模块无副作用且廉价」，本模块只能如实地把那次导入放在
一处、并让它的失败可归因，挡不住模块里写的任何东西。
"""

from __future__ import annotations

import importlib
import importlib.util
import tomllib
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Final

from nucleamind.contracts import ErrorCode, NucleaError

__all__ = [
    "ENTRY_POINT_GROUP",
    "MANIFEST_ATTRIBUTE",
    "MANIFEST_FILENAME",
    "Discovery",
    "EntryPointLister",
    "PluginCandidate",
    "SourceKind",
    "discover",
    "installed_entry_points",
    "read_candidate",
]

#: entry point 组名（§7.1）。`pyproject.toml` 的 `[project.entry-points."nucleamind.plugins"]`
#: 里那个字符串，`D00` 建仓时就已经登记。
ENTRY_POINT_GROUP: Final = "nucleamind.plugins"

#: 目录形态插件的 manifest 文件名。
MANIFEST_FILENAME: Final = "plugin.toml"

#: entry point 与单文件插件里那个 manifest 对象的属性名（entry point 可以指定别的，
#: 单文件不行——文件本身没有第二个地方写这个约定）。
MANIFEST_ATTRIBUTE: Final = "MANIFEST"

#: `"pkg.module:MANIFEST"` 的分隔符，与 `builtin_loader._SETUP_SEPARATOR` 同形。
_ATTRIBUTE_SEPARATOR: Final = ":"

#: 扫描目录时跳过的前缀：`.git`、`__pycache__`、`_scratch` 之类不是插件。
_SKIPPED_PREFIXES: Final = (".", "_")


class SourceKind(StrEnum):
    """候选来自哪一条来源。三者读 manifest 的代价不同，诊断要说得出是哪一种。"""

    ENTRY_POINT = "entry_point"
    DIRECTORY = "directory"
    MODULE_FILE = "module_file"


@dataclass(frozen=True, slots=True)
class PluginCandidate:
    """一个候选插件：**在读 manifest 之前**就已知的全部事实。

    `plugin_id` 来自来源本身（entry point name / 目录名 / 文件名），不是从 manifest 读的
    ——这正是启用判定能发生在导入之前的原因。`location` 是取回 manifest 需要的那个串：
    entry point 是 `"pkg.module:MANIFEST"`，其余两种是文件系统路径。
    """

    plugin_id: str
    kind: SourceKind
    location: str

    @property
    def origin(self) -> str:
        """诊断里指认「这份声明是哪来的」的那一行（`parse_manifest(origin=...)` 用）。"""
        if self.kind is SourceKind.ENTRY_POINT:
            return f"{ENTRY_POINT_GROUP}:{self.plugin_id} -> {self.location}"
        return self.location


@dataclass(frozen=True, slots=True)
class Discovery:
    """一次发现的产物：候选清单与**发现阶段**的失败。

    失败在这里就已经可能发生（搜索路径不存在、跨来源 id 撞车），与「manifest 校验失败」
    分开：前者调用方改的是配置，后者改的是插件。
    """

    candidates: tuple[PluginCandidate, ...] = ()
    failures: tuple[NucleaError, ...] = ()


#: 「已安装的 entry point 有哪些」。做成可注入的：真实实现要读整个环境的包元数据，
#: 而测试需要在不安装任何东西的前提下断言「20 个未启用插件不产生导入」。
EntryPointLister = Callable[[], Sequence[tuple[str, str]]]


def installed_entry_points() -> tuple[tuple[str, str], ...]:
    """当前环境里 `nucleamind.plugins` 组的 `(name, value)`。

    **不 `load()`**：`importlib.metadata` 的 `EntryPoint` 拿到的是元数据，`name` 与
    `value` 都是字符串，读它们不导入任何插件模块。这一条是「未启用即零开销」的地基。
    """
    from importlib.metadata import entry_points

    return tuple((point.name, point.value) for point in entry_points(group=ENTRY_POINT_GROUP))


def _scan_directory(root: Path, failures: list[NucleaError]) -> list[PluginCandidate]:
    """扫一个搜索路径下的直接子项。不递归——插件不藏在孙目录里。"""
    try:
        children = sorted(root.iterdir(), key=lambda item: item.name)
    except OSError as exc:
        failures.append(
            NucleaError(
                ErrorCode.CONFIG_INVALID,
                "插件搜索路径无法读取。",
                detail={"path": str(root), "reason": type(exc).__name__},
            )
        )
        return []

    found: list[PluginCandidate] = []
    for child in children:
        if child.name.startswith(_SKIPPED_PREFIXES):
            continue
        if child.is_dir() and (child / MANIFEST_FILENAME).is_file():
            found.append(
                PluginCandidate(
                    plugin_id=child.name,
                    kind=SourceKind.DIRECTORY,
                    location=str(child / MANIFEST_FILENAME),
                )
            )
        elif child.is_file() and child.suffix == ".py":
            found.append(
                PluginCandidate(
                    plugin_id=child.stem,
                    kind=SourceKind.MODULE_FILE,
                    location=str(child),
                )
            )
    return found


def discover(
    *,
    search_paths: Sequence[Path] = (),
    entry_points: EntryPointLister = installed_entry_points,
) -> Discovery:
    """枚举两条来源，产出候选清单。**不读、不导入任何 manifest。**

    顺序是「entry point 在前、搜索路径在后」，但那只是列表顺序：加载顺序永不决定谁生效
    （`EDG-102`），覆盖只由 manifest 的 `overrides` 决定。

    **跨来源重复 id 时各方都不生效**并记一条失败——与 `kernel/registry` 的冲突语义一致：
    选任何一边都是替用户做决定，而这里连「哪一边更新」都无从判断。

    **搜索路径不存在是失败而不是跳过**：那是用户在配置里显式写下的一条路径，静默忽略会让
    「我的插件怎么没被发现」查不出原因。
    """
    failures: list[NucleaError] = []
    found: list[PluginCandidate] = [
        PluginCandidate(plugin_id=name, kind=SourceKind.ENTRY_POINT, location=value)
        for name, value in entry_points()
    ]
    for raw in search_paths:
        path = Path(raw)
        if not path.is_dir():
            failures.append(
                NucleaError(
                    ErrorCode.CONFIG_INVALID,
                    "插件搜索路径不存在或不是目录。",
                    detail={"path": str(path)},
                )
            )
            continue
        found.extend(_scan_directory(path, failures))

    counts: dict[str, int] = {}
    for candidate in found:
        counts[candidate.plugin_id] = counts.get(candidate.plugin_id, 0) + 1
    for plugin_id, count in sorted(counts.items()):
        if count > 1:
            failures.append(
                NucleaError(
                    ErrorCode.PLUGIN_REGISTRATION_CONFLICT,
                    "同一个插件 id 出现在多条来源里；两边都不会被加载。",
                    detail={
                        "plugin_id": plugin_id,
                        "origins": [c.origin for c in found if c.plugin_id == plugin_id],
                    },
                )
            )

    candidates = tuple(item for item in found if counts[item.plugin_id] == 1)
    return Discovery(candidates=candidates, failures=tuple(failures))


def _fail_read(candidate: PluginCandidate, message: str, **detail: object) -> NucleaError:
    return NucleaError(
        ErrorCode.PLUGIN_LOAD_FAILED,
        message,
        detail={
            "plugin_id": candidate.plugin_id,
            "origin": candidate.origin,
            "source": candidate.kind.value,
            **detail,
        },
    )


def _read_toml(candidate: PluginCandidate) -> object:
    path = Path(candidate.location)
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except OSError as exc:
        raise _fail_read(candidate, "无法读取 plugin.toml。", reason=type(exc).__name__) from exc
    except tomllib.TOMLDecodeError as exc:
        raise NucleaError(
            ErrorCode.PLUGIN_MANIFEST_UNSUPPORTED,
            "plugin.toml 不是合法的 TOML。",
            detail={
                "plugin_id": candidate.plugin_id,
                "origin": candidate.origin,
                "reason": str(exc),
            },
        ) from exc


def _read_module_file(candidate: PluginCandidate) -> object:
    """执行一个单文件插件并取出它的 `MANIFEST`。

    用 `spec_from_file_location` 而不是改 `sys.path`：搜索路径是用户随手指的目录，把它
    塞进导入路径会让那里的任何 `.py` 都能被后续 `import` 命中，那是发现机制不该有的
    副作用。模块也**不登记进 `sys.modules`**——单文件插件没有相对导入，登记只会让
    「未启用即未导入」的断言变得难以陈述。
    """
    path = Path(candidate.location)
    spec = importlib.util.spec_from_file_location(f"nucleamind_plugin_{path.stem}", path)
    if spec is None or spec.loader is None:
        raise _fail_read(candidate, "无法为单文件插件建立导入规格。")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        # 第三方模块在导入期抛什么都可能。**只放类型名不放消息**——与 `D13` 的命令
        # handler 同一条理由：异常文本可能带着凭据。只捕 `Exception`，取消要放行。
        raise _fail_read(candidate, "导入插件模块失败。", exception=type(exc).__name__) from exc
    return _attribute_of(candidate, module, MANIFEST_ATTRIBUTE)


def _read_entry_point(candidate: PluginCandidate) -> object:
    module_name, separator, attribute = candidate.location.partition(_ATTRIBUTE_SEPARATOR)
    if not separator or not module_name or not attribute:
        raise _fail_read(candidate, 'entry point 必须写成 "pkg.module:MANIFEST"。')
    try:
        module = importlib.import_module(module_name)
    except Exception as exc:
        raise _fail_read(
            candidate, "导入插件模块失败。", module=module_name, exception=type(exc).__name__
        ) from exc
    return _attribute_of(candidate, module, attribute)


def _attribute_of(candidate: PluginCandidate, module: object, attribute: str) -> object:
    found = getattr(module, attribute, None)
    if found is None:
        raise _fail_read(candidate, "插件模块里没有 manifest 对象。", attribute=attribute)
    return found


def read_candidate(candidate: PluginCandidate) -> object:
    """取回这个候选的 manifest 原始数据。

    交出的是 `object` 而不是某个 manifest 类型：`R2` 禁止 `kernel/` 认识
    `sdk.PluginManifest`，而这里本来也只搬运不解释。调用方（`runtime/inventory.py`）
    收到的要么是一份 `Mapping`（`plugin.toml`），要么是插件模块里那个对象。

    **异常约定**：读不到、导不进、没有 manifest 对象一律 `PLUGIN_LOAD_FAILED`；
    TOML 本身语法错误是 `PLUGIN_MANIFEST_UNSUPPORTED`（那是声明的问题，不是加载的问题）。
    两者都带 `plugin_id` 与 `origin`。**取消语义**：同步函数，不检查取消——
    发现发生在启动期，且每一步都是有界的本地 IO。
    """
    match candidate.kind:
        case SourceKind.DIRECTORY:
            return _read_toml(candidate)
        case SourceKind.MODULE_FILE:
            return _read_module_file(candidate)
        case SourceKind.ENTRY_POINT:
            return _read_entry_point(candidate)
