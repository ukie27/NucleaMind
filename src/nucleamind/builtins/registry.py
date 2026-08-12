"""内建能力的静态清单（技术方案 §7.1、§8）。

职责：以 `BUILTIN_MANIFESTS` 声明全部内建能力的 manifest——这是内建能力**唯一**的发现来源。
不负责：导入任何 `setup` 实现、决定加载顺序、判定权限、注册能力本身。

**为什么现在是空元组**：`D17`–`D22` 还没落地，而 `PluginManifest` 拒绝
`capabilities=()`（`sdk/manifest.py` 的校验），所以放一条占位 manifest 根本构造不出来。
空元组也正是 `EDG-101`/`PLG-007` 要求被测到的形状：**没有任何内建能力时实例也必须能装配
起来**。`D17`–`D22` 各追加一条，`D23` 断言最终条数。

**内建不享受特权**（`BAS-005`）：这里的每一条都是普通的 `PluginManifest`，与外部插件同型，
同样要声明 `capabilities` 与 `permissions`，同样经 `runtime/wiring.py` 翻译成 `LoadRequest`
后走 `kernel/plugins/host.py` 那**一个** Host 注册。本目录受 `R4` 约束，只能 import
`sdk/` 与 `contracts/`，因此这里连 registry 长什么样都看不见。
"""

from __future__ import annotations

from typing import Final

from nucleamind.sdk import PluginManifest

__all__ = ["BUILTIN_MANIFESTS"]

#: 全部内建能力的 manifest。`D17`–`D22` 逐个追加（session_jsonl / context_basic /
#: model_openai / tools_fs / tools_shell / commands_core / cli_entry）。
BUILTIN_MANIFESTS: Final[tuple[PluginManifest, ...]] = ()
