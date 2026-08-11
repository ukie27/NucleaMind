"""SDK 版本与兼容判定（技术方案 §7.6，需求 `SDK-005`、`CMP-001`）。

职责：导出 `SDK_VERSION`，并按 PEP 440 判定一个插件声明的 `sdk_range` 是否兼容当前 SDK。
不负责：决定不兼容时怎么办（拒绝加载还是记入报告，由 `D27` 的两阶段加载按 `critical`
判定）、也不负责主程序版本——SDK 版本与发行版本独立演进。

**当前是 0.x**：§7.6 的兼容承诺（minor 只允许新增、移除或语义变更必须 major、当前
major 的最后一个 minor 发布后至少维护 6 个月）从 `1.0.0` 起算。Kernel 尚未落地，此刻
宣布 1.0 等于承诺一个还没有被任何实现验证过的表面。`D30` 插件里程碑达成后再发 1.0。
"""

from __future__ import annotations

from typing import Final

from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version

from nucleamind.contracts import ErrorCode, NucleaError

__all__ = ["SDK_VERSION", "is_compatible", "parse_sdk_range"]

#: 当前 SDK 版本（语义化版本，PEP 440 可解析）。插件用 `sdk_range` 声明兼容范围。
SDK_VERSION: Final = "0.1.0"

#: 解析好的当前版本。模块级常量：`is_compatible()` 在阶段 A 的校验循环里逐个插件调用，
#: 每次重新解析同一个字面量没有意义。
_CURRENT: Final = Version(SDK_VERSION)


def parse_sdk_range(sdk_range: str) -> SpecifierSet:
    """把 `sdk_range` 解析为 PEP 440 specifier 集合。

    形状非法抛 `PLUGIN_MANIFEST_UNSUPPORTED` 并带上原始串——`CMP-001` 要求缺失或非法的
    兼容字段直接判定为校验失败并指出位置，不做兜底猜测（比如「解析不了就当全兼容」，
    那正好让最该被拦下的插件通过）。
    """
    try:
        return SpecifierSet(sdk_range)
    except InvalidSpecifier as exc:
        raise NucleaError(
            ErrorCode.PLUGIN_MANIFEST_UNSUPPORTED,
            "sdk_range 不是合法的 PEP 440 版本范围（例如 \">=0.1,<0.2\"）。",
            detail={"field": "sdk_range", "sdk_range": sdk_range},
        ) from exc


def is_compatible(sdk_range: str, *, sdk_version: str = SDK_VERSION) -> bool:
    """当前 SDK 是否落在插件声明的兼容范围内（`SDK-005`）。

    `prereleases=True`：0.x 阶段的预发布版本必须能被 `>=0.1,<0.2` 这类范围接纳，
    否则用 `0.1.5rc1` 跑一遍插件矩阵就得先改所有插件的 manifest。注意这不改变 PEP 440
    的排序事实——`0.2.0rc1` 依然小于 `0.2.0`，因此它不满足 `>=0.2`。

    `sdk_version` 只为测试留出注入点——生产路径永远用当前 SDK 版本，不接受调用方
    「换一个版本再试试」。
    """
    specifier = parse_sdk_range(sdk_range)
    version = _CURRENT if sdk_version == SDK_VERSION else _parse_version(sdk_version)
    return specifier.contains(version, prereleases=True)


def _parse_version(value: str) -> Version:
    try:
        return Version(value)
    except InvalidVersion as exc:
        raise NucleaError(
            ErrorCode.PLUGIN_MANIFEST_UNSUPPORTED,
            "版本号不符合 PEP 440。",
            detail={"field": "version", "version": value},
        ) from exc
