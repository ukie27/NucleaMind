"""只读诊断查询：不启动实例也能回答「装了什么」「谁提供了这项能力」（`D29`）。

职责：为 `nm plugins list` / `nm capabilities` / `nm session` 提供**不取实例锁、
不装 orchestrator、不写 `permissions.json`** 的三条查询路径——`inspect_plugins()` 跑到
阶段 A 为止，`inspect_capabilities()` 继续跑一次注册并交出覆盖解析报告，
`open_session_store()` 只装会话存储那一条能力。
不负责：装配可用实例（`bootstrap.py`）、改配置（`config_edit.py`）、格式化输出
（`runtime/cli/commands/`）、发现与阶段 A 的判定（`inventory.py` / `plugin_plan.py`）。

除了 `open_session_store()`（`D23` 起就在这里的形态，它沿用 `write_config_error()` 那条
`EDG-501` 的后半句），本模块不写任何文件。

**为什么不直接调 `bootstrap()`**，三条理由都是硬的：

1. 它**取实例锁**。看一眼装了什么不该与正在跑的实例互斥——`nm config show` 与
   `nm permissions` 已经立过这条规矩。
2. 它**写 `permissions.json`**（`ledger.save()`）。`D26` 定死只读路径判定照做、但从头到尾
   没人调 `save()`（`open_session_store` 的先例），否则一条不取锁的命令会与正在跑的实例
   抢同一个文件。
3. 它跑 §10.1 步骤 8 的必需能力校验。一个还没配模型的实例会让 `nm capabilities` 以
   「没有指定要用哪个模型」失败，而那恰恰是最需要看一眼能力表的时刻。

**同样地，报告里的冲突不抛出**：`raise_if_failed()` 是启动路径的语义。对这两条命令而言，
冲突正是要印出来的东西（`NFR-502`、`PLG-006`）。

**一处如实记下的副作用**：阶段 A 的 `check_state_version()` 在插件状态目录**已经存在**
且还没有标记文件时会补写 `.nucleamind-state.json`。它与一次真实加载写的内容完全相同、
幂等，也不会为一个从未写盘的插件建目录（`D27` 的约定）。除此之外这两条路一个字节都不写。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from nucleamind.builtins.registry import BUILTIN_MANIFESTS
from nucleamind.contracts import CapabilityKind, InstanceId, SessionStore
from nucleamind.kernel.config import InstanceLayout, LoadedConfig, load_config
from nucleamind.kernel.observability import EventBus, PluginStatus
from nucleamind.kernel.plugins import LoadOutcome, PermissionLedger
from nucleamind.kernel.registry import ResolutionReport
from nucleamind.sdk import PluginManifest

from .bootstrap import (
    load_config_or_report,
    plan_external,
    require_sessions,
    select_manifests,
    wire_all,
)
from .inventory import PluginInventory
from .plugin_context import PluginRuntime, RuntimePluginContext
from .plugin_disable import suppressed_capabilities
from .plugin_plan import discover_plugins

__all__ = ["Inspection", "inspect_capabilities", "inspect_plugins", "open_session_store"]


@dataclass(frozen=True, slots=True)
class Inspection:
    """一次只读查询的产物。

    `inventory` 是**修正过的**那一份（阶段 A 落榜项已从 `discovered` 移进 `failures`），
    与会话内 `/plugins` 看到的同源；`report` 只有 `inspect_capabilities()` 会填。
    """

    loaded: LoadedConfig
    inventory: PluginInventory
    report: ResolutionReport | None = None
    #: 逐提供方的加载结果。带 `error` 的那些是「`setup()` 没跑通」，与 `report.failures`
    #: 的「冲突」是两件事：前者的能力**从来没进过** registry，后者进了又被判出局。
    outcomes: tuple[LoadOutcome, ...] = ()

    @property
    def statuses(self) -> tuple[PluginStatus, ...]:
        """投影成 `/plugins` 那张表的形状，按 id 排序。"""
        return self.inventory.statuses()


def _prepare(
    *,
    instance_dir: Path | str | None,
    instance: str | None,
    env: Mapping[str, str] | None,
    overrides: Sequence[str] | None,
    home: Path | None,
    manifests: Sequence[PluginManifest],
) -> tuple[InstanceLayout, LoadedConfig, tuple[PluginManifest, ...], EventBus]:
    """配置 → 内建清单 → 一个不接任何 sink 的事件总线。

    总线是**必须**的（发现与阶段 A 都往上发事件），但这条路上没有订阅者：只读命令不该
    往 `logs/events-<date>.jsonl` 里追加一次「实例启动」。它同时也是「本函数不写文件」
    这条承诺的一部分——`bootstrap` 那条路上的 `write_config_error()` 同样不在这里。
    """
    layout = InstanceLayout.resolve(
        instance_dir=instance_dir, instance=instance, env=env, home=home
    )
    loaded = load_config(
        instance_dir=layout.root, env=env, overrides=overrides, home=home, ensure_dirs=False
    )
    builtins = select_manifests(manifests, loaded.config)
    return layout, loaded, builtins, EventBus(InstanceId(layout.root.name))


def inspect_plugins(
    *,
    instance_dir: Path | str | None = None,
    instance: str | None = None,
    env: Mapping[str, str] | None = None,
    overrides: Sequence[str] | None = None,
    home: Path | None = None,
    manifests: Sequence[PluginManifest] = BUILTIN_MANIFESTS,
) -> Inspection:
    """发现外部插件并跑完阶段 A，**不导入任何 `setup`**。

    `nm plugins list` 的数据源。跳过原因、发现阶段的失败与阶段 A 的失败在同一份清单里
    ——用户不需要知道一个插件是在哪个阶段落的榜，他只需要知道它没被加载、以及为什么
    （`D27` 的结论）。

    **异常约定**：配置读不出来（文件坏了、字段非法）时原样抛 `NucleaError`——那时连
    「装了哪些插件」都无从谈起。插件自身的问题一律进 `inventory.failures`，不抛。
    """
    layout, loaded, builtins, bus = _prepare(
        instance_dir=instance_dir,
        instance=instance,
        env=env,
        overrides=overrides,
        home=home,
        manifests=manifests,
    )
    _, inventory = plan_external(
        discover_plugins(loaded.config, layout, bus),
        loaded.config,
        layout,
        loaded.workspace_root,
        bus,
        builtins,
        strict=False,
    )
    return Inspection(loaded=loaded, inventory=inventory)


async def inspect_capabilities(
    *,
    instance_dir: Path | str | None = None,
    instance: str | None = None,
    env: Mapping[str, str] | None = None,
    overrides: Sequence[str] | None = None,
    home: Path | None = None,
    manifests: Sequence[PluginManifest] = BUILTIN_MANIFESTS,
) -> Inspection:
    """跑一次完整注册并交出覆盖解析报告，**不做步骤 8 的必需能力判定**。

    `nm capabilities` 的数据源。它真的会跑每个提供方的 `setup()`——`shadowed` 关系只有在
    全部登记都到齐之后才算得出来（`EDG-102`：覆盖永不由加载顺序决定），没有更便宜的路。
    内建与外部插件走的仍是同一次 `wire_capabilities()`（`SDK-007`）。

    **权限账本只读不写**：判定照做（一个插件的能力受不受权限影响，两条路必须给同一个
    答案），但这里从头到尾没人调 `save()`。

    **跑完就把 ctx 收掉**：`setup()` 里订阅的事件与派生的后台任务在这条路上没有实例去
    停它们（`AgentInstance.stop()` 不在这条路上），因此本函数自己走一遍
    `RuntimePluginContext.shutdown()`——一条只读命令不该让进程带着几个还在跑的插件任务
    退出。收尾不按停止顺序（`PLG-005` 讲的是「被依赖者后停」，而这里根本没有人被启动
    过）；它只是把刚刚建出来的东西还回去。

    **异常约定**：与 `inspect_plugins()` 相同——配置问题抛，插件问题进报告。
    关键插件在阶段 A 失败同样只记不抛（`strict=False`）。
    """
    layout, loaded, builtins, bus = _prepare(
        instance_dir=instance_dir,
        instance=instance,
        env=env,
        overrides=overrides,
        home=home,
        manifests=manifests,
    )
    plan, inventory = plan_external(
        discover_plugins(loaded.config, layout, bus),
        loaded.config,
        layout,
        loaded.workspace_root,
        bus,
        builtins,
        strict=False,
    )
    contexts: list[RuntimePluginContext] = []
    try:
        wiring = await wire_all(
            (*builtins, *plan.manifests),
            loaded.config,
            layout,
            loaded.workspace_root,
            bus,
            PluginRuntime(),
            env,
            contexts,
            PermissionLedger.load(layout.permissions_path),
            external_ids=[manifest.id for manifest in plan.manifests],
            # `on_disable=leave_missing` 抑制掉的能力在这里同样要缺席，否则
            # `nm capabilities` 印出来的生效集合与真正启动时的不是同一份（`D30`）。
            suppressed=suppressed_capabilities(inventory, loaded.config),
            # 关键提供方失败也只记不抛：凭据还没导出时，`model-openai` 的 `setup()` 会
            # 取不到密钥，而那正是最需要看一眼能力表的时刻（见 `wire_capabilities`）。
            halt_on_critical=False,
        )
    finally:
        for ctx in reversed(contexts):
            await ctx.shutdown()
    return Inspection(
        loaded=loaded, inventory=inventory, report=wiring.report, outcomes=wiring.outcomes
    )


async def open_session_store(
    *,
    instance_dir: Path | str | None = None,
    instance: str | None = None,
    env: Mapping[str, str] | None = None,
    home: Path | None = None,
    manifests: Sequence[PluginManifest] = BUILTIN_MANIFESTS,
) -> tuple[LoadedConfig, SessionStore]:
    """只把会话存储装起来（`nm session` 用）。**不取实例锁、不装 orchestrator。**

    只加载声明了 `SESSION_STORE` 的 manifest，因此不会因为「模型还没配」而让一条只读的
    诊断命令失败——但它仍然走同一条注册路径，插件覆盖了会话存储时 `nm session` 看到的
    就是插件那一份。直接 `new JsonlSessionStore(...)` 会让这条命令永远只认内建实现。
    """
    layout = InstanceLayout.resolve(
        instance_dir=instance_dir, instance=instance, env=env, home=home
    )
    loaded = load_config_or_report(layout, env=env, overrides=None, home=home)
    builtins = select_manifests(manifests, loaded.config)
    selected = tuple(
        manifest
        for manifest in builtins
        if any(decl.kind is CapabilityKind.SESSION_STORE for decl in manifest.capabilities)
    )
    bus = EventBus(InstanceId(layout.root.name))
    # 外部插件走同一条路（`D27`）：覆盖了会话存储的插件，`nm session` 看到的就是它那一份。
    # 同样只取声明了 `SESSION_STORE` 的那些——一条只读命令不该因为「模型还没配」而失败。
    plan, _ = plan_external(
        discover_plugins(loaded.config, layout, bus),
        loaded.config,
        layout,
        loaded.workspace_root,
        bus,
        builtins,
    )
    external = tuple(
        manifest
        for manifest in plan.manifests
        if any(decl.kind is CapabilityKind.SESSION_STORE for decl in manifest.capabilities)
    )
    wiring = await wire_all(
        (*selected, *external),
        loaded.config,
        layout,
        loaded.workspace_root,
        bus,
        PluginRuntime(),
        env,
        [],
        # **只读路径不落盘**：`nm session` 不取实例锁，让它改写 `permissions.json` 会与
        # 正在跑的实例抢同一个文件。判定照做（会话存储插件的授权语义不能两套），
        # 但这个账本从头到尾没人调 `save()`。
        PermissionLedger.load(layout.permissions_path),
        external_ids=[manifest.id for manifest in external],
    )
    wiring.report.raise_if_failed()
    return loaded, require_sessions(wiring.registry)
