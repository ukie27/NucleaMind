"""实例布局、配置加载与实例锁（技术方案 §6.7、§10.1 步骤 1–2、§11）。

职责：re-export 本包九个模块的公开表面，使调用方只需 `from nucleamind.kernel.config
import ...` 一条导入路径；`load_config()` 是这里的主入口。
不负责：获取实例锁（`InstanceLock` 由 `runtime/bootstrap.py` 在生命周期里持有）、
读写实例目录里除 `config.json` 之外的任何文件、加载插件（`D25`）。

模块间依赖是单向的：`layout` / `process` / `merge` 互不相识，`lock` 只用 `process`，
`fields` 谁都不认识，`schema` 用 `fields` 与 `merge` 的 pointer 工具、`secrets` 只用后者，`sources` 只产出 `merge` 的层，
`loader` 编排全部。配置的四层优先级只在 `sources.collect_layers()` 的返回顺序里定义一次。

`secrets` 刻意不接进 `load_config()`：`SecretStr` 不是 `JsonValue`，塞进合并后的文档会让
`validate_config()` 无从校验；`${VAR}` 在加载路径上就是一个普通字符串。接线在 `D19`
（provider 凭据）与 `D26`（`ctx.secret()`）。
"""

from __future__ import annotations

from .fields import FieldKind, FieldSpec
from .layout import (
    CONFIG_FILENAME,
    DEFAULT_INSTANCE_NAME,
    INSTANCE_DIR_ENV,
    INSTANCE_NAME_ENV,
    LOCK_FILENAME,
    LOGS_DIRNAME,
    PERMISSIONS_FILENAME,
    PLUGINS_DIRNAME,
    SESSIONS_DIRNAME,
    WORKSPACE_DIRNAME,
    InstanceLayout,
)
from .loader import LoadedConfig, load_config
from .lock import InstanceLock, LockInfo, StaleLockReclaimed
from .merge import ConfigLayer, MergeResult, escape_pointer_token, merge_layers, pointer_of
from .process import Liveness, process_is_alive, process_started_at
from .schema import (
    SECTION_SPECS,
    SESSION_CONCURRENCY_CHOICES,
    ContextSection,
    HooksSection,
    LoggingSection,
    ModelSection,
    NucleaConfig,
    PluginEntry,
    PluginsSection,
    RoutingSection,
    TurnSection,
    WorkspaceSection,
    defaults,
    validate_config,
)
from .secrets import (
    SECRET_REF_PATTERN,
    SecretMap,
    SecretRef,
    contains_secret_ref,
    prepare_for_write,
    resolve_secrets,
    resolve_text,
    scan_secret_refs,
    secret_ref_names,
)
from .sources import (
    CLI_ORIGIN,
    DEFAULT_ORIGIN,
    ENV_ORIGIN,
    ENV_PREFIX,
    FILE_ORIGIN,
    collect_layers,
    env_layer,
    file_layer,
    overrides_layer,
    parse_override,
    read_config_file,
)

__all__ = [
    "CLI_ORIGIN",
    "CONFIG_FILENAME",
    "DEFAULT_INSTANCE_NAME",
    "DEFAULT_ORIGIN",
    "ENV_ORIGIN",
    "ENV_PREFIX",
    "FILE_ORIGIN",
    "INSTANCE_DIR_ENV",
    "INSTANCE_NAME_ENV",
    "LOCK_FILENAME",
    "LOGS_DIRNAME",
    "PERMISSIONS_FILENAME",
    "PLUGINS_DIRNAME",
    "SECRET_REF_PATTERN",
    "SECTION_SPECS",
    "SESSIONS_DIRNAME",
    "WORKSPACE_DIRNAME",
    "ConfigLayer",
    "ContextSection",
    "SESSION_CONCURRENCY_CHOICES",
    "FieldKind",
    "FieldSpec",
    "HooksSection",
    "InstanceLayout",
    "InstanceLock",
    "Liveness",
    "LoadedConfig",
    "LockInfo",
    "LoggingSection",
    "MergeResult",
    "ModelSection",
    "NucleaConfig",
    "PluginEntry",
    "PluginsSection",
    "RoutingSection",
    "SecretMap",
    "SecretRef",
    "StaleLockReclaimed",
    "TurnSection",
    "WorkspaceSection",
    "collect_layers",
    "contains_secret_ref",
    "defaults",
    "env_layer",
    "escape_pointer_token",
    "file_layer",
    "load_config",
    "merge_layers",
    "overrides_layer",
    "parse_override",
    "pointer_of",
    "prepare_for_write",
    "process_is_alive",
    "process_started_at",
    "read_config_file",
    "resolve_secrets",
    "resolve_text",
    "scan_secret_refs",
    "secret_ref_names",
    "validate_config",
]
