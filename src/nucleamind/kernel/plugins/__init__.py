"""插件运行时（宿主侧）：唯一的注册分派与静态清单 bootstrap（技术方案 §6.1、§7.3、§7.5）。

职责：re-export `declarations`（注册意图的 kernel 投影）、`host`（唯一的 Host `NucleaAPI`
实现）、`capabilities`（五个单值 kind 的载荷形状与取回函数）与 `builtin_loader`
（把一批 `LoadRequest` 跑成注册）的公开表面。
不负责：发现插件、校验 manifest、构造 `PluginContext` 与权限判定——那些分别在 `D25`、
`D26`、`D27`；本包不读配置、不访问网络。

包内依赖单向：`declarations` 与 `capabilities` 互不相识，`host` 用这两个，
`builtin_loader` 用 `host`。

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
from .host import CapabilityHost

__all__ = [
    "CapabilityBinding",
    "CapabilityDeclaration",
    "CapabilityHost",
    "ChannelBinding",
    "CliEntryBinding",
    "LoadOutcome",
    "LoadRequest",
    "MemoryProviderBinding",
    "ModelProviderBinding",
    "RegisteredChannel",
    "RegisteredCliEntry",
    "RegisteredMemoryProvider",
    "RegisteredModelProvider",
    "RegisteredSessionStore",
    "RegistrationHost",
    "SessionStoreBinding",
    "SetupFn",
    "channels_from",
    "cli_entry_from",
    "import_setup",
    "load_into",
    "memory_providers_from",
    "model_providers_from",
    "session_store_from",
]
