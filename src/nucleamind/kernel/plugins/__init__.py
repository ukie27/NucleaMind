"""插件运行时（宿主侧）：唯一的注册分派与静态清单 bootstrap（技术方案 §6.1、§7.3、§7.5）。

职责：re-export `declarations`（注册意图的 kernel 投影）、`discovery`（两条显式来源的
插件发现）、`host`（唯一的 Host `NucleaAPI` 实现）、`capabilities`（五个单值 kind 的载荷
形状与取回函数）与 `builtin_loader`（把一批 `LoadRequest` 跑成注册）与 `permissions`（权限账本）的公开表面。
不负责：校验 manifest、构造 `PluginContext`、实现被守卫的资源门面、决定谁被启用——
那些分别在 `sdk/manifest.py`、`runtime/plugin_context.py`、`runtime/access/` 与 `runtime/`；
本包不读配置、不访问网络（`permissions.py` 只读写 `permissions.json` 那一个文件）。

包内依赖单向：`declarations`、`capabilities`、`discovery` 与 `permissions` 互不相识，
`host` 用前两个，`builtin_loader` 用 `host`。

**本包不 import `sdk/`**（规则 `R2`）。因此 manifest 到 `LoadRequest` 的翻译不在这里，
而在 `runtime/wiring.py`——这也正是内建与外部插件共用同一条注册路径的落点：两者只在
「谁产出 `LoadRequest`」上不同，注册接口完全一致（`SDK-007`）。
"""

from __future__ import annotations

from .builtin_loader import LoadOutcome, RegistrationHost, SetupFn, import_setup, load_into
from .capabilities import (
    CapabilityBinding,
    ChannelBinding,
    CliEntryBinding,
    MemoryProviderBinding,
    ModelProviderBinding,
    RegisteredChannel,
    RegisteredCliEntry,
    RegisteredMemoryProvider,
    RegisteredModelProvider,
    RegisteredSessionStore,
    SessionStoreBinding,
    channels_from,
    cli_entry_from,
    memory_providers_from,
    model_providers_from,
    session_store_from,
)
from .declarations import CapabilityDeclaration, LoadRequest
from .discovery import (
    ENTRY_POINT_GROUP,
    MANIFEST_ATTRIBUTE,
    MANIFEST_FILENAME,
    Discovery,
    EntryPointLister,
    PluginCandidate,
    SourceKind,
    discover,
    installed_entry_points,
    read_candidate,
)
from .host import CapabilityHost
from .permissions import (
    LEDGER_VERSION,
    Decision,
    Grant,
    LedgerDecision,
    LedgerEntry,
    PermissionLedger,
    PluginGrants,
    format_permission,
    parse_permission,
)

__all__ = [
    "ENTRY_POINT_GROUP",
    "LEDGER_VERSION",
    "MANIFEST_ATTRIBUTE",
    "MANIFEST_FILENAME",
    "CapabilityBinding",
    "CapabilityDeclaration",
    "CapabilityHost",
    "ChannelBinding",
    "CliEntryBinding",
    "Decision",
    "Discovery",
    "EntryPointLister",
    "Grant",
    "LedgerDecision",
    "LedgerEntry",
    "LoadOutcome",
    "LoadRequest",
    "MemoryProviderBinding",
    "ModelProviderBinding",
    "PermissionLedger",
    "PluginCandidate",
    "PluginGrants",
    "RegisteredChannel",
    "RegisteredCliEntry",
    "RegisteredMemoryProvider",
    "RegisteredModelProvider",
    "RegisteredSessionStore",
    "RegistrationHost",
    "SessionStoreBinding",
    "SetupFn",
    "SourceKind",
    "channels_from",
    "cli_entry_from",
    "discover",
    "format_permission",
    "import_setup",
    "installed_entry_points",
    "load_into",
    "memory_providers_from",
    "model_providers_from",
    "parse_permission",
    "read_candidate",
    "session_store_from",
]
