"""启动序列：从「实例在哪」到一个可以接受输入的 `AgentInstance`（技术方案 §10.1）。

职责：按 §10.1 的十步装配一个实例——取锁、加载配置、挑选内建清单、发现并规划外部插件、
注册能力、解析覆盖、校验必需能力、装出 `OrchestratorDeps` 与两个门面。
不负责：跑它（`instance.py`）、解析 argv（`runtime/cli/`）、阶段 A 的三项判定
（`plugin_plan.py` + `kernel/plugins/loader.py`）、生成首次运行的配置（`D24`）。

**内建的配置块由这里合成**（`CFG-002` 的另一面）：`R4` 禁止 `builtins/` 够到 `kernel/`，
因此「会话写哪个目录」「workspace 的根在哪」「命令前缀是什么」只能由装配根经
`plugins.<id>.config` 交下来。用户显式写过的键**压过**这里派生的值——派生的是默认位置，
不是不可覆盖的策略。

**`keep` 与 `setup()` 必须同源于同一份配置**（`D20` 定下的机制）：这里把同一个
`plugins.<id>.config` 既喂给声明过滤、又喂给 `setup()`。忘了传 `keep` 的后果是
`CapabilityHost.finish()` 以 `PLUGIN_LOAD_FAILED` 报「声明了却没注册」，那个报错是对的。

**`EDG-108` 在这里落地两次**：配置试图禁用 CLI 入口时直接拒绝启动；覆盖 CLI 的提供方
没能交出实现时，用同一批 manifest 再装一次、但只让内建提供 CLI 入口（`BAS-010` 的
「强制回落」，且它不允许被配置成 `fail_start`）。
"""

from __future__ import annotations

from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import replace
from datetime import date
from pathlib import Path

from nucleamind.builtins import cli_entry, commands_core, session_jsonl, tools_fs, tools_shell
from nucleamind.builtins.registry import BUILTIN_MANIFESTS
from nucleamind.contracts import (
    Builtin,
    CapabilityKind,
    CliEntry,
    ErrorCode,
    EventName,
    InstanceId,
    JsonValue,
    ModelInfo,
    ModelProvider,
    NucleaError,
    OutboundMessage,
    Plugin,
    PluginId,
    ProviderId,
    SessionStore,
)
from nucleamind.kernel.config import (
    InstanceLayout,
    InstanceLock,
    LoadedConfig,
    NucleaConfig,
    load_config,
)
from nucleamind.kernel.observability import (
    Diagnostics,
    EventBus,
    JsonlFileSink,
    MemoryRingSink,
    PluginState,
    PluginStatus,
    write_config_error,
)
from nucleamind.kernel.plugins import (
    Decision,
    Grant,
    LedgerDecision,
    LoadOutcome,
    PermissionLedger,
    PluginLifecycle,
    PluginPhase,
    channels_from,
    cli_entry_from,
    model_providers_from,
    session_store_from,
)
from nucleamind.kernel.registry import CapabilityRegistry, SuppressedCapabilities
from nucleamind.kernel.routing import (
    ConcurrencyPolicy,
    DedupCache,
    Dispatcher,
    SessionScheduler,
    build_command_index,
)
from nucleamind.kernel.turn import (
    HookRouter,
    OrchestratorDeps,
    ToolExecutor,
    TurnOrchestrator,
    TurnReceipt,
    bindings_from,
    context_providers_from,
    tools_from,
)
from nucleamind.sdk import CapabilityDecl, PluginContext, PluginManifest

from .instance import AgentInstance, Closer
from .introspection import build_instance_view, build_turn_control
from .inventory import PluginInventory
from .plugin_context import PluginRuntime, RuntimePluginContext, build_plugin_context
from .plugin_disable import suppressed_capabilities
from .plugin_plan import (
    ExternalPlan,
    correct_inventory,
    discover_plugins,
    plan_external_plugins,
    plan_plugins,
)
from .wiring import Wiring, wire_capabilities

#: `PluginManifest` 从这里再导出一次：`embed/` 只能 import `contracts/` 与 `runtime/`
#: （`R5`），而 `open_instance(manifests=...)` 的类型在 `sdk/`。转发比让门面收 `object` 诚实。
__all__ = [
    "BUILTIN_MANIFESTS",
    "PluginManifest",
    "approve",
    "bootstrap",
    "builtin_config_blocks",
    "capability_filter",
    "declared_grants",
    "load_config_or_report",
    "plan_external",
    "require_sessions",
    "select_manifests",
    "suppressed_capabilities",
    "wire_all",
]

#: 「这一项能力这次还注册吗」——按插件 id 索引的裁剪器（`TOL-006`）。三份内建导出的
#: `enabled_*_names()` 是它的全部内容；第三方插件没有这条路，因此默认全留。
_ENABLED_NAMES: Mapping[str, Callable[[Mapping[str, JsonValue]], Collection[str]]] = {
    "tools-fs": tools_fs.enabled_tool_names,
    "tools-shell": tools_shell.enabled_tool_names,
    "commands-core": commands_core.enabled_command_names,
}

#: 被裁剪器管辖的能力类别。`CLI_ENTRY` / `SESSION_STORE` 这类单值能力不在其中——
#: 它们的「禁用」是 `plugins.disable`，不是按名字挑。
_FILTERED_KINDS = (CapabilityKind.TOOL, CapabilityKind.COMMAND)


def builtin_config_blocks(
    config: NucleaConfig, layout: InstanceLayout, workspace: Path
) -> dict[str, dict[str, JsonValue]]:
    """内建能力的**派生**配置：装配根知道、而内建够不着的那几个值。

    用户在 `plugins.<id>.config` 里显式写过的键压过这里的值（见模块 docstring）。
    每一项都对应一个已知的坑：`session-jsonl` 没有 `dir` 会把会话写进插件私有目录、
    `tools_fs` / `tools_shell` 没有 `workspace` 会在一个没人预期的目录里读写与执行、
    `commands-core` 没有 `prefix` 会在 `/help` 里印出错的前缀。
    """
    return {
        "session-jsonl": {session_jsonl.CONFIG_DIRECTORY_KEY: str(layout.sessions_dir)},
        "tools-fs": {tools_fs.CONFIG_WORKSPACE_KEY: str(workspace)},
        "tools-shell": {tools_shell.CONFIG_WORKSPACE_KEY: str(workspace)},
        "commands-core": {commands_core.CONFIG_PREFIX_KEY: config.routing.command_prefix},
        "cli-entry": {cli_entry.CONFIG_INSTANCE_ID_KEY: layout.root.name},
    }



def config_block_for(
    manifest: PluginManifest,
    config: NucleaConfig,
    derived: Mapping[str, Mapping[str, JsonValue]],
) -> dict[str, JsonValue]:
    """一个提供方最终看到的配置块：派生默认值 + 用户写的那份。"""
    block: dict[str, JsonValue] = dict(derived.get(manifest.id, {}))
    block.update(config.plugins.entry(manifest.id).config)
    return block


def capability_filter(
    config: NucleaConfig, derived: Mapping[str, Mapping[str, JsonValue]]
) -> Callable[[PluginManifest, CapabilityDecl], bool]:
    """构造 `wire_capabilities(keep=...)`。与 `setup()` 同源于同一份配置。"""

    def keep(manifest: PluginManifest, decl: CapabilityDecl) -> bool:
        enabled_names = _ENABLED_NAMES.get(manifest.id)
        if enabled_names is None or decl.kind not in _FILTERED_KINDS:
            return True
        return decl.name in enabled_names(config_block_for(manifest, config, derived))

    return keep


def declared_grants(manifest: PluginManifest) -> tuple[Grant, ...]:
    """manifest 的权限声明，翻成 kernel 侧的 `Grant`。

    **翻译只在这里一处**：`R2` 禁止 `kernel/` 认识 `PermissionDecl`，因此账本收的是
    `(kind, target, reason)` 三元组——与 `D25` 的「发现在 kernel、manifest 判定在 runtime」
    是同一条分界线。

    **声明是授权的上限**：账本里有、这里没有的记录不参与授权（它留在文件里只作审计）。
    """
    return tuple(
        Grant(kind=decl.kind, target=decl.target, reason=decl.reason)
        for decl in manifest.permissions
    )


def approve(
    ledger: PermissionLedger, manifest: PluginManifest, bus: EventBus
) -> LedgerDecision:
    """把一份声明判成实际授权，并把变更发成事件（`NFR-301`）。

    **事件只在账本真的变了时发**（`decision.recorded` 非空）：一条每次启动都出现的
    「已授予」只会让真正的扩权淹在噪声里，与 `D24` 的「没有孤儿时不发事件」同一条判据。
    `pending` 与 `revoked` 例外——它们是**当前生效的拒绝**，每次启动都值得说一遍，
    否则用户看到的现象是「插件装上了却什么都干不了」而日志里一个字都没有。
    """
    decision = ledger.decide(manifest.id, declared_grants(manifest))
    for entry in decision.recorded:
        bus.publish(
            EventName.CAPABILITY_PERMISSION_GRANTED,
            payload={
                "plugin": manifest.id,
                "permission": entry.name,
                "decision": entry.decision.value,
                "source": entry.source,
                "reason": entry.reason,
            },
        )
    for grant in (*decision.pending, *decision.revoked):
        if any(entry.key == grant.key for entry in decision.recorded):
            continue
        bus.publish(
            EventName.CAPABILITY_PERMISSION_GRANTED,
            payload={
                "plugin": manifest.id,
                "permission": grant.name,
                "decision": Decision.PENDING.value
                if grant in decision.pending
                else Decision.REVOKED.value,
                "source": "ledger",
                "reason": grant.reason,
            },
        )
    return decision


def plan_external(
    inventory: PluginInventory,
    config: NucleaConfig,
    layout: InstanceLayout,
    workspace: Path,
    bus: EventBus,
    builtins: Sequence[PluginManifest],
    *,
    strict: bool = True,
) -> tuple[ExternalPlan, PluginInventory]:
    """把阶段 A 需要的两个「只有装配根知道」的东西交给 `plugin_plan.plan_plugins()`。

    校验用的配置块与 `setup()` 拿到的是**同一份**（都走 `config_block_for`）——校验一份、
    执行另一份等于没校验。状态目录同样只有布局说得出（`R4` 挡着插件自己够到它）。

    `strict=False` 是只读诊断路径（`D29` 的 `runtime/inspect.py`）用的：关键插件在阶段 A
    失败时**不抛**，如实记进清单——`nm plugins list` 的全部意义就是把那条失败印出来，
    而不是跟着它一起死掉。两条路共用这里的两个 lambda，因此「校验的那份配置块」在诊断
    路径上与启动路径完全一致。
    """
    derived = builtin_config_blocks(config, layout, workspace)

    def config_for(manifest: PluginManifest) -> Mapping[str, JsonValue]:
        return config_block_for(manifest, config, derived)

    def state_dir_for(plugin_id: str) -> Path:
        return layout.plugins_dir / plugin_id

    provided = [manifest.id for manifest in builtins]
    if strict:
        return plan_plugins(
            inventory,
            bus,
            config_for=config_for,
            state_dir_for=state_dir_for,
            provided=provided,
        )
    plan = plan_external_plugins(
        inventory.discovered,
        config_for=config_for,
        state_dir_for=state_dir_for,
        provided=provided,
    )
    return plan, correct_inventory(inventory, plan)


def select_manifests(
    manifests: Sequence[PluginManifest], config: NucleaConfig
) -> tuple[PluginManifest, ...]:
    """§10.1 步骤 3：跳过被禁用项，**CLI_ENTRY 除外**。

    `plugins.disable` 里出现一个声明了 CLI 入口的提供方即**拒绝配置**（`EDG-108`）——
    静默忽略它会让用户以为自己关掉了 CLI，而实际没有；照办则让实例没有任何入口。
    """
    disabled = set(config.plugins.disable)
    kept: list[PluginManifest] = []
    for manifest in manifests:
        if manifest.id not in disabled:
            kept.append(manifest)
            continue
        if any(decl.kind is CapabilityKind.CLI_ENTRY for decl in manifest.capabilities):
            raise NucleaError(
                ErrorCode.CONFIG_INVALID,
                "CLI 入口不可禁用：不装任何 Channel 插件时它是唯一的本地交互入口。",
                detail={
                    "pointer": "/plugins/disable",
                    "plugin": manifest.id,
                    "suggestion": "从 plugins.disable 里删掉它；要换实现请用插件覆盖 "
                    "builtin:stdio。",
                },
            )
    return tuple(kept)


def load_config_or_report(
    layout: InstanceLayout,
    *,
    env: Mapping[str, str] | None,
    overrides: Sequence[str] | None,
    home: Path | None,
) -> LoadedConfig:
    """§10.1 步骤 2。解析失败时把错误写进 `logs/`（`EDG-501` 的后半句）。

    **这是 `write_config_error()` 唯一的调用点**：配置解析失败发生在事件总线建起来之前，
    做成 sink 就等于把这条需求推回它无法成立的时序里（`D12` 的结论）。写盘失败不掩盖
    原始错误——它 best-effort，返回 `False` 而已。
    """
    try:
        return load_config(
            instance_dir=layout.root, env=env, overrides=overrides, home=home, ensure_dirs=False
        )
    except NucleaError as error:
        write_config_error(layout.config_error_log_path(date.today()), error)
        raise


def _pick_model(
    registry: CapabilityRegistry, config: NucleaConfig
) -> tuple[ModelProvider, str, ModelInfo | None]:
    """§10.1 步骤 8 的 MODEL 一项：选出生效的 provider 与模型标识。"""
    bindings = model_providers_from(registry)
    if not bindings:
        raise _missing("MODEL", "没有任何模型供应商，实例无法回答任何输入。")
    wanted = config.model.provider
    chosen = next((b for b in bindings if b.name == wanted), None) if wanted else bindings[0]
    if chosen is None:
        raise NucleaError(
            ErrorCode.CAPABILITY_MISSING,
            "配置里指定的模型供应商没有注册。",
            detail={
                "pointer": "/model/provider",
                "wanted": wanted,
                "available": [b.name for b in bindings],
            },
        )
    model_id = config.model.name
    if not model_id:
        raise NucleaError(
            ErrorCode.CONFIG_INVALID,
            "没有指定要用哪个模型。",
            detail={
                "pointer": "/model/name",
                "suggestion": '在 config.json 里写 {"model": {"name": "gpt-4o-mini"}}。',
            },
        )
    return chosen.value, model_id, chosen.value.describe(model_id)


def require_sessions(registry: CapabilityRegistry) -> SessionStore:
    binding = session_store_from(registry)
    if binding is None:
        raise _missing("SESSION_STORE", "没有会话存储，历史无处可写（SES-003）。")
    return binding.value


def _missing(kind: str, why: str) -> NucleaError:
    return NucleaError(
        ErrorCode.CAPABILITY_MISSING,
        f"必需能力缺失：{kind}。{why}",
        detail={"kind": kind, "suggestion": "检查 plugins.disable 与插件加载结果（nm 会打印）。"},
    )


async def wire_all(
    manifests: Sequence[PluginManifest],
    config: NucleaConfig,
    layout: InstanceLayout,
    workspace: Path,
    bus: EventBus,
    runtime: PluginRuntime,
    env: Mapping[str, str] | None,
    contexts: list[RuntimePluginContext],
    ledger: PermissionLedger,
    *,
    builtin_cli_only: bool = False,
    external_ids: Collection[str] = (),
    suppressed: SuppressedCapabilities | None = None,
    halt_on_critical: bool = True,
) -> Wiring:
    """跑一次注册。`builtin_cli_only=True` 时只让内建提供 CLI 入口（`EDG-108` 的回落）。

    **内建与外部插件在这里没有第二条路**（`SDK-007`）：同一个 `manifests` 序列、同一个
    `context_for`、同一个 `keep`，唯一的差别是 `provider_for` 交出 `Builtin()` 还是
    `Plugin(<id>)`。外部插件排在内建之后，但那不决定谁覆盖谁（`EDG-102`）。
    """
    derived = builtin_config_blocks(config, layout, workspace)
    keep = capability_filter(config, derived)
    external = set(external_ids)

    def provider_for(manifest: PluginManifest) -> ProviderId:
        """外部插件以自己的 id 为提供方身份（`priority` 基准值 100，内建是 0）。"""
        return Plugin(PluginId(manifest.id)) if manifest.id in external else Builtin()

    def keep_with_cli(manifest: PluginManifest, decl: CapabilityDecl) -> bool:
        if (
            builtin_cli_only
            and decl.kind is CapabilityKind.CLI_ENTRY
            and manifest.id != "cli-entry"
        ):
            return False
        return keep(manifest, decl)

    def context_for(manifest: PluginManifest) -> PluginContext:
        entry = config.plugins.entry(manifest.id)
        ctx = build_plugin_context(
            manifest.id,
            config=config_block_for(manifest, config, derived),
            secrets=entry.secrets,
            state_dir=layout.plugins_dir / manifest.id,
            grants=approve(ledger, manifest, bus).granted,
            bus=bus,
            runtime=runtime,
            env=env,
            workspace=workspace,
            config_path=layout.config_path,
        )
        # `build_plugin_context()` 的返回类型是 `PluginContext`（那是它存在的理由：
        # 静态证明一致性）。装配根还要按 `EDG-104` 收走 ctx 派生的任务，因此在这里窄化
        # 一次——唯一的构造点就在同一个文件里，这个 `isinstance` 不可能不成立。
        assert isinstance(ctx, RuntimePluginContext)  # noqa: S101
        contexts.append(ctx)
        bus.publish(EventName.PLUGIN_DISCOVERED, payload={"plugin": manifest.id})
        return ctx

    return await wire_capabilities(
        manifests=manifests,
        context_for=context_for,
        provider_for=provider_for,
        keep=keep_with_cli,
        suppressed=suppressed,
        halt_on_critical=halt_on_critical,
    )


def _lifecycles(
    manifests: Sequence[PluginManifest], outcomes: Sequence[LoadOutcome]
) -> tuple[PluginLifecycle, ...]:
    """给每个提供方建一份生命周期，置于 `LOADED` 或 `FAILED`（`D28`、`NFR-201`）。

    **按位置对齐**：`load_into()` 对每个请求恰好产出一个结果且保持顺序，而请求是按
    `manifests` 一一翻译的。按 `ProviderId` 索引在这里行不通——全部内建共用一个
    `Builtin()`，那样会把七份内建的加载结果并成一条（`D23` 在配置块上、`D26` 在权限账本上
    踩过同一个坑）。

    走到这一步的提供方都已过阶段 A，因此先推 `VALIDATED`；`setup()` 失败的在那个阶段
    失败（`failed_phase=validated`），这正是「记录失败发生在哪个阶段」要的信息。
    """
    lifecycles: list[PluginLifecycle] = []
    for manifest, outcome in zip(manifests, outcomes, strict=False):
        lifecycle = PluginLifecycle(plugin_id=manifest.id)
        lifecycle.advance(PluginPhase.VALIDATED)
        if outcome.error is None:
            lifecycle.advance(PluginPhase.LOADED)
        else:
            lifecycle.fail(outcome.error)
        lifecycles.append(lifecycle)
    return tuple(lifecycles)


async def bootstrap(
    *,
    instance_dir: Path | str | None = None,
    instance: str | None = None,
    env: Mapping[str, str] | None = None,
    overrides: Sequence[str] | None = None,
    home: Path | None = None,
    manifests: Sequence[PluginManifest] = BUILTIN_MANIFESTS,
    acquire_lock: bool = True,
) -> AgentInstance:
    """装配一个实例（§10.1 的十步）。返回的实例尚未 `start()`。

    **异常约定**：任何一步失败都原样抛 `NucleaError`——启动失败必须是显式的。已经取到的
    锁在失败路径上被释放，否则一次启动失败会砖掉实例目录直到下次回收。
    """
    # 1 布局与实例锁
    layout = InstanceLayout.resolve(instance_dir=instance_dir, instance=instance, env=env, home=home)
    layout.ensure()
    lock = InstanceLock(layout.lock_path).acquire() if acquire_lock else None
    try:
        return await _bootstrap_locked(
            layout, lock, env=env, overrides=overrides, home=home, manifests=manifests
        )
    except BaseException:
        if lock is not None:
            lock.release()
        raise


async def _bootstrap_locked(
    layout: InstanceLayout,
    lock: InstanceLock | None,
    *,
    env: Mapping[str, str] | None,
    overrides: Sequence[str] | None,
    home: Path | None,
    manifests: Sequence[PluginManifest],
) -> AgentInstance:
    """步骤 2–8。拆出来只为让 `bootstrap()` 的锁释放路径是一条 `try`。"""
    # 2 配置
    loaded = load_config_or_report(layout, env=env, overrides=overrides, home=home)
    config = loaded.config
    instance_id = InstanceId(layout.root.name)

    # 事件总线与两个 sink。JSONL sink 的开关在配置里，因此它只能在步骤 2 之后接上——
    # 在此之前发生的事只进内存环，这是配置与日志开关之间不可消除的先后关系。
    bus = EventBus(instance_id)
    ring = MemoryRingSink()
    bus.subscribe(ring, name="memory-ring")
    closers: list[Closer] = []
    if config.logging.file_enabled:
        sink = JsonlFileSink(layout.events_log_path)
        bus.subscribe(sink, name="jsonl-file")
        closers.append(_closer(sink.close))
    bus.publish(EventName.INSTANCE_STARTING, payload={"instance": str(instance_id)})

    # 3 内建清单（跳过被禁用项，CLI 入口除外）
    selected = select_manifests(manifests, config)

    # 3b 外部插件发现（`D25`）：未列入 `plugins.enabled` 的候选连 manifest 都不读。
    inventory = discover_plugins(config, layout, bus)
    # 3c 阶段 A 的剩余三步与拓扑排序（`D27`）。产出接到诊断上，`/plugins` 因此列得出
    # 候选、跳过原因与两个阶段的失败。
    plan, inventory = plan_external(
        inventory, config, layout, loaded.workspace_root, bus, selected
    )
    external_ids = [manifest.id for manifest in plan.manifests]
    # 3d 被禁用的覆盖者留下的空缺：`BAS-004` 不允许内建在这里**隐式**复活，因此用户必须
    # 对每一条 `on_disable` 表态（`D30`）。判定在配置层与注册之间——它是配置错误，不该等到
    # 一次白跑的 `setup()` 之后才报出来。
    suppressed = suppressed_capabilities(inventory, config)
    # 内建在前、外部插件按拓扑序在后。顺序只保证「被依赖者先 setup」，覆盖由 manifest 的
    # `overrides` 决定（`EDG-102`）。
    all_manifests = (*selected, *plan.manifests)

    # 4–7 注册 → 解析覆盖 → 冻结。内建与外部插件共用这一条路径（`SDK-007`）。
    runtime = PluginRuntime()
    contexts: list[RuntimePluginContext] = []
    # 权限账本：`permissions.json` 的批准叠在 manifest 声明之前（`D26`）。读不懂那份文件
    # 是**启动失败**而不是「当成空账本」——后者等于一次静默的全部重新授予。
    ledger = PermissionLedger.load(layout.permissions_path)
    wiring = await wire_all(
        all_manifests,
        config,
        layout,
        loaded.workspace_root,
        bus,
        runtime,
        env,
        contexts,
        ledger,
        external_ids=external_ids,
        suppressed=suppressed,
    )
    if cli_entry_from(wiring.registry) is None and any(
        decl.kind is CapabilityKind.CLI_ENTRY
        for manifest in all_manifests
        for decl in manifest.capabilities
    ):
        # `EDG-108`/`BAS-010`：覆盖 CLI 的提供方没交出实现，强制回落到内建实现。
        # 重装一次而不是打补丁——半装好的 registry 已经冻结，改它比重来更容易出错。
        contexts.clear()
        wiring = await wire_all(
            all_manifests,
            config,
            layout,
            loaded.workspace_root,
            bus,
            runtime,
            env,
            contexts,
            ledger,
            builtin_cli_only=True,
            external_ids=external_ids,
            suppressed=suppressed,
        )
    # 账本只在真的变了时落盘（`save()` 自己判 `dirty`）。写在注册之后：`setup()` 抛异常
    # 时那个提供方的授权记录同样值得留下——下一次启动它不该被当成首次而重新全授。
    ledger.save()
    for outcome in wiring.outcomes:
        bus.publish(
            EventName.PLUGIN_LOADED if outcome.error is None else EventName.PLUGIN_LOAD_FAILED,
            payload={"provider": str(outcome.provider)},
            error=outcome.error,
        )
    wiring.report.raise_if_failed()

    # 8 必需能力
    registry = wiring.registry
    sessions = require_sessions(registry)
    model, model_id, model_info = _pick_model(registry, config)
    cli = cli_entry_from(registry)
    if cli is None:
        raise _missing("CLI_ENTRY", "没有本地交互入口（BAS-009）。")

    instance = _assemble(
        layout=layout,
        loaded=loaded,
        bus=bus,
        ring=ring,
        wiring=wiring,
        inventory=inventory,
        sessions=sessions,
        model=model,
        model_id=model_id,
        model_info=model_info,
        cli=cli.value,
        contexts=tuple(contexts),
        lifecycles=_lifecycles(all_manifests, wiring.outcomes),
        runtime=runtime,
        lock=lock,
        closers=closers,
    )
    return instance


def _plugin_statuses(
    inventory: PluginInventory, lifecycles: Sequence[PluginLifecycle]
) -> Callable[[], Sequence[PluginStatus]]:
    """`/plugins` 的数据源：发现清单叠上运行期状态（`D28` + `D29`）。

    清单本身只知道「已发现 / 已跳过 / 已失败」——它在 `setup()` 跑之前就产出了，因此一个
    已经在跑的插件在那里仍然写着 `discovered`。运行期的真相在 `PluginLifecycle` 上，
    **状态由它的 `state` 投影给出**（`PHASE_STATES` 是唯一那张表，这里不另写一份映射）。

    只覆盖清单里已有的 id：`lifecycles` 同时含内建，而内建不是插件（见调用点的注释）。
    每次调用重算一次——生命周期是可变的，缓存一份快照会让 `/plugins` 永远停在启动那一刻。
    """
    by_id = {lifecycle.plugin_id: lifecycle for lifecycle in lifecycles}

    def statuses() -> Sequence[PluginStatus]:
        rows: list[PluginStatus] = []
        for status in inventory.statuses():
            lifecycle = by_id.get(str(status.plugin_id))
            if lifecycle is None or status.state is PluginState.FAILED:
                # 阶段 A 落榜的插件根本没有生命周期，而已经记下的失败不该被一个
                # 「后来它又被加载了」的状态盖掉。
                rows.append(status)
                continue
            rows.append(replace(status, state=lifecycle.state))
        return tuple(rows)

    return statuses


def _closer(fn: Callable[[], None]) -> Closer:
    """把一个同步收尾包成 `Closer`。"""

    async def close() -> None:
        fn()

    return close


def _assemble(
    *,
    layout: InstanceLayout,
    loaded: LoadedConfig,
    bus: EventBus,
    ring: MemoryRingSink,
    wiring: Wiring,
    inventory: PluginInventory,
    sessions: SessionStore,
    model: ModelProvider,
    model_id: str,
    model_info: ModelInfo | None,
    cli: CliEntry,
    contexts: tuple[RuntimePluginContext, ...],
    lifecycles: tuple[PluginLifecycle, ...],
    runtime: PluginRuntime,
    lock: InstanceLock | None,
    closers: Sequence[Closer],
) -> AgentInstance:
    """把已取回的能力装成 `OrchestratorDeps` 与 `AgentInstance`（`D14` 定的那张清单）。

    三个超时、并发策略、队列上限、去重参数与命令前缀**全部来自配置**——这里是那些字段
    唯一的消费点，`kernel/` 里的默认值只在没有装配根的测试里生效。
    """
    config = loaded.config
    registry = wiring.registry
    channels = tuple(
        (binding.value.channel_id, binding.value) for binding in channels_from(registry)
    )
    by_channel = dict(channels)

    async def deliver(message: OutboundMessage) -> None:
        """按 `channel_id` 路由回对应 Channel（`MSG-006`：寻址在消息自己身上）。

        找不到对应 Channel 时**静默丢弃**：那是 `embed.submit()` 这类没有 Channel 的
        调用方的正常情形，它拿的是 `TurnReceipt.messages`。
        """
        channel = by_channel.get(message.channel_id)
        if channel is not None:
            await channel.deliver(message)

    def report_failure(error: NucleaError) -> None:
        """Hook 失败的去向。`publish()` 有返回值，`on_failure` 要的是 `None`——
        写成 lambda 会把那个 `RuntimeEvent` 当成返回值交回去。"""
        bus.publish(EventName.PLUGIN_FAILED, error=error)

    executor = ToolExecutor(tools_from(registry))
    router = HookRouter(
        bindings_from(registry),
        observer_timeout_ms=config.hooks.observer_timeout_ms,
        interceptor_timeout_ms=config.hooks.interceptor_timeout_ms,
        on_failure=report_failure,
    )
    deps = OrchestratorDeps(
        instance_id=bus.instance_id,
        bus=bus,
        sessions=sessions,
        model=model,
        tools=executor,
        hooks=router,
        dispatcher=Dispatcher(build_command_index(registry), prefix=config.routing.command_prefix),
        scheduler=SessionScheduler[TurnReceipt](
            policy=ConcurrencyPolicy(config.routing.session_concurrency),
            queue_max_size=config.routing.queue_max_size,
        ),
        dedup=DedupCache(
            capacity=config.routing.dedup_capacity, ttl_ms=config.routing.dedup_ttl_ms
        ),
        limits=loaded.limits,
        model_id=model_id,
        # 模型看得见的工具集与调度用的工具集同源——`ToolExecutor.specs` 是唯一来源。
        tool_specs=executor.specs,
        context_providers=context_providers_from(registry),
        model_info=model_info,
        context_provider_timeout_ms=config.context.provider_timeout_ms,
        deliver=deliver,
    )
    orchestrator = TurnOrchestrator(deps)
    diagnostics = Diagnostics(
        events=ring,
        capabilities_source=lambda: wiring.report,
        # `D25`：`/plugins` 的数据源。内建不出现在这里——它们是 `Builtin()` 提供方而不是
        # 插件，`/capabilities` 才是回答「这项能力谁提供的」的地方。
        plugins_source=_plugin_statuses(inventory, lifecycles),
    )
    # `D22` 的两个门面：命令索引与配置文档都用 callable 取，理由见 `introspection.py`。
    # 配置文档交的是 `${VAR}` 字面量那一棵树（`/config` 的脱敏靠这条结构性保证）。
    runtime.ready(
        instance_view=build_instance_view(
            commands_source=lambda: build_command_index(registry),
            diagnostics=diagnostics,
            config_source=lambda: _config_document(loaded),
            sessions=sessions,
        ),
        turn_control=build_turn_control(orchestrator),
    )
    return AgentInstance(
        instance_id=bus.instance_id,
        layout=layout,
        config=loaded,
        bus=bus,
        diagnostics=diagnostics,
        registry=registry,
        report=wiring.report,
        deps=deps,
        orchestrator=orchestrator,
        cli_entry=cli,
        channels=channels,
        outcomes=wiring.outcomes,
        contexts=contexts,
        lifecycles=lifecycles,
        stop_timeout_ms=config.plugins.stop_timeout_ms,
        channel_concurrency=config.routing.channel_concurrency,
        channel_queue_max_size=config.routing.channel_queue_max_size,
        runtime=runtime,
        lock=lock,
        closers=tuple(closers),
    )


def _config_document(loaded: LoadedConfig) -> Mapping[str, JsonValue]:
    """`/config` 看到的那棵树。`to_json()` 的 `config` 段就是它。"""
    document = loaded.to_json()["config"]
    return document if isinstance(document, Mapping) else {}
