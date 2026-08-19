"""`D26` 在装配根上的接线：账本、事件与受限运行时拿到的授权。

职责：验「批准叠在声明之前」这条路真的走通了——第一次启动写 `permissions.json`、
第二次不重写、扩权落 `pending` 且 `ctx` 真的拿不到门面、只读路径不落盘。
不负责：验账本本身的判定（`tests/kernel/test_permissions.py`）、验三个门面的行为
（`tests/runtime/test_access.py`）。

**Fake 只换模型这一项**，与 `test_bootstrap.py` 同一条分界线：这套用例真的装了六份内建
manifest，因此它验的是「内建与插件走同一条判定」（`BAS-005`）而不是一个构造出来的样例。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nucleamind.contracts import ErrorCode, EventName, InstanceId, NucleaError, PermissionKind
from nucleamind.kernel.observability import EventBus
from nucleamind.kernel.plugins import Decision, PermissionLedger
from nucleamind.runtime.access import GuardedFileAccess
from nucleamind.runtime.bootstrap import bootstrap, declared_grants
from nucleamind.runtime.inspect import open_session_store
from nucleamind.runtime.instance import AgentInstance
from nucleamind.runtime.plugin_context import PluginRuntime, build_plugin_context
from nucleamind.sdk import PermissionDecl, PluginManifest

from ._support import SCRIPT, TEST_MANIFESTS, text_response, write_config


@pytest.fixture(autouse=True)
def _script() -> None:
    SCRIPT[:] = [text_response("好的。")]


async def _boot(root: Path, manifests: tuple[PluginManifest, ...] = TEST_MANIFESTS) -> AgentInstance:
    return await bootstrap(instance_dir=root, manifests=manifests)


def _read(root: Path) -> dict[str, object]:
    document = json.loads((root / "permissions.json").read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    return document


async def test_the_first_boot_records_every_declaration(tmp_path: Path) -> None:
    """TOFU：第一次启动把六份内建的声明整份记下来，开箱可用因此不受影响。"""
    write_config(tmp_path)
    instance = await _boot(tmp_path)
    await instance.stop()

    providers = _read(tmp_path)["providers"]
    assert isinstance(providers, dict)
    # 声明了权限的内建都在（`context-basic` / `commands-core` 一条也不声明，因此不在）。
    assert {"session-jsonl", "tools-fs", "tools-shell"} <= set(providers)
    # 用 `tools-fs` 而不是 `model-openai`：本套用例把模型换成了 Fake，而那份 manifest
    # 一条权限也不声明——拿它断言等于什么都没断言。
    grants = providers["tools-fs"]["grants"]  # type: ignore[index]
    assert {row["permission"] for row in grants} == {"fs:read", "fs:write"}
    assert {row["decision"] for row in grants} == {"granted"}
    assert {row["source"] for row in grants} == {"first_use"}
    # 记的是引用的名字，不是值——账本里从来没有凭据可泄漏。
    assert "sk-" not in (tmp_path / "permissions.json").read_text(encoding="utf-8")


async def test_the_first_boot_publishes_a_permission_event(tmp_path: Path) -> None:
    write_config(tmp_path)
    instance = await _boot(tmp_path)
    try:
        events = [
            event
            for event in instance.diagnostics.events.events()
            if event.name is EventName.CAPABILITY_PERMISSION_GRANTED
        ]
        assert events, "首次授予必须可审计（`NFR-301`）"
        assert {"plugin", "permission", "decision", "source", "reason"} <= set(
            events[0].payload
        )
    finally:
        await instance.stop()


async def test_a_second_boot_neither_rewrites_nor_re_announces(tmp_path: Path) -> None:
    """一条每次启动都出现的「已授予」只会让真正的扩权淹在噪声里（`D24` 的同一条判据）。"""
    write_config(tmp_path)
    first = await _boot(tmp_path)
    await first.stop()
    stamp = (tmp_path / "permissions.json").stat().st_mtime_ns
    before = _read(tmp_path)

    second = await _boot(tmp_path)
    try:
        assert _read(tmp_path) == before
        assert (tmp_path / "permissions.json").stat().st_mtime_ns == stamp
        assert not [
            event
            for event in second.diagnostics.events.events()
            if event.name is EventName.CAPABILITY_PERMISSION_GRANTED
        ]
    finally:
        await second.stop()


async def test_an_expanded_declaration_lands_in_pending_and_the_facade_stays_shut(
    tmp_path: Path,
) -> None:
    """`NFR-307` 的可执行形态：插件升级新增的那条权限，在批准之前 `ctx` 真的拿不到。"""
    write_config(tmp_path)
    instance = await _boot(tmp_path)
    await instance.stop()

    upgraded = tuple(
        manifest.model_copy(
            update={
                "permissions": (
                    *manifest.permissions,
                    PermissionDecl(kind=PermissionKind.SHELL, reason="新版本要跑构建"),
                )
            }
        )
        if manifest.id == "tools-fs"
        else manifest
        for manifest in TEST_MANIFESTS
    )
    upgraded_instance = await _boot(tmp_path, upgraded)
    try:
        ledger = PermissionLedger.load(tmp_path / "permissions.json")
        entry = next(e for e in ledger.entries_for("tools-fs") if e.name == "shell")
        assert (entry.decision, entry.source) == (Decision.PENDING, "declared")
        # 已有的那几条不受影响——扩权只挡新增项。
        assert any(e.decision is Decision.GRANTED for e in ledger.entries_for("tools-fs"))

        # 「待批准」必须真的关着门面，而不只是文件里的一行字。
        upgraded_manifest = next(m for m in upgraded if m.id == "tools-fs")
        granted = ledger.decide("tools-fs", declared_grants(upgraded_manifest)).granted
        ctx = build_plugin_context(
            "tools-fs",
            config={},
            secrets={},
            state_dir=tmp_path / "plugins" / "tools-fs",
            grants=granted,
            bus=EventBus(InstanceId("test")),
            runtime=PluginRuntime(),
            workspace=tmp_path / "workspace",
        )
        with pytest.raises(NucleaError) as caught:
            _ = ctx.shell
        assert caught.value.code is ErrorCode.PERMISSION_DENIED
        assert isinstance(ctx.fs, GuardedFileAccess)
    finally:
        await upgraded_instance.stop()


async def test_an_explicit_grant_takes_effect_on_the_next_boot(tmp_path: Path) -> None:
    """`nm permissions grant` 与账本文件是同一条路：批准之后下次启动就生效。"""
    write_config(tmp_path)
    first = await _boot(tmp_path)
    await first.stop()

    ledger = PermissionLedger.load(tmp_path / "permissions.json")
    ledger.set_decision("tools-fs", (PermissionKind.FS_WRITE, ""), Decision.REVOKED)
    ledger.save()

    second = await _boot(tmp_path)
    try:
        reloaded = PermissionLedger.load(tmp_path / "permissions.json")
        entry = next(e for e in reloaded.entries_for("tools-fs") if e.name == "fs:write")
        # 撤销压过声明：manifest 仍然声明它，但账本说不。
        assert entry.decision is Decision.REVOKED
    finally:
        await second.stop()


async def test_a_broken_ledger_fails_the_start(tmp_path: Path) -> None:
    """静默当成空账本等于一次静默的全部重新授予。"""
    write_config(tmp_path)
    (tmp_path / "permissions.json").write_text("{oops", encoding="utf-8")
    with pytest.raises(NucleaError) as caught:
        await _boot(tmp_path)
    assert caught.value.code is ErrorCode.CONFIG_INVALID


async def test_a_read_only_path_never_writes_the_ledger(tmp_path: Path) -> None:
    """`nm session` 不取实例锁，让它改写 `permissions.json` 会与在跑的实例抢同一个文件。"""
    write_config(tmp_path)
    async with open_session_store(instance_dir=tmp_path, manifests=TEST_MANIFESTS) as (
        _loaded,
        store,
    ):
        await store.list_keys()
    assert not (tmp_path / "permissions.json").exists()
