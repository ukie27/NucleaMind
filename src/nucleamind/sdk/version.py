"""SDK 版本与兼容判定（技术方案 §7.6，需求 `SDK-005`、`CMP-001`）。

职责：导出 `SDK_VERSION`，并按 PEP 440 判定一个插件声明的 `sdk_range` 是否兼容当前 SDK。
不负责：决定不兼容时怎么办（拒绝加载还是记入报告，由 `D27` 的两阶段加载按 `critical`
判定）、也不负责主程序版本——SDK 版本与发行版本独立演进。

**当前是 1.1**。§7.6 的兼容承诺从 `1.0.0`（`D42`）起算：minor 只允许新增、移除或语义
变更必须 major、当前 major 的最后一个 minor 发布后至少维护 6 个月。

**`1.1.0` 是 `D45` 的 minor 新增**，四项全部只增不改：`contracts.OpaqueBlock`、
`ChunkKind.OPAQUE`、`ModelMessage.provider_blocks` / `ModelResponse.provider_blocks`、
`ModelChunk.block`。想用它们的插件把 `sdk_range` 写成 `">=1.1,<2.0"`——`contracts` 虽然
不由本模块导出（`R4` 让插件直接 import 它），`sdk_range` 仍然是「我需要多新的宿主」
唯一的声明处。**声明 `">=1.0"` 的插件一个字都不用改**，那正是 minor 的含义。

**为什么是这一刻。** 0.x 那段时间的理由是「Kernel 尚未落地，宣布 1.0 等于承诺一个还没有
被任何实现验证过的表面」，条件写的是「`D30` 插件里程碑达成后」。`D30` 之后又过了十一个
官方插件（`D31`–`D40`）；`D41` 把它们全部纳入类型检查、`D42` 补齐了它们撞出来的四个缺口
（`ToolResult.trust`、`FileAccess` 的二进制读写、`HttpAccess` 的字节上界、
`EventHandler` 接受同步 handler）。**表面现在有十一个实现验证过它，而最后一轮修补也已
落地**——再往后拖，1.0 就只是一个不断推迟的日期而不是一个判据。

如实记着一件事：那四个缺口是 `D41`/`D42` 才发现的，也就是说在此之前「表面已经稳定」
这个判断有过一次误判。1.0 的承诺是**从现在**起不再破坏性变更，不是追认此前每一版都对。
"""

from __future__ import annotations

from typing import Final

from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version

from nucleamind.contracts import ErrorCode, NucleaError

__all__ = ["SDK_VERSION", "is_compatible", "parse_sdk_range"]

#: 当前 SDK 版本（语义化版本，PEP 440 可解析）。插件用 `sdk_range` 声明兼容范围。
SDK_VERSION: Final = "1.1.0"

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
            "sdk_range 不是合法的 PEP 440 版本范围（例如 \">=1.0,<2.0\"）。",
            detail={"field": "sdk_range", "sdk_range": sdk_range},
        ) from exc


def is_compatible(sdk_range: str, *, sdk_version: str = SDK_VERSION) -> bool:
    """当前 SDK 是否落在插件声明的兼容范围内（`SDK-005`）。

    `prereleases=True`：预发布版本必须能被 `>=1.0,<2.0` 这类范围接纳，否则用
    `1.1.0rc1` 跑一遍插件矩阵就得先改所有插件的 manifest。注意这不改变 PEP 440 的排序
    事实——`2.0.0rc1` 依然小于 `2.0.0`，因此它不满足 `>=2.0`。

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
