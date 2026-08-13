"""配置 schema 与校验（技术方案 §6.7、`CFG-001`、`EDG-501`）。

职责：用一张声明式字段表定义**有哪些配置字段**、它们的默认值与所属小节，校验合并后的
JSON，并把每处问题连同 JSON Pointer 位置一起报出来；`TurnSection.to_limits()` 把 turn
小节转成 `TurnLimits`。
不负责：逐字段的类型校验积木（`fields.py`）、读取任何来源（`sources.py`）、分层合并
（`merge.py`）、决定 workspace 的最终绝对路径（`loader.py`）。

**不用 pydantic，手写校验。** 技术方案 §6.7 的字面表述是「代码中的 Pydantic default」，
这里取其意不取其形：规范性的两条（`extra="forbid"`、JSON Pointer 位置）都照做，实现方式
另选。三个理由，按分量排序：

1. `CFG-005` 要求每个生效值可追溯来源，这就要求默认值层**物化成一份 dict**（`defaults()`）
   才能和其它层一样带上来源。默认值一旦是 dict，合并与来源追踪就已经全在 `merge.py` 里
   自己写了，pydantic 剩下的贡献只是校验十几个字段的类型。
2. pydantic 的 `ValidationError.loc` 是元组，仍要自己转成 RFC 6901；而 `sdk/manifest.py`
   的 `_format_location` 产出点分路径且**不能 import**（`R2`）。
3. 实测 `import pydantic` 约 90 ms、连带把 `kernel.config` 的导入推到 300 ms 以上，而
   `NFR-405` 给整个冷启动的预算就是 300 ms。配置加载在启动第 2 步、永远在路径上
   （`sdk/manifest.py` 只在真的要发现插件时才付这笔钱）。
   `test_loading_config_does_not_import_pydantic` 是这条约束的可执行形态。

**`detail` 里绝不放配置值**，只放指针、类型名与变量名：密钥可以出现在任何指针上
（`/plugins/acme/config/api_key`），而 `contracts.redact` 按**键名**判定，一个通用的
`{"value": ...}` 键正好绕过它。这条规则顺带预先满足 `D11` 的哨兵测试。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final, Mapping

from ...contracts import ErrorCode, NucleaError
from . import plugin_blocks as blocks
from .fields import (
    FieldKind,
    FieldSpec,
    bool_at,
    coerce_value,
    int_at,
    issue,
    opt_int_at,
    opt_str_at,
    str_at,
    str_tuple_at,
    suggest,
)
from .merge import pointer_of
from .plugin_blocks import PluginEntry

if TYPE_CHECKING:
    from ...contracts import JsonValue
    from ..turn.limits import TurnLimits

__all__ = [
    "IGNORED_TOP_LEVEL_KEYS",
    "SCHEMA_KEY",
    "SECTION_SPECS",
    "SESSION_CONCURRENCY_CHOICES",
    "ContextSection",
    "HooksSection",
    "LoggingSection",
    "ModelSection",
    "NucleaConfig",
    "PluginEntry",
    "PluginsSection",
    "RoutingSection",
    "TurnSection",
    "WorkspaceSection",
    "defaults",
    "validate_config",
]

#: 生成的 `config.json` 里那句 schema 引用（`D24`）。它**不是**配置字段：编辑器读它，
#: 运行期忽略它。
SCHEMA_KEY: Final = "$schema"

#: 顶层放行、但不参与校验的键。目前只有一个，而且它必须是**具名的一条**而不是
#: 「以 `$` 开头就放行」那种规则——后者会让任何拼错成 `$turn` 的小节静默消失。
#: 这是全项目第二处对未知键让路的地方，第一处是 `plugins` 小节里的插件 id。
IGNORED_TOP_LEVEL_KEYS: Final[tuple[str, ...]] = (SCHEMA_KEY,)

#: turn 六项预算的默认值。**与 `kernel/turn/limits.py` 的 `DEFAULT_*` 必须逐一相等**，
#: 由 `test_turn_defaults_match_the_limits_module` 盯着。
#:
#: 这里重写字面量而不是 import 那些常量，是为了不把 turn 引擎拖上配置路径：import
#: `kernel.turn.limits` 会执行 `kernel/turn/__init__.py`，连带 engine / scheduling /
#: folding 与 asyncio 一起进来，而 `nm config show` 与诊断只需要六个整数。
DEFAULT_MAX_ITERATIONS: Final = 16
DEFAULT_MAX_TOOL_CALLS_PER_TURN: Final = 48
DEFAULT_TOOL_TIMEOUT_MS: Final = 120_000
DEFAULT_TOOL_RESULT_MAX_BYTES: Final = 65_536
DEFAULT_TURN_TIMEOUT_MS: Final = 900_000

#: 路由的五项默认值。**与 `kernel/routing/` 的同名 `DEFAULT_*` 必须逐一相等**，由
#: `test_routing_defaults_match_the_routing_package` 盯着。这里同样重写字面量而不是 import：
#: `kernel.routing` 会把 asyncio 与调度器一起拖上配置路径，而 `nm config show` 不需要它们。
DEFAULT_COMMAND_PREFIX: Final = "/"
DEFAULT_SESSION_CONCURRENCY: Final = "queue"
DEFAULT_QUEUE_MAX_SIZE: Final = 32
DEFAULT_DEDUP_CAPACITY: Final = 4096
DEFAULT_DEDUP_TTL_MS: Final = 600_000

#: `session_concurrency` 的合法取值，与 `routing.ConcurrencyPolicy` 的三个取值同名。
SESSION_CONCURRENCY_CHOICES: Final = ("queue", "merge", "reject")

#: Hook 与 Context Provider 的三项超时（技术方案 §6.6、§10.2 第 7 步 b）。
#: **与 `kernel/turn/hooks.py` 与 `context_builder.py` 的同名 `DEFAULT_*` 必须逐一相等**，
#: 由 `test_orchestration_defaults_match_the_turn_package` 盯着。同样重写字面量而不是
#: import：`kernel.turn` 会把 engine 与 asyncio 拖上配置路径（见上面的注释）。
DEFAULT_OBSERVER_TIMEOUT_MS: Final = 2_000
DEFAULT_INTERCEPTOR_TIMEOUT_MS: Final = 5_000
DEFAULT_CONTEXT_PROVIDER_TIMEOUT_MS: Final = 3_000


#: 全部已知字段。**这是 `extra="forbid"` 的唯一依据**：不在表里的键即未知字段。
#: `D11`（secrets）/`D12`（可观测性）/`D19` 在此扩展，不要在别处另开一张表。
SECTION_SPECS: Final[Mapping[str, Mapping[str, FieldSpec]]] = {
    "turn": {
        "max_iterations": FieldSpec(FieldKind.POSITIVE_INT, DEFAULT_MAX_ITERATIONS),
        "max_tool_calls_per_turn": FieldSpec(
            FieldKind.POSITIVE_INT, DEFAULT_MAX_TOOL_CALLS_PER_TURN
        ),
        "tool_timeout_ms": FieldSpec(FieldKind.POSITIVE_INT, DEFAULT_TOOL_TIMEOUT_MS),
        "tool_result_max_bytes": FieldSpec(
            FieldKind.POSITIVE_INT, DEFAULT_TOOL_RESULT_MAX_BYTES
        ),
        "turn_timeout_ms": FieldSpec(FieldKind.POSITIVE_INT, DEFAULT_TURN_TIMEOUT_MS),
        "context_max_tokens": FieldSpec(FieldKind.OPTIONAL_POSITIVE_INT, None),
    },
    "workspace": {
        "root": FieldSpec(FieldKind.OPTIONAL_STR, None),
    },
    "routing": {
        "command_prefix": FieldSpec(FieldKind.STR, DEFAULT_COMMAND_PREFIX),
        "session_concurrency": FieldSpec(
            FieldKind.STR, DEFAULT_SESSION_CONCURRENCY, SESSION_CONCURRENCY_CHOICES
        ),
        "queue_max_size": FieldSpec(FieldKind.POSITIVE_INT, DEFAULT_QUEUE_MAX_SIZE),
        "dedup_capacity": FieldSpec(FieldKind.POSITIVE_INT, DEFAULT_DEDUP_CAPACITY),
        "dedup_ttl_ms": FieldSpec(FieldKind.POSITIVE_INT, DEFAULT_DEDUP_TTL_MS),
    },
    "plugins": {
        "disable": FieldSpec(FieldKind.STR_LIST, ()),
        "search_paths": FieldSpec(FieldKind.STR_LIST, ()),
    },
    "hooks": {
        "observer_timeout_ms": FieldSpec(FieldKind.POSITIVE_INT, DEFAULT_OBSERVER_TIMEOUT_MS),
        "interceptor_timeout_ms": FieldSpec(
            FieldKind.POSITIVE_INT, DEFAULT_INTERCEPTOR_TIMEOUT_MS
        ),
    },
    "context": {
        "provider_timeout_ms": FieldSpec(
            FieldKind.POSITIVE_INT, DEFAULT_CONTEXT_PROVIDER_TIMEOUT_MS
        ),
    },
    "model": {
        "provider": FieldSpec(FieldKind.OPTIONAL_STR, None),
        "name": FieldSpec(FieldKind.OPTIONAL_STR, None),
    },
    "logging": {
        "level": FieldSpec(FieldKind.STR, "info"),
        "file_enabled": FieldSpec(FieldKind.BOOL, True),
    },
}


@dataclass(frozen=True, slots=True)
class TurnSection:
    """一次 turn 的预算。字段名与 `LimitKind` 的取值逐一对应（`limits.py` 的约定）。"""

    max_iterations: int = DEFAULT_MAX_ITERATIONS
    max_tool_calls_per_turn: int = DEFAULT_MAX_TOOL_CALLS_PER_TURN
    tool_timeout_ms: int = DEFAULT_TOOL_TIMEOUT_MS
    tool_result_max_bytes: int = DEFAULT_TOOL_RESULT_MAX_BYTES
    turn_timeout_ms: int = DEFAULT_TURN_TIMEOUT_MS
    #: `None` = 由模型能力推导，不是「无限制」。见 `TurnLimits.resolve_context_max_tokens`。
    context_max_tokens: int | None = None

    def to_limits(self) -> TurnLimits:
        """转成 `TurnLimits`。

        **函数内 import 是刻意的**：见 `DEFAULT_MAX_ITERATIONS` 的注释——只有真的要构造
        `TurnLimits` 的调用方（编排层）才付得起把 turn 包导入进来的代价。
        """
        from ..turn.limits import TurnLimits as _TurnLimits

        return _TurnLimits(
            max_iterations=self.max_iterations,
            max_tool_calls_per_turn=self.max_tool_calls_per_turn,
            tool_timeout_ms=self.tool_timeout_ms,
            tool_result_max_bytes=self.tool_result_max_bytes,
            turn_timeout_ms=self.turn_timeout_ms,
            context_max_tokens=self.context_max_tokens,
        )


@dataclass(frozen=True, slots=True)
class RoutingSection:
    """输入分流与 Session 并发（`D13`）。字段与 `kernel/routing/` 的构造参数一一对应。

    `command_prefix` 是路由的配置项而不是命令身份的一部分（见 `contracts/command.py`）：
    改前缀不该等于改全部命令声明。
    """

    command_prefix: str = DEFAULT_COMMAND_PREFIX
    #: `queue` / `merge` / `reject`，取值由 `SESSION_CONCURRENCY_CHOICES` 限定。
    session_concurrency: str = DEFAULT_SESSION_CONCURRENCY
    #: 单个 session 的等待上限；超出即降级为拒绝，不静默丢弃（`EDG-202`）。
    queue_max_size: int = DEFAULT_QUEUE_MAX_SIZE
    dedup_capacity: int = DEFAULT_DEDUP_CAPACITY
    dedup_ttl_ms: int = DEFAULT_DEDUP_TTL_MS


@dataclass(frozen=True, slots=True)
class HooksSection:
    """Hook 分发的两项超时（技术方案 §6.6）。

    观察者是**整批**超时、拦截器是**每个 handler** 超时：前者并发执行、返回值被忽略，
    整体拖不动 turn 就行；后者串行且能改流水线，一个慢 handler 会连累后面全部。
    """

    observer_timeout_ms: int = DEFAULT_OBSERVER_TIMEOUT_MS
    interceptor_timeout_ms: int = DEFAULT_INTERCEPTOR_TIMEOUT_MS


@dataclass(frozen=True, slots=True)
class ContextSection:
    """Context 组装（技术方案 §10.2 第 7 步 b）。

    `context_max_tokens` **不在这里**：它是 turn 的六项预算之一，字段名与 `LimitKind`
    的取值一一对应，搬过来会破坏那条已被测试钉死的对应关系。
    """

    #: 单个 Context Provider 的独立超时。超时按其关键性中止或跳过（`CTX-005`、`EDG-302`）。
    provider_timeout_ms: int = DEFAULT_CONTEXT_PROVIDER_TIMEOUT_MS


@dataclass(frozen=True, slots=True)
class WorkspaceSection:
    """workspace 位置。`None` = 用实例目录下的 `workspace/`（`InstanceLayout.workspace_dir`）。"""

    root: str | None = None


@dataclass(frozen=True, slots=True)
class PluginsSection:
    """插件加载的开关与逐插件的配置块。真正的加载在 `D25`，这里只固定配置形状。

    `disable` / `search_paths` 是**保留键**，`plugins` 小节里其余的键都是插件 id
    （技术方案 §6.7 的 `plugins.<plugin_id>.config`），形状校验在 `plugin_blocks.py`。
    """

    #: 显式禁用的插件 id。id 形状由 `D25` 用 `contracts` 的解析器校验。
    disable: tuple[str, ...] = ()
    #: 额外的插件搜索路径，在 `InstanceLayout.plugins_dir` 之外。
    search_paths: tuple[str, ...] = ()
    #: 插件 id -> 它的 `{config, secrets}`。装配根按 id 取，取不到就给空块。
    entries: Mapping[str, PluginEntry] = blocks.NO_PLUGIN_ENTRIES

    def entry(self, plugin_id: str) -> PluginEntry:
        """取一个插件的条目。**没配过不是错误**——每个字段都有默认值的插件应当免配置可用。"""
        return self.entries.get(plugin_id, PluginEntry())


@dataclass(frozen=True, slots=True)
class ModelSection:
    """默认模型选择。provider 凭据不在配置文件里（只走环境变量，§6.7）。"""

    provider: str | None = None
    name: str | None = None


@dataclass(frozen=True, slots=True)
class LoggingSection:
    """事件 sink 的开关。sink 实现在 `D12`。"""

    level: str = "info"
    #: 写 `logs/events-<date>.jsonl`。
    file_enabled: bool = True


@dataclass(frozen=True, slots=True)
class NucleaConfig:
    """整份配置。所有小节都有默认值——缺失的 `config.json` 因此是完全合法的状态。"""

    turn: TurnSection = field(default_factory=TurnSection)
    routing: RoutingSection = field(default_factory=RoutingSection)
    hooks: HooksSection = field(default_factory=HooksSection)
    context: ContextSection = field(default_factory=ContextSection)
    workspace: WorkspaceSection = field(default_factory=WorkspaceSection)
    plugins: PluginsSection = field(default_factory=PluginsSection)
    model: ModelSection = field(default_factory=ModelSection)
    logging: LoggingSection = field(default_factory=LoggingSection)

    def to_json(self) -> dict[str, JsonValue]:
        """诊断视图。元组转列表，保证真能被 `json.dumps` 编码。"""
        return {
            "turn": {
                "max_iterations": self.turn.max_iterations,
                "max_tool_calls_per_turn": self.turn.max_tool_calls_per_turn,
                "tool_timeout_ms": self.turn.tool_timeout_ms,
                "tool_result_max_bytes": self.turn.tool_result_max_bytes,
                "turn_timeout_ms": self.turn.turn_timeout_ms,
                "context_max_tokens": self.turn.context_max_tokens,
            },
            "workspace": {"root": self.workspace.root},
            "routing": {
                "command_prefix": self.routing.command_prefix,
                "session_concurrency": self.routing.session_concurrency,
                "queue_max_size": self.routing.queue_max_size,
                "dedup_capacity": self.routing.dedup_capacity,
                "dedup_ttl_ms": self.routing.dedup_ttl_ms,
            },
            "hooks": {
                "observer_timeout_ms": self.hooks.observer_timeout_ms,
                "interceptor_timeout_ms": self.hooks.interceptor_timeout_ms,
            },
            "context": {"provider_timeout_ms": self.context.provider_timeout_ms},
            "plugins": {
                "disable": list(self.plugins.disable),
                "search_paths": list(self.plugins.search_paths),
                **blocks.entries_to_json(self.plugins.entries),
            },
            "model": {"provider": self.model.provider, "name": self.model.name},
            "logging": {"level": self.logging.level, "file_enabled": self.logging.file_enabled},
        }


def defaults() -> dict[str, JsonValue]:
    """把默认值物化成一层原始 JSON。

    `CFG-005` 的来源追踪要求默认值和其它层同形：只有这样「这个值取自默认值」才是一个
    可以回答的问题，而不是「查不到来源」的兜底解释。
    """
    return {
        section: {name: spec.default for name, spec in fields.items()}
        for section, fields in SECTION_SPECS.items()
    }


def _validate_section(
    name: str,
    raw: JsonValue,
    issues: list[NucleaError],
) -> dict[str, JsonValue]:
    """校验一个小节，返回**已逐字段校验过**的取值映射（缺席的字段不出现在里面）。

    这里刻意不构造 dataclass：小节各有各的字段类型，泛型地 `**values` 展开会把每个字段
    都退化成 `JsonValue`。构造留给 `validate_config` 里五处具名调用，那里类型才收得回来。
    """
    specs = SECTION_SPECS[name]
    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        issues.append(
            issue(ErrorCode.CONFIG_INVALID, "该小节必须是 JSON 对象。", pointer_of([name]))
        )
        return {}

    values: dict[str, JsonValue] = {}
    # `plugins` 小节里的未知键**不是**未知字段，而是插件 id（技术方案 §6.7 的
    # `plugins.<plugin_id>.config`）。它们的形状由 `plugin_blocks.py` 校验，
    # 因此这里不能一并报成 `CONFIG_UNKNOWN_FIELD`。
    if name != blocks.PLUGINS_SECTION:
        for key in raw:
            if key not in specs:
                issues.append(
                    issue(
                        ErrorCode.CONFIG_UNKNOWN_FIELD,
                        f"未知配置字段。{suggest(key, list(specs))}",
                        pointer_of([name, key]),
                    )
                )
    for field_name, spec in specs.items():
        if field_name not in raw:
            continue
        adopted, problem = coerce_value(raw[field_name], spec, pointer_of([name, field_name]))
        if problem is not None:
            issues.append(problem)
            continue
        values[field_name] = adopted
    return values


def validate_config(data: Mapping[str, JsonValue]) -> NucleaConfig:
    """校验合并后的配置。失败时抛错，**一次报出全部问题**。

    逐条抛出会让用户改一个键、重启、再看到下一个错误。因此先把全部问题收集起来，
    再用第一处的错误码抛出，完整清单挂在 `detail["errors"]`——单个未知字段因此仍然得到
    `CONFIG_UNKNOWN_FIELD`（`CFG-001`），而不是一个笼统的「配置无效」。

    **异常约定**：任何一处问题即抛 `NucleaError`，`detail["errors"]` 的每项含
    `pointer` / `code` / `reason`；绝不含配置值本身。
    """
    issues: list[NucleaError] = []

    for key in data:
        if key in IGNORED_TOP_LEVEL_KEYS:
            # `$schema` 是给编辑器的，不是配置字段。放行它是 `D24` 的显式决定：
            # 生成的初始配置引用一份派生 schema，若这里报未知字段，刚生成的文件下一次
            # 启动就会失败——那是最糟的首次体验。
            continue
        if key not in SECTION_SPECS:
            issues.append(
                issue(
                    ErrorCode.CONFIG_UNKNOWN_FIELD,
                    f"未知配置小节。{suggest(key, list(SECTION_SPECS))}",
                    pointer_of([key]),
                )
            )

    sections = {name: _validate_section(name, data.get(name), issues) for name in SECTION_SPECS}
    raw_plugins = data.get(blocks.PLUGINS_SECTION)
    plugin_entries = (
        blocks.validate_plugin_entries(raw_plugins, issues) if isinstance(raw_plugins, Mapping) else {}
    )

    if issues:
        errors: list[JsonValue] = [
            {
                "pointer": str(issue.detail.get("pointer", "")),
                "code": issue.code.value,
                "reason": issue.user_message,
            }
            for issue in issues
        ]
        raise NucleaError(
            issues[0].code,
            f"配置校验失败，共 {len(errors)} 处问题。",
            detail={"errors": errors},
        )

    # 逐个具名构造而不是 `**sections`：小节的字段类型在这里才收窄回具体形状，
    # 展开一个 `dict[str, JsonValue]` 会让每个字段都退化成 `JsonValue`。
    turn = sections["turn"]
    routing = sections["routing"]
    hooks = sections["hooks"]
    plugins = sections["plugins"]
    model = sections["model"]
    logging_values = sections["logging"]
    return NucleaConfig(
        turn=TurnSection(
            max_iterations=int_at(turn, "max_iterations", DEFAULT_MAX_ITERATIONS),
            max_tool_calls_per_turn=int_at(
                turn, "max_tool_calls_per_turn", DEFAULT_MAX_TOOL_CALLS_PER_TURN
            ),
            tool_timeout_ms=int_at(turn, "tool_timeout_ms", DEFAULT_TOOL_TIMEOUT_MS),
            tool_result_max_bytes=int_at(
                turn, "tool_result_max_bytes", DEFAULT_TOOL_RESULT_MAX_BYTES
            ),
            turn_timeout_ms=int_at(turn, "turn_timeout_ms", DEFAULT_TURN_TIMEOUT_MS),
            context_max_tokens=opt_int_at(turn, "context_max_tokens"),
        ),
        workspace=WorkspaceSection(root=opt_str_at(sections["workspace"], "root")),
        routing=RoutingSection(
            command_prefix=str_at(routing, "command_prefix", DEFAULT_COMMAND_PREFIX),
            session_concurrency=str_at(
                routing, "session_concurrency", DEFAULT_SESSION_CONCURRENCY
            ),
            queue_max_size=int_at(routing, "queue_max_size", DEFAULT_QUEUE_MAX_SIZE),
            dedup_capacity=int_at(routing, "dedup_capacity", DEFAULT_DEDUP_CAPACITY),
            dedup_ttl_ms=int_at(routing, "dedup_ttl_ms", DEFAULT_DEDUP_TTL_MS),
        ),
        hooks=HooksSection(
            observer_timeout_ms=int_at(
                hooks, "observer_timeout_ms", DEFAULT_OBSERVER_TIMEOUT_MS
            ),
            interceptor_timeout_ms=int_at(
                hooks, "interceptor_timeout_ms", DEFAULT_INTERCEPTOR_TIMEOUT_MS
            ),
        ),
        context=ContextSection(
            provider_timeout_ms=int_at(
                sections["context"], "provider_timeout_ms", DEFAULT_CONTEXT_PROVIDER_TIMEOUT_MS
            ),
        ),
        plugins=PluginsSection(
            disable=str_tuple_at(plugins, "disable"),
            search_paths=str_tuple_at(plugins, "search_paths"),
            entries=plugin_entries,
        ),
        model=ModelSection(
            provider=opt_str_at(model, "provider"),
            name=opt_str_at(model, "name"),
        ),
        logging=LoggingSection(
            level=str_at(logging_values, "level", "info"),
            file_enabled=bool_at(logging_values, "file_enabled", True),
        ),
    )
