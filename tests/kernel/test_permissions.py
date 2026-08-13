"""`kernel/plugins/permissions.py` 的用例：TOFU 判定与 `permissions.json` 的读写（`D26`）。

覆盖四组：权限名的解析与渲染、`PluginGrants` 的查询面、账本的 TOFU / 扩权 / 撤销判定、
文件的读写与坏文件的拒绝。

**判定用例全部用注入的假时钟**，因此 `decided_at` 是一个可断言的常量而不是「今天」。
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from nucleamind.contracts import ErrorCode, NucleaError, PermissionKind
from nucleamind.kernel.plugins import (
    LEDGER_VERSION,
    Decision,
    Grant,
    LedgerEntry,
    PermissionLedger,
    PluginGrants,
    format_permission,
    parse_permission,
)

FROZEN = datetime(2026, 8, 13, 12, 0, tzinfo=UTC)


def ledger(path: Path, **kwargs: object) -> PermissionLedger:
    return PermissionLedger(path, now=lambda: FROZEN, **kwargs)  # pyright: ignore[reportArgumentType]


READ = Grant(PermissionKind.FS_READ, reason="读取用户的笔记")
WRITE = Grant(PermissionKind.FS_WRITE, reason="写回整理结果")
SECRET = Grant(PermissionKind.SECRET, "api_key", reason="调用模型")


# ------------------------------------------------------------------ 权限名


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("fs:read", (PermissionKind.FS_READ, "")),
        ("fs:write", (PermissionKind.FS_WRITE, "")),
        ("net", (PermissionKind.NET, "")),
        ("shell", (PermissionKind.SHELL, "")),
        ("secret:api_key", (PermissionKind.SECRET, "api_key")),
        ("net:example.com", (PermissionKind.NET, "example.com")),
        ("fs:read:notes/", (PermissionKind.FS_READ, "notes/")),
    ],
)
def test_permission_names_round_trip(text: str, expected: tuple[PermissionKind, str]) -> None:
    """`fs:read` 自己就含冒号——从右边切最后一个冒号会把它切成 `fs` + `read`。"""
    assert parse_permission(text) == expected
    assert format_permission(*expected) == text


def test_an_unknown_permission_name_is_rejected() -> None:
    """认不出来就报，并把合法前缀一并交出——这条错误的读者正在敲命令行。"""
    with pytest.raises(NucleaError) as caught:
        parse_permission("fs")
    assert caught.value.code is ErrorCode.INPUT_MALFORMED
    assert "net" in str(caught.value.detail["known"])


# ------------------------------------------------------------------ PluginGrants


def test_grants_answer_kind_and_target_separately() -> None:
    grants = PluginGrants.of("fs:read", "fs:read:notes", "secret:api_key")
    assert grants.allows(PermissionKind.FS_READ)
    assert not grants.allows(PermissionKind.SHELL)
    assert grants.targets(PermissionKind.FS_READ) == ("", "notes")
    assert grants.targets(PermissionKind.NET) == ()


def test_granting_secret_as_a_kind_is_not_enough_for_any_name() -> None:
    """`secret` 必须带 target（`PermissionDecl` 写死），因此「授予了 secret」这件事本身
    不足以取任何一个凭据。"""
    grants = PluginGrants.of("secret:api_key")
    assert grants.allows_secret("api_key")
    assert not grants.allows_secret("other_key")


# ------------------------------------------------------------------ TOFU


def test_first_sighting_grants_the_whole_declaration(tmp_path: Path) -> None:
    book = ledger(tmp_path / "permissions.json")
    decision = book.decide("notes", [READ, WRITE])

    assert decision.granted.to_json() == ["fs:read", "fs:write"]
    assert decision.pending == ()
    assert {entry.source for entry in decision.recorded} == {"first_use"}
    assert [entry.decided_at for entry in decision.recorded] == [FROZEN.isoformat()] * 2
    assert book.dirty


def test_deciding_twice_records_nothing_new(tmp_path: Path) -> None:
    """幂等：第二次启动不该把文件改脏，否则每次 `nm run` 都在动实例目录。"""
    book = ledger(tmp_path / "permissions.json")
    book.decide("notes", [READ])
    book.save()

    again = book.decide("notes", [READ])
    assert again.granted.to_json() == ["fs:read"]
    assert again.recorded == ()
    assert not book.dirty


def test_an_expanded_declaration_is_pending_not_granted(tmp_path: Path) -> None:
    """升级后新增的那条默认拒绝——这就是 `NFR-307`「扩权必须是显式操作」的落点。"""
    book = ledger(tmp_path / "permissions.json")
    book.decide("notes", [READ])

    decision = book.decide("notes", [READ, Grant(PermissionKind.SHELL, reason="跑构建")])
    assert decision.granted.to_json() == ["fs:read"]
    assert [grant.name for grant in decision.pending] == ["shell"]
    assert [entry.source for entry in decision.recorded] == ["declared"]


def test_an_explicit_grant_turns_a_pending_entry_on(tmp_path: Path) -> None:
    book = ledger(tmp_path / "permissions.json")
    book.decide("notes", [READ])
    book.decide("notes", [READ, Grant(PermissionKind.SHELL, reason="跑构建")])

    book.set_decision("notes", (PermissionKind.SHELL, ""), Decision.GRANTED)
    decision = book.decide("notes", [READ, Grant(PermissionKind.SHELL, reason="跑构建")])
    assert decision.granted.to_json() == ["fs:read", "shell"]
    assert decision.pending == ()


def test_a_revoked_permission_stays_off_even_though_it_is_declared(tmp_path: Path) -> None:
    book = ledger(tmp_path / "permissions.json")
    book.decide("notes", [READ, WRITE])
    book.set_decision("notes", (PermissionKind.FS_WRITE, ""), Decision.REVOKED)

    decision = book.decide("notes", [READ, WRITE])
    assert decision.granted.to_json() == ["fs:read"]
    assert [grant.name for grant in decision.revoked] == ["fs:write"]


def test_the_declaration_is_the_upper_bound(tmp_path: Path) -> None:
    """账本里有、manifest 没声明的记录不参与授权：它留在文件里只作审计。"""
    book = ledger(tmp_path / "permissions.json")
    book.set_decision("notes", (PermissionKind.SHELL, ""), Decision.GRANTED)

    decision = book.decide("notes", [READ])
    assert decision.granted.to_json() == ["fs:read"]
    assert {entry.name for entry in book.entries_for("notes")} == {"shell", "fs:read"}


def test_pre_approval_does_not_count_as_having_been_seen(tmp_path: Path) -> None:
    """预先批准是一个**更宽松**的动作，不该换来一个更严的结果。

    用户预批了 `shell`，插件第一次真的加载时其余声明仍走首见路径——把 `user` 记录算成
    「见过」会让它们全部落进 `pending`。
    """
    book = ledger(tmp_path / "permissions.json")
    book.set_decision("notes", (PermissionKind.SHELL, ""), Decision.GRANTED)

    decision = book.decide("notes", [READ, Grant(PermissionKind.SHELL, reason="跑构建")])
    assert decision.granted.to_json() == ["fs:read", "shell"]
    assert decision.pending == ()


def test_repeating_the_same_explicit_decision_does_not_dirty_the_book(tmp_path: Path) -> None:
    book = ledger(tmp_path / "permissions.json")
    book.set_decision("notes", (PermissionKind.SHELL, ""), Decision.GRANTED)
    book.save()

    book.set_decision("notes", (PermissionKind.SHELL, ""), Decision.GRANTED)
    assert not book.dirty


def test_forgetting_a_provider_restores_first_sighting(tmp_path: Path) -> None:
    book = ledger(tmp_path / "permissions.json")
    book.decide("notes", [READ])
    book.set_decision("notes", (PermissionKind.FS_READ, ""), Decision.REVOKED)

    assert book.forget("notes")
    assert not book.forget("notes")
    assert book.decide("notes", [READ]).granted.to_json() == ["fs:read"]


def test_a_stricter_first_use_policy_denies_everything(tmp_path: Path) -> None:
    """`first_use_policy=PENDING` 是「什么都要先批准」，它必须真的可用。"""
    book = ledger(tmp_path / "permissions.json", first_use_policy=Decision.PENDING)
    decision = book.decide("notes", [READ, SECRET])
    assert decision.granted.granted == frozenset()
    assert len(decision.pending) == 2


# ------------------------------------------------------------------ 文件


def test_the_ledger_round_trips_through_the_file(tmp_path: Path) -> None:
    path = tmp_path / "permissions.json"
    book = ledger(path)
    book.decide("notes", [READ, SECRET])
    assert book.save()

    reloaded = PermissionLedger.load(path)
    entries = reloaded.entries_for("notes")
    assert [entry.name for entry in entries] == ["fs:read", "secret:api_key"]
    assert entries[0].reason == "读取用户的笔记"
    assert entries[0].decision is Decision.GRANTED
    assert reloaded.decide("notes", [READ, SECRET]).recorded == ()


def test_saving_an_unchanged_ledger_writes_nothing(tmp_path: Path) -> None:
    path = tmp_path / "permissions.json"
    book = ledger(path)
    book.decide("notes", [READ])
    assert book.save()
    assert not book.save()
    assert not path.with_name(f"{path.name}.tmp").exists()


def test_a_missing_file_is_an_empty_ledger(tmp_path: Path) -> None:
    """首次运行的正常情形——不是错误。"""
    book = PermissionLedger.load(tmp_path / "nope.json")
    assert book.providers() == ()
    assert not book.dirty


def test_the_written_document_is_plain_json(tmp_path: Path) -> None:
    path = tmp_path / "permissions.json"
    book = ledger(path)
    book.decide("notes", [SECRET])
    book.save()

    document = json.loads(path.read_text(encoding="utf-8"))
    assert document == {
        "version": LEDGER_VERSION,
        "providers": {
            "notes": {
                "grants": [
                    {
                        "permission": "secret:api_key",
                        "decision": "granted",
                        "reason": "调用模型",
                        "decided_at": FROZEN.isoformat(),
                        "source": "first_use",
                    }
                ]
            }
        },
    }
    # 记的是**引用的名字**而不是凭据本身：账本里从来没有值可泄漏。
    assert "sk-" not in path.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "payload",
    [
        "not json at all",
        '["a list"]',
        '{"version": 99, "providers": {}}',
        '{"version": 1}',
        '{"version": 1, "providers": {"x": []}}',
        '{"version": 1, "providers": {"x": {"grants": {}}}}',
        '{"version": 1, "providers": {"x": {"grants": [1]}}}',
        '{"version": 1, "providers": {"x": {"grants": [{"decision": "granted"}]}}}',
        '{"version": 1, "providers": {"x": {"grants": [{"permission": "fs", "decision": "granted"}]}}}',
        '{"version": 1, "providers": {"x": {"grants": [{"permission": "net", "decision": "maybe"}]}}}',
    ],
)
def test_a_broken_ledger_is_a_startup_failure(tmp_path: Path, payload: str) -> None:
    """**不静默当成空账本**：那等于一次静默的全部重新授予，正是这份文件要防的事。"""
    path = tmp_path / "permissions.json"
    path.write_text(payload, encoding="utf-8")
    with pytest.raises(NucleaError) as caught:
        PermissionLedger.load(path)
    assert caught.value.code is ErrorCode.CONFIG_INVALID
    assert caught.value.detail["file"] == str(path)


def test_a_hand_written_entry_gets_its_reason_backfilled(tmp_path: Path) -> None:
    """手写的文件可以省掉 `reason`，下次启动从 manifest 补上——但**决定本身不动**。"""
    book = ledger(
        tmp_path / "permissions.json",
        entries={
            "notes": [
                LedgerEntry(
                    kind=PermissionKind.FS_READ,
                    target="",
                    decision=Decision.REVOKED,
                    reason="",
                    decided_at="",
                    source="user",
                )
            ]
        },
    )
    decision = book.decide("notes", [READ])
    assert decision.granted.granted == frozenset()
    assert book.entries_for("notes")[0].reason == "读取用户的笔记"
