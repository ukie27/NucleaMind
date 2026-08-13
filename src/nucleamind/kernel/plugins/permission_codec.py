"""权限账本的**文件形态**：`permissions.json` 的词汇、解析与落盘（`D26`）。

职责：`Decision` / `LedgerEntry` 两个记录类型、权限名的解析与渲染、读一份账本文件、
把一份账本原子写回去。
不负责：判定谁被授予什么（`permissions.py` 的 `PermissionLedger.decide()`）、
认识 manifest（`R2`；翻译在 `runtime/bootstrap.py`）。

**分界线是「认不认识判定」**：本模块知道文件长什么样、认得权限名的写法，但一条记录该是
`granted` 还是 `pending` 它一个字都不管。与 `kernel/config/` 里 `fields.py`（校验积木，
一个字段名都不认识）和 `schema.py`（字段表）的那条分界线是同一种。拆开的直接原因是
`kernel/` 的单文件上限 500 行，理由与 `D10`/`D12`/`D16` 的几次拆分相同。

**读不懂一律抛 `CONFIG_INVALID`**：静默当成空账本会把「你的批准记录坏了」变成一次静默的
**全部重新授予**——那正是这份文件要防的事。
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Final, cast

from nucleamind.contracts import ErrorCode, JsonValue, NucleaError, PermissionKind

__all__ = [
    "LEDGER_VERSION",
    "Decision",
    "LedgerEntry",
    "entry_order",
    "format_permission",
    "parse_permission",
    "read_ledger",
    "render_ledger",
    "write_ledger",
]

#: 文件格式版本。读到别的版本**拒绝而不是尽力解析**——一份读错的权限文件会静默扩权。
LEDGER_VERSION: Final = 1

_KINDS_BY_LENGTH: Final[tuple[PermissionKind, ...]] = tuple(
    sorted(PermissionKind, key=lambda kind: len(kind.value), reverse=True)
)


class Decision(StrEnum):
    """一条记录的状态。

    `PENDING` 不是「还没问」的占位符，它是一个**已经生效的拒绝**：声明扩大之后新增的那项
    在用户批准之前不授予。把它塌进 `REVOKED` 会让「用户明确说不」与「还没来得及说」
    在 `nm permissions list` 里不可区分，而两者的下一步动作完全不同。
    """

    GRANTED = "granted"
    PENDING = "pending"
    REVOKED = "revoked"


def format_permission(kind: PermissionKind, target: str = "") -> str:
    """渲染成 `fs:read` / `secret:api_key` 这样的一个串（配置、CLI 与文件里的形态）。"""
    return f"{kind.value}:{target}" if target else kind.value


def parse_permission(text: str) -> tuple[PermissionKind, str]:
    """`format_permission()` 的逆运算。

    **按最长 kind 前缀匹配**：`fs:read` 自己就含冒号，从右边切最后一个冒号会把它切成
    `fs` + `read`，而 `fs` 不是任何一种权限。

    **异常约定**：认不出来抛 `INPUT_MALFORMED`，`detail` 里给出全部合法前缀——这条错误
    的读者是正在敲 `nm permissions grant` 的人。
    """
    raw = text.strip()
    for kind in _KINDS_BY_LENGTH:
        if raw == kind.value:
            return (kind, "")
        prefix = kind.value + ":"
        if raw.startswith(prefix):
            return (kind, raw[len(prefix) :])
    raise NucleaError(
        ErrorCode.INPUT_MALFORMED,
        "认不出这个权限名。",
        detail={"permission": raw, "known": [kind.value for kind in PermissionKind]},
    )


@dataclass(frozen=True, slots=True)
class LedgerEntry:
    """账本里的一条记录。"""

    kind: PermissionKind
    target: str
    decision: Decision
    reason: str
    decided_at: str
    #: `first_use`（TOFU 默认）/ `declared`（声明扩大后自动记的待批准）/ `user`（显式操作）。
    source: str

    @property
    def key(self) -> tuple[PermissionKind, str]:
        return (self.kind, self.target)

    @property
    def name(self) -> str:
        return format_permission(self.kind, self.target)

    def to_json(self) -> dict[str, JsonValue]:
        return {
            "permission": self.name,
            "decision": self.decision.value,
            "reason": self.reason,
            "decided_at": self.decided_at,
            "source": self.source,
        }


def entry_order(key: tuple[PermissionKind, str]) -> tuple[str, str]:
    """记录的排序键。文件里的顺序稳定，diff 才读得出「这次多了哪一条」。"""
    return (key[0].value, key[1])


def render_ledger(entries: Mapping[str, Mapping[tuple[PermissionKind, str], LedgerEntry]]) -> dict[str, JsonValue]:
    """把账本渲染成 JSON 文档。"""
    providers: dict[str, JsonValue] = {}
    for plugin_id in sorted(entries):
        items = entries[plugin_id]
        providers[plugin_id] = {
            "grants": [items[key].to_json() for key in sorted(items, key=entry_order)]
        }
    return {"version": LEDGER_VERSION, "providers": providers}


def read_ledger(path: Path) -> dict[str, list[LedgerEntry]] | None:
    """读一份账本文件。文件不存在返回 `None`（首次运行的正常情形，不是错误）。

    **异常约定**：文件在但读不动、不是 JSON、版本对不上、形状不对，一律抛 `CONFIG_INVALID`。
    """
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise _invalid(path, "权限文件读不动。", os_error=type(exc).__name__) from exc
    document = _parse_document(raw, path)
    providers = document.get("providers")
    if not isinstance(providers, dict):
        raise _invalid(path, "权限文件缺少 providers 小节。")
    return {
        plugin_id: _parse_entries(plugin_id, block, path)
        for plugin_id, block in providers.items()
    }


def write_ledger(path: Path, document: Mapping[str, JsonValue]) -> None:
    """原子写：同目录临时文件 → `fsync` → `os.replace`。

    **异常约定**：写失败抛 `PERSISTENCE_WRITE_FAILED`。不留半份文件——替换成功之后没有
    可失败的步骤，失败一律发生在替换之前（`D20` 的同一条判据）。
    """
    payload = json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    temp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(temp, "wb") as handle:  # noqa: PTH123
            handle.write(payload.encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    except OSError as exc:
        temp.unlink(missing_ok=True)
        raise NucleaError(
            ErrorCode.PERSISTENCE_WRITE_FAILED,
            "权限文件写入失败。",
            detail={"file": str(path), "os_error": type(exc).__name__},
        ) from exc


def _invalid(path: Path, message: str, **detail: JsonValue) -> NucleaError:
    """错误码在函数名里、消息在第二位——与 `sdk/manifest.py::_fail` 同形。

    一份读不懂的权限文件永远是 `CONFIG_INVALID`：它和 `config.json` 一样是用户的资产，
    补救动作也一样（去改那个文件）。
    """
    payload: dict[str, JsonValue] = {"file": str(path)}
    payload.update(detail)
    return NucleaError(ErrorCode.CONFIG_INVALID, message, detail=payload)


def _parse_document(raw: bytes, path: Path) -> Mapping[str, JsonValue]:
    try:
        loaded: object = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _invalid(path, "权限文件不是合法 JSON。") from exc
    if not isinstance(loaded, dict):
        raise _invalid(path, "权限文件的顶层必须是一个对象。")
    # `dict[Unknown, Unknown]` 到 `Mapping[str, JsonValue]` 的收窄：`json.loads` 的产物
    # 按定义就是 `JsonValue`，且 JSON 的键只可能是字符串。上面那句 `isinstance` 就是
    # `AGENTS.md` 原则 6 要求的运行时检查；逐层再验一遍只会把同一件事写两遍。
    document = cast("Mapping[str, JsonValue]", loaded)
    version = document.get("version")
    if version != LEDGER_VERSION:
        raise _invalid(
            path,
            "权限文件的版本读不了。",
            found=version if isinstance(version, int | str) else None,
            expected=LEDGER_VERSION,
        )
    return document


def _parse_entries(plugin_id: str, block: JsonValue, path: Path) -> list[LedgerEntry]:
    if not isinstance(block, dict):
        raise _invalid(path, "权限文件里的提供方记录必须是一个对象。", plugin=plugin_id)
    grants = block.get("grants")
    if not isinstance(grants, list):
        raise _invalid(path, "提供方记录缺少 grants 列表。", plugin=plugin_id)
    return [_parse_entry(plugin_id, item, path) for item in grants]


def _parse_entry(plugin_id: str, item: JsonValue, path: Path) -> LedgerEntry:
    if not isinstance(item, dict):
        raise _invalid(path, "权限记录必须是一个对象。", plugin=plugin_id)
    name = item.get("permission")
    decision = item.get("decision")
    if not isinstance(name, str) or not isinstance(decision, str):
        raise _invalid(
            path,
            "权限记录必须有 permission 与 decision 两个字符串字段。",
            plugin=plugin_id,
        )
    try:
        kind, target = parse_permission(name)
    except NucleaError as exc:
        raise _invalid(
            path, "权限记录里有认不出的权限名。", plugin=plugin_id, permission=name
        ) from exc
    if decision not in {member.value for member in Decision}:
        raise _invalid(
            path,
            "权限记录里有认不出的决定。",
            plugin=plugin_id,
            permission=name,
            decision=decision,
        )
    return LedgerEntry(
        kind=kind,
        target=target,
        decision=Decision(decision),
        reason=_text(item.get("reason")),
        decided_at=_text(item.get("decided_at")),
        source=_text(item.get("source")) or "user",
    )


def _text(value: JsonValue) -> str:
    return value if isinstance(value, str) else ""
