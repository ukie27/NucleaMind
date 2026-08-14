"""依赖规则 `R1`–`R6` 的 AST 断言（技术方案 §3.1）。

职责：对真实源码树断言六条依赖规则，并用注入违规样例的反向测试证明守卫会拦。
不负责：规则的判定逻辑本身（见 `_boundaries.py`），也不导入被测模块。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ._boundaries import collect_violations, legacy_importers
from ._common import (
    PACKAGE_DIR,
    REPO_ROOT,
    SRC_DIR,
    make_package_tree,
    plugin_package_roots,
    write_module,
)

# --------------------------------------------------------------------------
# 正向：真实源码树必须干净
# --------------------------------------------------------------------------


def test_real_tree_has_no_dependency_violations() -> None:
    violations = collect_violations(
        src_dir=SRC_DIR,
        repo_root=REPO_ROOT,
        plugin_roots=plugin_package_roots(REPO_ROOT),
    )
    assert not violations, "依赖规则违规：\n" + "\n".join(str(v) for v in violations)


def test_empty_layers_pass() -> None:
    """新层此时多为空骨架，守卫对空目录必须返回通过而不是报错。"""
    assert collect_violations(src_dir=SRC_DIR / "does-not-exist", repo_root=REPO_ROOT) == []


def test_no_new_layer_module_imports_legacy() -> None:
    """`R6` 自 `D31` 起没有例外：新层 → legacy 的导入一条都不许有。

    `D31` 之前这里断言的是「恰好只有 `runtime/legacy_entry.py` 一处」，那条白名单
    随 `nm legacy` 一并删除了。断言从「只有一个」变成「一个也没有」是本模块的收口——
    再出现任何一条新层 → legacy 的导入都是回退，不是新的过渡例外。
    """
    importers = legacy_importers(src_dir=SRC_DIR, repo_root=REPO_ROOT)
    assert importers == [], (
        f"新层不得 import legacy/（`R6` 已无例外），实际为：{importers}"
    )


def test_r6_is_one_directional_legacy_may_import_new_layers(tmp_path: Path) -> None:
    """`R6` 是单向规则：`legacy/` import 新层合法，不得写成对称检查。"""
    src = make_package_tree(tmp_path, layers=("contracts", "kernel", "legacy"))
    write_module(
        src,
        "nucleamind/legacy/api/server.py",
        "from nucleamind.kernel import turn\nfrom nucleamind.contracts import ids\n",
    )
    assert collect_violations(src_dir=src, repo_root=tmp_path) == []


# --------------------------------------------------------------------------
# 反向：每条规则各有一个注入样例，必须被拦下
# --------------------------------------------------------------------------

# (规则号, 违规模块相对 src/ 的路径, 源码)
_INJECTED_VIOLATIONS: list[tuple[str, str, str]] = [
    (
        "R1",
        "nucleamind/contracts/message.py",
        "from nucleamind.kernel.registry import Registry\n",
    ),
    (
        "R2",
        "nucleamind/kernel/turn/engine.py",
        "from nucleamind.builtins.model_openai import Provider\n",
    ),
    (
        "R3",
        "nucleamind/sdk/api.py",
        "from nucleamind.kernel.config import load\n",
    ),
    (
        "R4",
        "nucleamind/builtins/tools_fs/read.py",
        "from nucleamind.kernel.registry import Registry\n",
    ),
    (
        "R5",
        "nucleamind/embed/instance.py",
        "from nucleamind.kernel import turn\nfrom nucleamind.builtins import tools_fs\n",
    ),
    (
        "R6",
        "nucleamind/kernel/turn/engine.py",
        "from nucleamind.legacy.agent.loop import AgentLoop\n",
    ),
]


@pytest.mark.parametrize(
    ("rule", "relative", "source"),
    _INJECTED_VIOLATIONS,
    ids=[rule for rule, _, _ in _INJECTED_VIOLATIONS],
)
def test_inject_violation_is_rejected(
    rule: str, relative: str, source: str, tmp_path: Path
) -> None:
    """注入违规样例必须失败——证明守卫真的会拦，而不是恒返回通过。"""
    src = make_package_tree(tmp_path, layers=("contracts", "kernel", "sdk", "builtins", "runtime", "embed", "legacy"))
    write_module(src, relative, source)

    violations = collect_violations(src_dir=src, repo_root=tmp_path)

    assert violations, f"{rule} 的违规样例没有被拦下：{relative}"
    assert rule in {v.rule for v in violations}, (
        f"样例应被判为 {rule}，实际判为 {sorted({v.rule for v in violations})}"
    )


def test_inject_plugin_importing_kernel_is_rejected(tmp_path: Path) -> None:
    """外部插件与 `builtins/` 同规则（`R4`）：只能 import sdk/ 与 contracts/。"""
    make_package_tree(tmp_path)
    plugin = tmp_path / "plugins" / "memory-sqlite"
    write_module(plugin, "nucleamind_plugin_memory_sqlite/__init__.py", "")
    write_module(
        plugin,
        "nucleamind_plugin_memory_sqlite/store.py",
        "from nucleamind.kernel.registry import Registry\n",
    )

    violations = collect_violations(
        src_dir=tmp_path / "src", repo_root=tmp_path, plugin_roots=[plugin]
    )
    assert {v.rule for v in violations} == {"R4"}, violations


def test_inject_any_legacy_adapter_is_rejected(tmp_path: Path) -> None:
    """`D31` 之后连「那一个」适配器也不再放行。

    这条替代了旧的「第二个适配器才失败」——`runtime/legacy_entry.py` 这个路径本身
    不再特殊，写在那里与写在别处后果完全相同。
    """
    src = make_package_tree(tmp_path, layers=("runtime", "legacy"))
    write_module(
        src,
        "nucleamind/runtime/legacy_entry.py",
        "from nucleamind.legacy.cli.commands import app\n",
    )
    write_module(
        src,
        "nucleamind/runtime/legacy_entry_v2.py",
        "from nucleamind.legacy.cli.commands import app\n",
    )

    violations = collect_violations(src_dir=src, repo_root=tmp_path)
    assert sorted(v.path for v in violations) == [
        "src/nucleamind/runtime/legacy_entry.py",
        "src/nucleamind/runtime/legacy_entry_v2.py",
    ], violations
    assert {v.rule for v in violations} == {"R6"}


def test_relative_imports_are_resolved(tmp_path: Path) -> None:
    """相对导入必须解析为绝对路径，否则 `from ..legacy import x` 会绕过所有规则。"""
    src = make_package_tree(tmp_path, layers=("kernel", "legacy"))
    write_module(src, "nucleamind/kernel/turn/__init__.py", "")
    write_module(src, "nucleamind/kernel/turn/engine.py", "from ...legacy.agent import loop\n")

    violations = collect_violations(src_dir=src, repo_root=tmp_path)
    assert [v.rule for v in violations] == ["R6"], violations


def test_package_dir_is_where_the_guard_thinks_it_is() -> None:
    """路径常量走样会让所有断言静默变成空集合。"""
    assert PACKAGE_DIR.is_dir()
    assert (PACKAGE_DIR / "legacy").is_dir()
