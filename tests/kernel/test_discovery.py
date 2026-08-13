"""插件发现的测试（`D25`；技术方案 §7.1，需求 `DST-002`、`NFR-401`）。

四条主线：

- **候选 id 先于 manifest 可知**。三条来源的 id 分别来自 entry point 名、目录名与文件名，
  这是「未启用即零导入开销」成立的地基，因此每条来源各有一个用例。
- **发现阶段不导入任何东西**。`discover()` 跑完之后 `sys.modules` 里不得多出插件模块，
  且有一条自证用例：真的去 `read_candidate()` 时那个模块**必须**出现，否则前一条断言
  在任何实现下都会通过。
- **跨来源重复 id 时各方都不生效**，与 `kernel/registry` 的冲突语义一致。
- **搜索路径写错是失败而不是静默跳过**：那是用户显式写下的一条配置。

本模块不认识 manifest 类型（`R2`），因此断言的是「交回来的原始数据长什么样」。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from nucleamind.contracts import ErrorCode, NucleaError
from nucleamind.kernel.plugins import (
    ENTRY_POINT_GROUP,
    MANIFEST_FILENAME,
    PluginCandidate,
    SourceKind,
    discover,
    installed_entry_points,
    read_candidate,
)

_TOML = """
id = "acme"
version = "1.0.0"
sdk_range = ">=0.1"
setup = "acme.plugin:setup"

[[capabilities]]
kind = "tool"
name = "acme.ping"
"""

_MODULE = """
MANIFEST = {"id": "solo", "version": "1.0.0"}
"""


def _directory_plugin(root: Path, plugin_id: str, body: str = _TOML) -> Path:
    package = root / plugin_id
    package.mkdir(parents=True)
    (package / MANIFEST_FILENAME).write_text(body, encoding="utf-8")
    return package


def _file_plugin(root: Path, plugin_id: str, body: str = _MODULE) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{plugin_id}.py"
    path.write_text(body, encoding="utf-8")
    return path


def _no_entry_points() -> tuple[tuple[str, str], ...]:
    return ()


# --------------------------------------------------------------------------- 来源


def test_a_directory_with_a_plugin_toml_is_a_candidate(tmp_path: Path) -> None:
    _directory_plugin(tmp_path, "acme")
    found = discover(search_paths=[tmp_path], entry_points=_no_entry_points)
    assert [(c.plugin_id, c.kind) for c in found.candidates] == [("acme", SourceKind.DIRECTORY)]
    assert not found.failures


def test_a_bare_python_file_is_a_candidate(tmp_path: Path) -> None:
    _file_plugin(tmp_path, "solo")
    found = discover(search_paths=[tmp_path], entry_points=_no_entry_points)
    assert [(c.plugin_id, c.kind) for c in found.candidates] == [("solo", SourceKind.MODULE_FILE)]


def test_an_entry_point_is_a_candidate_without_loading_it() -> None:
    """`(name, value)` 都是元数据字符串，读它们不导入任何插件模块。"""
    found = discover(entry_points=lambda: (("acme", "acme.plugin:MANIFEST"),))
    (candidate,) = found.candidates
    assert candidate.plugin_id == "acme"
    assert candidate.kind is SourceKind.ENTRY_POINT
    assert candidate.location == "acme.plugin:MANIFEST"
    assert ENTRY_POINT_GROUP in candidate.origin


def test_a_directory_without_a_manifest_is_not_a_candidate(tmp_path: Path) -> None:
    """插件的**状态**目录长这样（`<instance>/plugins/<id>/`），它不是代码来源。"""
    (tmp_path / "acme").mkdir()
    (tmp_path / "acme" / "state.json").write_text("{}", encoding="utf-8")
    assert discover(search_paths=[tmp_path], entry_points=_no_entry_points).candidates == ()


def test_dot_and_underscore_prefixed_entries_are_skipped(tmp_path: Path) -> None:
    _directory_plugin(tmp_path, ".hidden")
    _file_plugin(tmp_path, "__init__")
    assert discover(search_paths=[tmp_path], entry_points=_no_entry_points).candidates == ()


def test_scanning_does_not_recurse(tmp_path: Path) -> None:
    """插件不藏在孙目录里——递归会把一个装了 vendor 目录的插件数成好几个。"""
    _directory_plugin(tmp_path / "nested", "acme")
    assert discover(search_paths=[tmp_path], entry_points=_no_entry_points).candidates == ()


def test_installed_entry_points_reads_the_declared_group() -> None:
    """真实环境里这一组目前是空的；断言它不炸、且交出的是字符串对。"""
    assert all(
        isinstance(name, str) and isinstance(value, str)
        for name, value in installed_entry_points()
    )


# --------------------------------------------------------------------------- 不导入


def test_discovery_imports_nothing(tmp_path: Path) -> None:
    _file_plugin(tmp_path, "probe_untouched", "raise AssertionError('不该被导入')")
    found = discover(search_paths=[tmp_path], entry_points=_no_entry_points)
    assert [c.plugin_id for c in found.candidates] == ["probe_untouched"]
    assert not any("probe_untouched" in name for name in sys.modules)


def test_reading_a_module_candidate_really_executes_it(tmp_path: Path) -> None:
    """上一条断言的自证：真的去读时那份模块**必须**被执行，否则它测的是空气。"""
    _file_plugin(tmp_path, "probe_executed", "raise RuntimeError('boom')")
    (candidate,) = discover(search_paths=[tmp_path], entry_points=_no_entry_points).candidates
    with pytest.raises(NucleaError) as caught:
        read_candidate(candidate)
    assert caught.value.code is ErrorCode.PLUGIN_LOAD_FAILED
    # 只放类型名不放异常消息——第三方模块的异常文本可能带着凭据。
    assert caught.value.detail["exception"] == "RuntimeError"
    assert "boom" not in repr(caught.value)


def test_a_module_candidate_does_not_pollute_sys_path(tmp_path: Path) -> None:
    _file_plugin(tmp_path, "solo")
    before = list(sys.path)
    (candidate,) = discover(search_paths=[tmp_path], entry_points=_no_entry_points).candidates
    read_candidate(candidate)
    assert sys.path == before


# --------------------------------------------------------------------------- 读取


def test_reading_a_directory_candidate_returns_the_toml_mapping(tmp_path: Path) -> None:
    _directory_plugin(tmp_path, "acme")
    (candidate,) = discover(search_paths=[tmp_path], entry_points=_no_entry_points).candidates
    data = read_candidate(candidate)
    assert isinstance(data, dict)
    assert data["id"] == "acme"
    assert data["capabilities"] == [{"kind": "tool", "name": "acme.ping"}]


def test_reading_a_module_candidate_returns_its_manifest_object(tmp_path: Path) -> None:
    _file_plugin(tmp_path, "solo")
    (candidate,) = discover(search_paths=[tmp_path], entry_points=_no_entry_points).candidates
    assert read_candidate(candidate) == {"id": "solo", "version": "1.0.0"}


def test_broken_toml_is_a_manifest_problem_not_a_load_problem(tmp_path: Path) -> None:
    """写错的 TOML 是**声明**的问题：用户要改的是那个文件，不是安装。"""
    _directory_plugin(tmp_path, "acme", "id = ")
    (candidate,) = discover(search_paths=[tmp_path], entry_points=_no_entry_points).candidates
    with pytest.raises(NucleaError) as caught:
        read_candidate(candidate)
    assert caught.value.code is ErrorCode.PLUGIN_MANIFEST_UNSUPPORTED
    assert caught.value.detail["plugin_id"] == "acme"


def test_a_module_without_a_manifest_attribute_fails(tmp_path: Path) -> None:
    _file_plugin(tmp_path, "empty", "X = 1")
    (candidate,) = discover(search_paths=[tmp_path], entry_points=_no_entry_points).candidates
    with pytest.raises(NucleaError) as caught:
        read_candidate(candidate)
    assert caught.value.code is ErrorCode.PLUGIN_LOAD_FAILED
    assert caught.value.detail["attribute"] == "MANIFEST"


def test_an_unimportable_entry_point_fails_with_its_origin() -> None:
    candidate = PluginCandidate(
        plugin_id="ghost", kind=SourceKind.ENTRY_POINT, location="no.such.module:MANIFEST"
    )
    with pytest.raises(NucleaError) as caught:
        read_candidate(candidate)
    assert caught.value.code is ErrorCode.PLUGIN_LOAD_FAILED
    assert caught.value.detail["module"] == "no.such.module"


def test_a_malformed_entry_point_value_fails() -> None:
    candidate = PluginCandidate(
        plugin_id="ghost", kind=SourceKind.ENTRY_POINT, location="no.attribute.here"
    )
    with pytest.raises(NucleaError) as caught:
        read_candidate(candidate)
    assert caught.value.code is ErrorCode.PLUGIN_LOAD_FAILED


def test_reading_an_entry_point_uses_the_named_attribute() -> None:
    """entry point 可以指定属性名（单文件不行——文件本身没有第二处写这个约定）。"""
    candidate = PluginCandidate(
        plugin_id="acme", kind=SourceKind.ENTRY_POINT, location="nucleamind.sdk.version:SDK_VERSION"
    )
    assert isinstance(read_candidate(candidate), str)


# --------------------------------------------------------------------------- 冲突与路径


def test_the_same_id_from_two_sources_disables_both(tmp_path: Path) -> None:
    """选任何一边都是替用户做决定，而这里连「哪一边更新」都无从判断。"""
    _directory_plugin(tmp_path, "acme")
    found = discover(
        search_paths=[tmp_path], entry_points=lambda: (("acme", "acme.plugin:MANIFEST"),)
    )
    assert found.candidates == ()
    (failure,) = found.failures
    assert failure.code is ErrorCode.PLUGIN_REGISTRATION_CONFLICT
    assert failure.detail["plugin_id"] == "acme"
    assert len(failure.detail["origins"]) == 2


def test_a_conflict_does_not_take_down_the_other_candidates(tmp_path: Path) -> None:
    _directory_plugin(tmp_path, "acme")
    _directory_plugin(tmp_path, "other")
    found = discover(
        search_paths=[tmp_path], entry_points=lambda: (("acme", "acme.plugin:MANIFEST"),)
    )
    assert [c.plugin_id for c in found.candidates] == ["other"]


def test_a_missing_search_path_is_reported(tmp_path: Path) -> None:
    """静默忽略会让「我的插件怎么没被发现」查不出原因。"""
    found = discover(search_paths=[tmp_path / "nope"], entry_points=_no_entry_points)
    assert found.candidates == ()
    (failure,) = found.failures
    assert failure.code is ErrorCode.CONFIG_INVALID
    assert "nope" in str(failure.detail["path"])


def test_a_file_given_as_a_search_path_is_reported(tmp_path: Path) -> None:
    path = tmp_path / "notadir.txt"
    path.write_text("x", encoding="utf-8")
    (failure,) = discover(search_paths=[path], entry_points=_no_entry_points).failures
    assert failure.code is ErrorCode.CONFIG_INVALID


def test_no_sources_at_all_is_a_first_class_path() -> None:
    """默认形态：没配搜索路径、没装任何插件包。"""
    assert discover(entry_points=_no_entry_points) == discover(
        search_paths=[], entry_points=_no_entry_points
    )
