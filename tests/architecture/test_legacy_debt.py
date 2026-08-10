"""`legacy/` 债务棘轮：数字只允许下降（技术方案 §4.3 第 3 条）。

职责：断言当前 `legacy/` 的文件数与行数不超过 `scripts/legacy_debt_baseline.json`，
并验证棘轮脚本本身在数字上升时会失败、在下降时才允许下调基线。
不负责：决定基线该降到多少——那由迁移进度决定，迁完一个模块后手工执行
`python scripts/legacy_debt.py --lower-baseline`。

这是「只出不进」从文档约定变成不可绕过检查的地方：新增文件会让 files 上升，
往遗留模块里加代码会让 lines 上升，两者都会在 CI 阻断。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from ._common import REPO_ROOT

_SCRIPT = REPO_ROOT / "scripts" / "legacy_debt.py"
_BASELINE_FILE = REPO_ROOT / "scripts" / "legacy_debt_baseline.json"


def _load_script():
    """按文件路径加载脚本模块；`scripts/` 不是包，不能直接 import。"""
    spec = importlib.util.spec_from_file_location("_legacy_debt_under_test", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def script():
    return _load_script()


def test_baseline_file_exists() -> None:
    assert _BASELINE_FILE.is_file(), (
        f"缺少债务基线 {_BASELINE_FILE}；执行 "
        "`python scripts/legacy_debt.py --lower-baseline` 生成"
    )


def test_current_debt_does_not_exceed_baseline(script) -> None:
    data = script.collect()
    baseline = script.load_baseline()
    problems = script.check_against_baseline(data, baseline)
    assert not problems, (
        "legacy/ 债务上升——「只出不进」被破坏：\n"
        + "\n".join(f"  {line}" for line in problems)
        + "\n迁移代码时请把实现搬到新家，不要往 legacy/ 添加文件。"
    )


def test_check_mode_passes_on_real_tree(script) -> None:
    """`--check` 是 CI 门禁形态，必须在当前仓库返回 0。"""
    assert script.main(["--check"]) == 0


def test_ratchet_rejects_growth(script) -> None:
    """注入「数字上升」必须失败——证明棘轮真的会拦。"""
    baseline = {"files": 352, "lines": 133317}

    grown_lines = {"files": 352, "lines": 133318}
    problems = script.check_against_baseline(grown_lines, baseline)
    assert len(problems) == 1 and "lines" in problems[0]

    grown_files = {"files": 353, "lines": 133317}
    problems = script.check_against_baseline(grown_files, baseline)
    assert len(problems) == 1 and "files" in problems[0]


def test_ratchet_accepts_shrink_and_equal(script) -> None:
    baseline = {"files": 352, "lines": 133317}
    assert script.check_against_baseline(baseline, baseline) == []
    assert script.check_against_baseline({"files": 300, "lines": 120000}, baseline) == []


def test_empty_legacy_is_a_legal_state(script, tmp_path: Path, monkeypatch) -> None:
    """`legacy/` 清空后本脚本与 R6 守卫一并删除；在那之前空目录也合法。"""
    monkeypatch.setattr(script, "_LEGACY", tmp_path / "gone")
    data = script.collect()
    assert data["exists"] is False
    assert (data["files"], data["lines"]) == (0, 0)
    assert script.check_against_baseline(data, script.load_baseline()) == []
