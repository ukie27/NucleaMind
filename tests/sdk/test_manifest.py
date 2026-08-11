"""manifest 的校验矩阵（技术方案 §7.2、`SDK-005`、`CMP-001`、`PLG-001`）。

两条被反复验证的性质：**每一条校验失败都给出字段路径**，以及**失败一律是
`NucleaError`**——缺兼容字段直接判定失败并指出位置，不做兜底猜测。
"""

from __future__ import annotations

from typing import Final

import pytest
from pydantic import ValidationError

from nucleamind.contracts import Builtin, CapabilityKind, ErrorCode, NucleaError, PermissionKind
from nucleamind.sdk import CapabilityDecl, PermissionDecl, PluginManifest, parse_manifest
from nucleamind.sdk.version import SDK_VERSION

#: 一份最小可用 manifest。各用例在它上面打补丁，只改一处，失败原因因此无歧义。
VALID: Final[dict[str, object]] = {
    "id": "memory-sqlite",
    "version": "0.1.0",
    "sdk_range": ">=0.1,<0.2",
    "setup": "nucleamind_plugin_memory_sqlite.plugin:setup",
    "capabilities": [{"kind": "memory", "name": "sqlite"}],
}


def parse(**patch: object) -> PluginManifest:
    return parse_manifest({**VALID, **patch}, origin="test")


# ------------------------------------------------------------------------------ 正例


def test_minimal_manifest_parses() -> None:
    manifest = parse()
    assert manifest.id == "memory-sqlite"
    assert manifest.capabilities[0].kind is CapabilityKind.MEMORY
    # 未声明的字段取默认值，而不是 None——加载器不必到处判空。
    assert manifest.dependencies == ()
    assert manifest.state_version == 1
    assert manifest.critical is False


def test_manifest_is_frozen() -> None:
    """manifest 是数据：解析之后没有人可以改它，包括加载器自己。"""
    manifest = parse()
    with pytest.raises(ValidationError):
        manifest.id = "other"  # type: ignore[misc]


def test_override_target_decodes_via_the_shared_parser() -> None:
    """覆盖目标只有一套编解码（`CapabilityRef.target` / `parse_capability_target`）。"""
    manifest = parse(
        capabilities=[{"kind": "tool", "name": "fs.read", "overrides": "builtin:fs.read"}]
    )
    assert manifest.capabilities[0].override_target == (Builtin(), "fs.read")


def test_no_override_means_none() -> None:
    assert parse().capabilities[0].override_target is None


def test_sdk_compatibility_is_evaluated_against_the_current_version() -> None:
    assert parse().sdk_compatible is True
    assert parse(sdk_range=">=99.0").sdk_compatible is False, f"当前 SDK 是 {SDK_VERSION}"


def test_platforms_empty_means_every_platform() -> None:
    assert parse().matches_platform("win32") is True
    assert parse().matches_platform("linux") is True


def test_platforms_are_matched_exactly() -> None:
    manifest = parse(platforms=["linux"])
    assert manifest.matches_platform("linux") is True
    assert manifest.matches_platform("win32") is False


def test_permission_grant_key_separates_targets() -> None:
    first = PermissionDecl(kind=PermissionKind.SECRET, reason="调用 API", target="openai_api_key")
    second = PermissionDecl(kind=PermissionKind.SECRET, reason="调用 API", target="other_key")
    assert first.grant_key != second.grant_key


def test_capability_decl_slot_is_kind_plus_name() -> None:
    decl = CapabilityDecl(kind=CapabilityKind.TOOL, name="fs.read")
    assert decl.slot == (CapabilityKind.TOOL, "fs.read")
    assert decl.priority == 100


# ------------------------------------------------------------------------------ 反例

#: (补丁, 期望出现在诊断里的字段路径)。每条一个失败点。
INVALID_CASES: Final[list[tuple[dict[str, object], str]]] = [
    ({"id": "Memory_SQLite"}, "id"),
    ({"id": "-leading"}, "id"),
    ({"version": "not-a-version!"}, "version"),
    ({"sdk_range": ">>=1"}, "sdk_range"),
    ({"setup": "no-colon"}, "setup"),
    ({"setup": "pkg.module:not an identifier"}, "setup"),
    ({"capabilities": []}, "capabilities"),
    ({"capabilities": [{"kind": "tool", "name": "NOT LOWER"}]}, "capabilities.name"),
    ({"capabilities": [{"kind": "tool", "name": "fs.read", "overrides": "??"}]}, "overrides"),
    ({"capabilities": [{"kind": "tool", "name": "fs.read", "priority": -1}]}, "priority"),
    (
        {"capabilities": [{"kind": "tool", "name": "a.b"}, {"kind": "tool", "name": "a.b"}]},
        "capabilities",
    ),
    ({"dependencies": ["memory-sqlite"]}, "dependencies"),
    ({"dependencies": ["a", "a"]}, "value"),
    ({"state_version": 0}, "state_version"),
    ({"permissions": [{"kind": "secret", "reason": "要用"}]}, "target"),
    ({"permissions": [{"kind": "net", "reason": "   "}]}, "reason"),
]


@pytest.mark.parametrize(
    ("patch", "field"), INVALID_CASES, ids=[str(list(p)[0]) + ":" + f for p, f in INVALID_CASES]
)
def test_invalid_manifest_reports_the_offending_field(patch: dict[str, object], field: str) -> None:
    with pytest.raises(NucleaError) as excinfo:
        parse(**patch)
    error = excinfo.value
    assert error.code is ErrorCode.PLUGIN_MANIFEST_UNSUPPORTED
    assert field in str(error.detail), f"诊断里没有字段路径 {field}：{dict(error.detail)}"


#: 结构错误由 pydantic 发现，`parse_manifest()` 把它们连同**字段路径**一起转成
#: `NucleaError`——`errors` 是 `[{"field": ..., "message": ...}]`。
STRUCTURAL_CASES: Final[list[tuple[dict[str, object], str]]] = [
    ({"unknown_field": 1}, "unknown_field"),
    ({"capabilities": [{"kind": "not-a-kind", "name": "a.b"}]}, "capabilities.0.kind"),
    ({"capabilities": [{"name": "a.b"}]}, "capabilities.0.kind"),
    ({"state_version": "one"}, "state_version"),
]


@pytest.mark.parametrize(("patch", "path"), STRUCTURAL_CASES, ids=[p for _, p in STRUCTURAL_CASES])
def test_structural_errors_carry_a_field_path(patch: dict[str, object], path: str) -> None:
    with pytest.raises(NucleaError) as excinfo:
        parse(**patch)
    detail = dict(excinfo.value.detail)
    assert detail["origin"] == "test"
    errors = detail["errors"]
    assert isinstance(errors, (list, tuple))
    fields = [dict(entry)["field"] for entry in errors]  # type: ignore[arg-type]
    assert path in fields, f"字段路径不含 {path}：{fields}"


def test_missing_required_field_is_rejected_without_guessing() -> None:
    """`CMP-001`：缺少 `sdk_range` 这类兼容字段直接判定失败，不做兜底。"""
    data = {key: value for key, value in VALID.items() if key != "sdk_range"}
    with pytest.raises(NucleaError) as excinfo:
        parse_manifest(data, origin="test")
    assert "sdk_range" in str(excinfo.value.detail)


def test_direct_construction_still_validates_semantics() -> None:
    """插件作者在自己的模块里直接构造时，语义校验同样生效（不只是 `parse_manifest`）。"""
    with pytest.raises(NucleaError):
        PluginManifest(
            id="Bad_Id",
            version="1.0",
            sdk_range=">=0.1",
            setup="a.b:c",
            capabilities=(CapabilityDecl(kind=CapabilityKind.TOOL, name="a.b"),),
        )
