"""权限账本：谁被授予了什么，以及那份决定存在哪里（技术方案 §7.5、`NFR-301`、`NFR-307`）。

职责：`Grant`（一项被声明的权限）、`PluginGrants`（一个提供方的生效授权）、
`PermissionLedger`（TOFU 判定，读写委托给 `permission_codec.py`）。
不负责：文件长什么样（`permission_codec.py`）、认识 `PermissionDecl`（那是
`sdk/manifest.py`，`R2` 禁止 kernel import 它——翻译在 `runtime/bootstrap.py`）、
构造 `PluginContext` 与实现被守卫的资源门面（都在 `runtime/`）。

**批准模型是 TOFU（trust on first use）+ 扩权需显式**：

1. 第一次见到一个提供方时，按 manifest 声明**整份**授予并记录下来（`source="first_use"`）。
2. 此后声明集合**扩大**——插件升级、换了实现、内建新增一条权限——新增项默认**拒绝**并记为
   `pending`，已有项继续生效。批准要走 `nm permissions grant` 或直接改这份文件。
3. 撤销同样是显式操作，记 `revoked`：此后即使 manifest 仍然声明也不授予。

内建与外部插件走**同一条判定**（`BAS-005`：内建不享受特权）。开箱可用不受影响——第一次
`nm run` 就把六份内建的声明记下来了；而 `NFR-307` 真正要防的「权限在用户不知情时变大」
由第 2 条兜住。**局限如实写在这里**：首次授予不是用户点头，它是一条被记录下来的默认值,
它让**扩权**可见，不让**初装**可见。要更严就把 `first_use_policy` 设成 `PENDING`。

**账本按 plugin id 索引而不是 `ProviderId`**：全部内建共用一个 `Builtin()`，按提供方索引
会让六份内建的权限并成一条——`D23` 在配置块上踩过同一个坑（`test_each_manifest_gets_its_own_context`）。

`Decision` / `LedgerEntry` / `format_permission` / `parse_permission` 从
`permission_codec` 再导出一次：调用方要的是「权限账本」这一件事，不必知道它由两个模块
拼起来（拆分的直接原因是 `kernel/` 的单文件上限 500 行）。

**这份文件不是安全边界**（§13.7）：同进程 Python 插件可以绕过全部门面直接 `import os`。
账本的价值是让越界意图可审计、让扩权在评审与 diff 里可见，不是「防恶意插件」。
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from nucleamind.contracts import JsonValue, PermissionKind

from .permission_codec import (
    LEDGER_VERSION,
    Decision,
    LedgerEntry,
    entry_order,
    format_permission,
    parse_permission,
    read_ledger,
    render_ledger,
    write_ledger,
)

__all__ = [
    "LEDGER_VERSION",
    "Decision",
    "Grant",
    "LedgerDecision",
    "LedgerEntry",
    "PermissionLedger",
    "PluginGrants",
    "format_permission",
    "parse_permission",
]

#: 由 `decide()` 自己写下的 `source`。见到它们才算「这个提供方被判定过」——用户预先批准
#: 留下的 `user` 记录不算（见 `decide()` 的 docstring）。
_SEEN_SOURCES: Final = frozenset({"first_use", "declared"})


@dataclass(frozen=True, slots=True)
class Grant:
    """一项被声明的权限。kernel 侧对 `PermissionDecl` 的投影（`R2` 够不着那个类型）。"""

    kind: PermissionKind
    target: str = ""
    #: manifest 里的用途说明。它会原样进 `permissions.json`——用户批准时读的就是这句。
    reason: str = ""

    @property
    def key(self) -> tuple[PermissionKind, str]:
        """授权记录的键。同 kind 不同 target 是两条独立授权。"""
        return (self.kind, self.target)

    @property
    def name(self) -> str:
        return format_permission(self.kind, self.target)


@dataclass(frozen=True, slots=True)
class PluginGrants:
    """一个提供方**实际生效**的授权集合 = manifest 声明 ∩ 账本批准。

    `PluginContext` 的四个访问器只问它，不问 manifest：那正是「批准叠在声明之前」的落点。
    """

    granted: frozenset[tuple[PermissionKind, str]] = frozenset()

    @property
    def kinds(self) -> frozenset[PermissionKind]:
        return frozenset(kind for kind, _ in self.granted)

    def allows(self, kind: PermissionKind) -> bool:
        """这一类权限有没有被授予（不问 target）。"""
        return any(existing is kind for existing, _ in self.granted)

    def allows_secret(self, name: str) -> bool:
        """`secret` 必须带 target（`PermissionDecl` 写死），因此「授予了 secret」这件事
        本身不足以取任何一个凭据。"""
        return (PermissionKind.SECRET, name) in self.granted

    def targets(self, kind: PermissionKind) -> tuple[str, ...]:
        """这一类权限被收窄到的目标。空元组表示未授予；含空串表示未收窄（整个根）。"""
        return tuple(sorted(target for existing, target in self.granted if existing is kind))

    def to_json(self) -> list[str]:
        return sorted(format_permission(kind, target) for kind, target in self.granted)

    @classmethod
    def of(cls, *permissions: str) -> PluginGrants:
        """从 `"fs:read"` 这样的串建一份授权。测试与 `embed/` 的便利构造。"""
        return cls(frozenset(parse_permission(text) for text in permissions))


@dataclass(frozen=True, slots=True)
class LedgerDecision:
    """一次 `decide()` 的完整结论。

    四份产出分开而不是只交回 `granted`：`pending` 要能被印出来（用户得知道该批准什么）、
    `revoked` 要能解释「为什么声明了却用不了」、`recorded` 决定要不要落盘与发事件。
    """

    plugin_id: str
    granted: PluginGrants
    pending: tuple[Grant, ...] = ()
    revoked: tuple[Grant, ...] = ()
    #: 本次新写进账本的记录（首次授予或新增待批准）。空则账本没变。
    recorded: tuple[LedgerEntry, ...] = ()


class PermissionLedger:
    """`permissions.json` 的读写与判定。

    生命周期：`load()` → 每个提供方 `decide()` → `save()`。`save()` 在没有变更时**一个
    字节都不写**——一次 `nm config show` 不该改动实例目录的 mtime。
    """

    __slots__ = ("_dirty", "_entries", "_now", "_path", "first_use_policy")

    def __init__(
        self,
        path: Path,
        *,
        entries: Mapping[str, Sequence[LedgerEntry]] | None = None,
        now: Callable[[], datetime] | None = None,
        first_use_policy: Decision = Decision.GRANTED,
    ) -> None:
        self._path = path
        self._entries: dict[str, dict[tuple[PermissionKind, str], LedgerEntry]] = {
            plugin_id: {entry.key: entry for entry in items}
            for plugin_id, items in (entries or {}).items()
        }
        self._now = now if now is not None else _utc_now
        self._dirty = False
        #: 首次见到一个提供方时的默认决定。设成 `PENDING` 即变成「什么都要先批准」，
        #: 那是更严的策略，但会让第一次 `nm run` 拿不到任何资源门面。
        self.first_use_policy = first_use_policy

    @property
    def path(self) -> Path:
        return self._path

    @property
    def dirty(self) -> bool:
        return self._dirty

    # ---------------------------------------------------------------- 读写

    @classmethod
    def load(
        cls,
        path: Path,
        *,
        now: Callable[[], datetime] | None = None,
        first_use_policy: Decision = Decision.GRANTED,
    ) -> PermissionLedger:
        """读一份账本。文件不存在即空账本（首次运行的正常情形）。

        **异常约定**：文件在但读不动、不是 JSON、版本更高、形状不对，一律抛
        `CONFIG_INVALID`——静默当成空账本会把「你的批准记录坏了」变成一次静默的**全部
        重新授予**，那正是这份文件要防的事。
        """
        entries = read_ledger(path)
        return cls(path, entries=entries, now=now, first_use_policy=first_use_policy)

    def save(self) -> bool:
        """把账本落盘（原子写在 `permission_codec.write_ledger`）。没有变更时不写。

        **异常约定**：写失败抛 `PERSISTENCE_WRITE_FAILED`。
        """
        if not self._dirty:
            return False
        write_ledger(self._path, self.to_json())
        self._dirty = False
        return True

    def to_json(self) -> dict[str, JsonValue]:
        return render_ledger(self._entries)

    # ---------------------------------------------------------------- 判定

    def entries_for(self, plugin_id: str) -> tuple[LedgerEntry, ...]:
        items = self._entries.get(plugin_id, {})
        return tuple(items[key] for key in sorted(items, key=entry_order))

    def providers(self) -> tuple[str, ...]:
        return tuple(sorted(self._entries))

    def decide(self, plugin_id: str, declared: Iterable[Grant]) -> LedgerDecision:
        """把一份 manifest 声明判成实际授权，必要时往账本里记新条目。

        **声明是上限**：账本里有、manifest 没声明的记录不参与授权（它留在文件里只作审计）。
        反过来，manifest 声明了、账本里没有的，按 `first_use_policy` 处理——首见即授予，
        否则记 `pending`。

        **「首见」看的是有没有被 `decide()` 见过，而不是有没有记录**：用户可以**预先**批准
        一个还没装上的插件的权限（`nm permissions grant`），那些记录的 `source` 是 `user`。
        把它们算成「见过」会让插件第一次真的加载时，除了预批的那条以外全部落进 `pending`
        ——用户做了一个更宽松的动作，却得到一个更严的结果。

        **异常约定**：不抛。判定失败不是一种结局：拒绝也是结论。
        """
        declarations = tuple(declared)
        known = self._entries.setdefault(plugin_id, {})
        first_sighting = not any(entry.source in _SEEN_SOURCES for entry in known.values())
        granted: set[tuple[PermissionKind, str]] = set()
        pending: list[Grant] = []
        revoked: list[Grant] = []
        recorded: list[LedgerEntry] = []

        for grant in declarations:
            entry = known.get(grant.key)
            if entry is None:
                decision = self.first_use_policy if first_sighting else Decision.PENDING
                entry = LedgerEntry(
                    kind=grant.kind,
                    target=grant.target,
                    decision=decision,
                    reason=grant.reason,
                    decided_at=self._stamp(),
                    source="first_use" if first_sighting else "declared",
                )
                known[grant.key] = entry
                recorded.append(entry)
                self._dirty = True
            elif entry.reason != grant.reason and entry.reason == "":
                # 老账本里没记用途（手写的文件），补上——但**不动决定本身**。
                entry = replace(entry, reason=grant.reason)
                known[grant.key] = entry
                self._dirty = True
            match entry.decision:
                case Decision.GRANTED:
                    granted.add(grant.key)
                case Decision.PENDING:
                    pending.append(grant)
                case Decision.REVOKED:
                    revoked.append(grant)

        return LedgerDecision(
            plugin_id=plugin_id,
            granted=PluginGrants(frozenset(granted)),
            pending=tuple(pending),
            revoked=tuple(revoked),
            recorded=tuple(recorded),
        )

    # ---------------------------------------------------------------- 显式操作

    def set_decision(
        self,
        plugin_id: str,
        permission: tuple[PermissionKind, str],
        decision: Decision,
        *,
        reason: str = "",
        source: str = "user",
    ) -> LedgerEntry:
        """显式批准 / 撤销一项权限（`nm permissions grant|revoke` 的落点）。

        对一条不存在的记录同样成立：用户可以**预先**批准一个还没装上的插件的权限。
        """
        known = self._entries.setdefault(plugin_id, {})
        previous = known.get(permission)
        entry = LedgerEntry(
            kind=permission[0],
            target=permission[1],
            decision=decision,
            reason=reason or (previous.reason if previous is not None else ""),
            decided_at=self._stamp(),
            source=source,
        )
        if previous is not None and _same_decision(previous, entry):
            return previous
        known[permission] = entry
        self._dirty = True
        return entry

    def forget(self, plugin_id: str) -> bool:
        """删掉一个提供方的全部记录。下次它会重新走一遍首见路径。"""
        if plugin_id not in self._entries:
            return False
        del self._entries[plugin_id]
        self._dirty = True
        return True

    def _stamp(self) -> str:
        return self._now().isoformat()


def _same_decision(left: LedgerEntry, right: LedgerEntry) -> bool:
    """只比对决定本身，不比时间戳——重复一次 `grant` 不该把文件改脏。"""
    return (left.decision, left.reason, left.source) == (
        right.decision,
        right.reason,
        right.source,
    )


def _utc_now() -> datetime:
    return datetime.now(UTC)
