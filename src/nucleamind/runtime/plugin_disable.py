"""被禁用插件留下的空缺怎么办：`on_disable` 的判定（`D30`，技术方案 §10.4、`BAS-004`）。

职责：从「已启用但被 `plugins.disable` 关掉」的插件清单里找出它们**曾经声明过的覆盖**，
要求用户对每一个显式表态，并把 `leave_missing` 翻译成 registry 认识的按能力抑制表。
不负责：发现与读取 manifest（`inventory.py`）、按提供方禁用（`bootstrap.select_manifests`
与 `build_inventory`）、判定谁覆盖谁（`kernel/registry/resolution.py`）。本模块不读文件、
不访问网络，是一个纯函数加一条错误。

**这是 `R5` 的落点**，与 `inventory.py` / `plugin_plan.py` 同一条理由：`PluginManifest` 与
`CapabilityDecl` 在 `sdk/`，而 `R2` 禁止 `kernel/` 认识它们，因此「manifest 的 `overrides`
→ `SuppressedCapabilities`」的翻译只能发生在唯一同时看得见两侧的这一层。

**为什么必须显式表态**：一个插件覆盖了 `builtin:jsonl` 之后被 `plugins.disable` 关掉，
今天的行为是内建自动复活——因为被禁用的插件根本没注册，覆盖关系于是不存在。那正是
`BAS-004` 禁止的「隐式恢复」，而且它不是无害的：用户可能是因为不再信任那份存储才关掉
插件的，会话历史悄悄换回另一个后端等于替他做了一个关于数据的决定。所以这里既不替他
恢复、也不替他留空，而是拒绝启动并指出那一个键。

**只在真的发生过覆盖时才要求表态**。没有 `overrides` 的插件被禁用只是少了一项能力，
没有「要不要回来」这个问题，`on_disable` 写不写都一样。
"""

from __future__ import annotations

from collections.abc import Iterable

from nucleamind.contracts import (
    CapabilityKind,
    ErrorCode,
    NucleaError,
    ProviderId,
    parse_capability_target,
)
from nucleamind.kernel.config import NucleaConfig, OnDisable
from nucleamind.kernel.registry import SuppressedCapabilities
from nucleamind.sdk import PluginManifest

from .inventory import PluginInventory, SkippedPlugin, SkipReason

__all__ = [
    "LEAVE_MISSING_REASON",
    "DisabledOverride",
    "override_targets",
    "suppressed_capabilities",
]

#: `nm capabilities` 的「已禁用」段里那一行的原因。写成常量是因为它同时是用户看到的文案
#: 与测试断言的锚点；散在两处就会在改文案时安静地对不上。
LEAVE_MISSING_REASON = "覆盖它的插件已被禁用，且 on_disable=leave_missing"


class DisabledOverride:
    """一个被禁用的插件曾经声明过的一条覆盖。

    用类而不是元组，是因为出错信息要同时说出**谁**覆盖了**什么**——只印目标会让用户
    不知道该去哪个插件条目里写那个键。
    """

    __slots__ = ("kind", "name", "plugin_id", "provider")

    def __init__(
        self, *, plugin_id: str, kind: CapabilityKind, provider: ProviderId, name: str
    ) -> None:
        self.plugin_id = plugin_id
        self.kind = kind
        self.provider = provider
        self.name = name

    @property
    def key(self) -> tuple[CapabilityKind, ProviderId, str]:
        """`SuppressedCapabilities` 的键。kind 取自**声明覆盖的那一方**，与
        `kernel/registry/resolution.py` 的 `_TargetKey` 完全同构。"""
        return (self.kind, self.provider, self.name)

    @property
    def target(self) -> str:
        """给人看的目标串：`session_store:jsonl ← builtin`。"""
        return f"{self.kind.value}:{self.name} ← {self.provider}"


def override_targets(manifest: PluginManifest) -> tuple[DisabledOverride, ...]:
    """一份 manifest 里的全部覆盖声明。

    覆盖目标串只用 `parse_capability_target()` 解码——`AGENTS.md` 定死两侧共用它，
    这里不另写一份。manifest 在阶段 A 已经校验过，因此解码不会失败。
    """
    found: list[DisabledOverride] = []
    for decl in manifest.capabilities:
        if decl.overrides is None:
            continue
        provider, name = parse_capability_target(decl.overrides)
        found.append(
            DisabledOverride(
                plugin_id=manifest.id, kind=decl.kind, provider=provider, name=name
            )
        )
    return tuple(found)


def _disabled_with_manifest(inventory: PluginInventory) -> tuple[SkippedPlugin, ...]:
    """被 `plugins.disable` 关掉、且 manifest 读得出来的那些。

    读不出来的（manifest 为 `None`）已经在 `inventory.failures` 里留了记录，这里不再为
    它们编一条「它可能覆盖过什么」的猜测。
    """
    return tuple(
        item
        for item in inventory.skipped
        if item.reason is SkipReason.DISABLED and item.manifest is not None
    )


def _undeclared(overrides: Iterable[DisabledOverride]) -> NucleaError:
    """「覆盖了东西却没说要不要恢复」这条错误。

    `pointer` 指向**那一个要写的键**而不是整个 `plugins` 小节：`BAS-006` 对凭据要求的
    「指出配置位置和字段名」在这里同样成立，一条只说「配置有问题」的错误会让用户去翻文档。
    """
    items = sorted(overrides, key=lambda item: (item.plugin_id, item.target))
    first = items[0]
    return NucleaError(
        ErrorCode.CONFIG_INVALID,
        "被禁用的插件覆盖过其他能力，必须显式说明那项能力是恢复还是保持缺失。",
        detail={
            "pointer": f"/plugins/{first.plugin_id}/on_disable",
            "plugins": sorted({item.plugin_id for item in items}),
            "overridden": [f"{item.plugin_id} 覆盖了 {item.target}" for item in items],
            "suggestion": f"在 plugins.{first.plugin_id} 里写 on_disable："
            f"{OnDisable.RESTORE_BUILTIN.value} 让被顶掉的实现重新生效，"
            f"{OnDisable.LEAVE_MISSING.value} 让那项能力保持缺失。",
        },
    )


def suppressed_capabilities(
    inventory: PluginInventory, config: NucleaConfig
) -> SuppressedCapabilities:
    """§10.1 步骤 3b 之后的一步：算出这次要按能力抑制哪些登记。

    对每个「已启用但被禁用」且**声明过覆盖**的插件查它的 `plugins.<id>.on_disable`：

    - 没写 → `CONFIG_INVALID`，一次把全部缺表态的插件都列出来（与 `validate_config()` 的
      「一次报全」同构）。
    - `restore_builtin` → 什么都不做，被顶掉的实现照常生效。
    - `leave_missing` → 把覆盖目标记进抑制表，那项能力随之从 `active` 里消失、并出现在
      `ResolutionReport.disabled` 段里（`nm capabilities` 因此看得见它为什么不在）。

    **异常约定**：缺表态时抛 `NucleaError(CONFIG_INVALID)`；其余情况不抛。
    """
    suppressed: dict[tuple[CapabilityKind, ProviderId, str], str] = {}
    undeclared: list[DisabledOverride] = []
    for item in _disabled_with_manifest(inventory):
        manifest = item.manifest
        if manifest is None:  # pragma: no cover - `_disabled_with_manifest` 已经筛过。
            continue
        overrides = override_targets(manifest)
        if not overrides:
            continue
        choice = config.plugins.entry(manifest.id).on_disable
        if choice is None:
            undeclared.extend(overrides)
        elif choice is OnDisable.LEAVE_MISSING:
            suppressed.update((override.key, LEAVE_MISSING_REASON) for override in overrides)
    if undeclared:
        raise _undeclared(undeclared)
    return suppressed
