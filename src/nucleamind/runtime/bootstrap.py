"""启动序列：从「实例在哪」到一个可以接受输入的 `AgentInstance`（技术方案 §10.1）。

职责：按 §10.1 的十步装配一个实例——取锁、加载配置、挑选内建清单、注册能力、解析覆盖、
校验必需能力、装出 `OrchestratorDeps` 与两个门面。
不负责：跑它（`instance.py`）、解析 argv（`runtime/cli/`）、发现外部插件（`D25`/`D27`）、
生成首次运行的配置（`D24`）。

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
from datetime import date
from pathlib import Path

from nucleamind.builtins import cli_entry, commands_core, session_jsonl, tools_fs, tools_shell
from nucleamind.builtins.registry import BUILTIN_MANIFESTS
from nucleamind.contracts import (
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
    PermissionKind,
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
    write_config_error,
)
from nucleamind.kernel.plugins import (
    channels_from,
    cli_entry_from,
    model_providers_from,
    session_store_from,
)
from nucleamind.kernel.registry import CapabilityRegistry
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
from .plugin_context import PluginGrants, PluginRuntime, RuntimePluginContext, build_plugin_context
from .wiring import Wiring, wire_capabilities

#: `PluginManifest` 从这里再导出一次：`embed/` 只能 import `contracts/` 与 `runtime/`
#: （`R5`），而 `open_instance(manifests=...)` 的类型在 `sdk/`。转发比让门面收 `object` 诚实。
__all__ = [
    "BUILTIN_MANIFESTS",
    "PluginManifest",
    "bootstrap",
    "builtin_config_blocks",
    "capability_filter",
    "open_session_store",
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


def grants_of(manifest: PluginManifest) -> PluginGrants:
    """一个提供方被授予的权限。

    **`D23` 里它等于 manifest 声明的集合**：用户批准（`permissions.json`）是 `D26`。
    如实写出来比留一个「看起来在判权限」的空壳好——后者会让评审以为这条已经做完了。
    """
    kinds = {decl.kind for decl in manifest.permissions}
    secrets = {
        decl.target for decl in manifest.permissions if decl.kind is PermissionKind.SECRET
    }
    return PluginGrants(kinds=frozenset(kinds), secrets=frozenset(secrets))


def _select_manifests(
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


def _load_config_or_report(
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


def _require_sessions(registry: CapabilityRegistry) -> SessionStore:
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


async def _wire(
    manifests: Sequence[PluginManifest],
    config: NucleaConfig,
    layout: InstanceLayout,
    workspace: Path,
    bus: EventBus,
    runtime: PluginRuntime,
    env: Mapping[str, str] | None,
    contexts: list[RuntimePluginContext],
    *,
    builtin_cli_only: bool = False,
) -> Wiring:
    """跑一次注册。`builtin_cli_only=True` 时只让内建提供 CLI 入口（`EDG-108` 的回落）。"""
    derived = builtin_config_blocks(config, layout, workspace)
    keep = capability_filter(config, derived)

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
            grants=grants_of(manifest),
            bus=bus,
            runtime=runtime,
            env=env,
        )
        # `build_plugin_context()` 的返回类型是 `PluginContext`（那是它存在的理由：
        # 静态证明一致性）。装配根还要按 `EDG-104` 收走 ctx 派生的任务，因此在这里窄化
        # 一次——唯一的构造点就在同一个文件里，这个 `isinstance` 不可能不成立。
        assert isinstance(ctx, RuntimePluginContext)  # noqa: S101
        contexts.append(ctx)
        bus.publish(EventName.PLUGIN_DISCOVERED, payload={"plugin": manifest.id})
        return ctx

    return await wire_capabilities(manifests=manifests, context_for=context_for, keep=keep_with_cli)


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
    loaded = _load_config_or_report(layout, env=env, overrides=overrides, home=home)
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
    selected = _select_manifests(manifests, config)

    # 4–7 注册 → 解析覆盖 → 冻结。外部插件的发现是 `D25`/`D27`；这条路径两者共用。
    runtime = PluginRuntime()
    contexts: list[RuntimePluginContext] = []
    wiring = await _wire(
        selected, config, layout, loaded.workspace_root, bus, runtime, env, contexts
    )
    if cli_entry_from(wiring.registry) is None and any(
        decl.kind is CapabilityKind.CLI_ENTRY
        for manifest in selected
        for decl in manifest.capabilities
    ):
        # `EDG-108`/`BAS-010`：覆盖 CLI 的提供方没交出实现，强制回落到内建实现。
        # 重装一次而不是打补丁——半装好的 registry 已经冻结，改它比重来更容易出错。
        contexts.clear()
        wiring = await _wire(
            selected,
            config,
            layout,
            loaded.workspace_root,
            bus,
            runtime,
            env,
            contexts,
            builtin_cli_only=True,
        )
    for outcome in wiring.outcomes:
        bus.publish(
            EventName.PLUGIN_LOADED if outcome.error is None else EventName.PLUGIN_LOAD_FAILED,
            payload={"provider": str(outcome.provider)},
            error=outcome.error,
        )
    wiring.report.raise_if_failed()

    # 8 必需能力
    registry = wiring.registry
    sessions = _require_sessions(registry)
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
        sessions=sessions,
        model=model,
        model_id=model_id,
        model_info=model_info,
        cli=cli.value,
        contexts=tuple(contexts),
        runtime=runtime,
        lock=lock,
        closers=closers,
    )
    return instance


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
    sessions: SessionStore,
    model: ModelProvider,
    model_id: str,
    model_info: ModelInfo | None,
    cli: CliEntry,
    contexts: tuple[RuntimePluginContext, ...],
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
    diagnostics = Diagnostics(events=ring, capabilities_source=lambda: wiring.report)
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
        runtime=runtime,
        lock=lock,
        closers=tuple(closers),
    )


def _config_document(loaded: LoadedConfig) -> Mapping[str, JsonValue]:
    """`/config` 看到的那棵树。`to_json()` 的 `config` 段就是它。"""
    document = loaded.to_json()["config"]
    return document if isinstance(document, Mapping) else {}


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
    loaded = _load_config_or_report(layout, env=env, overrides=None, home=home)
    selected = tuple(
        manifest
        for manifest in _select_manifests(manifests, loaded.config)
        if any(decl.kind is CapabilityKind.SESSION_STORE for decl in manifest.capabilities)
    )
    bus = EventBus(InstanceId(layout.root.name))
    wiring = await _wire(
        selected,
        loaded.config,
        layout,
        loaded.workspace_root,
        bus,
        PluginRuntime(),
        env,
        [],
    )
    wiring.report.raise_if_failed()
    return loaded, _require_sessions(wiring.registry)
