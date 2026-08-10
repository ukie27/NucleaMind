"""D00 一次性工具：捕获与比对测试行为基线。

用途：仓库重构（`nanobot/` -> `src/nucleamind/legacy/`）会改变 pytest node ID，
因此需要一份「规范化用例 ID -> 结果」的基线，用于证明重构没有丢失或改变用例。

D00 验收通过后，本脚本与 `migration-snapshot/` 一并删除。

用法：
    python scripts/test_snapshot.py capture --out migration-snapshot/before.json
    python scripts/test_snapshot.py compare --before before.json --after after.json

`capture` 先跑 `--collect-only` 再跑完整测试；任一阶段出现采集错误（collection
error）都会以非零码退出且拒绝写出基线——模块导入失败会让用例静默消失，
这种基线不可信。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent

# 「根标签 + 相对路径」归一：文件移动会改变 node ID 的路径部分，但根标签保证
# tests/channels/... 与 nanobot/channels/... 归一后不会相撞。顺序敏感——
# 长前缀必须排在短前缀之前。
_ROOT_PREFIXES: tuple[tuple[str, str], ...] = (
    ("src/nucleamind/legacy/", "pkg"),
    ("nanobot/", "pkg"),
    ("tests/legacy/", "tests"),
    ("tests/", "tests"),
)

# 同一用例的 setup/call/teardown 可能各产生一个报告，取严重度最高的作为结果。
_SEVERITY: dict[str, int] = {
    "passed": 0,
    "xpassed": 1,
    "skipped": 2,
    "xfailed": 3,
    "failed": 4,
    "error": 5,
    "notrun": 6,
}


def canonical_id(nodeid: str) -> str:
    """把 pytest node ID 归一为「根标签:相对路径::用例」。"""
    path, sep, rest = nodeid.partition("::")
    path = path.replace("\\", "/")
    for prefix, label in _ROOT_PREFIXES:
        if path.startswith(prefix):
            return f"{label}:{path[len(prefix):]}{sep}{rest}"
    return f"other:{path}{sep}{rest}"


# --------------------------------------------------------------------------
# pytest 端：作为子进程运行一次 pytest，把原始结果写成 JSON
# --------------------------------------------------------------------------


def _phase_outcome(report: Any) -> str | None:
    """把单个阶段报告翻译成结果标签，无关阶段返回 None。"""
    was_xfail = hasattr(report, "wasxfail")
    if report.when == "call":
        if was_xfail:
            return "xfailed" if report.skipped else "xpassed"
        return str(report.outcome)
    if report.failed:
        return "error"
    if report.when == "setup" and report.skipped:
        return "xfailed" if was_xfail else "skipped"
    return None


class _SnapshotPlugin:
    def __init__(self) -> None:
        self.collected: list[str] = []
        self.outcomes: dict[str, str] = {}
        self.collect_errors: list[dict[str, str]] = []

    def pytest_collection_modifyitems(self, items: list[Any]) -> None:
        self.collected.extend(str(item.nodeid) for item in items)

    def pytest_collectreport(self, report: Any) -> None:
        if report.failed:
            self.collect_errors.append(
                {
                    "nodeid": str(report.nodeid or "<root>"),
                    "detail": str(report.longrepr)[:2000],
                }
            )

    def pytest_runtest_logreport(self, report: Any) -> None:
        outcome = _phase_outcome(report)
        if outcome is None:
            return
        nodeid = str(report.nodeid)
        previous = self.outcomes.get(nodeid)
        if previous is None or _SEVERITY[outcome] > _SEVERITY[previous]:
            self.outcomes[nodeid] = outcome


def _run_pytest(args: list[str], raw_out: Path) -> int:
    import pytest

    plugin = _SnapshotPlugin()
    exit_code = pytest.main(args, plugins=[plugin])
    raw_out.write_text(
        json.dumps(
            {
                "exit_code": int(exit_code),
                "collected": plugin.collected,
                "outcomes": plugin.outcomes,
                "collect_errors": plugin.collect_errors,
            }
        ),
        encoding="utf-8",
    )
    return 0


# --------------------------------------------------------------------------
# capture
# --------------------------------------------------------------------------


def _basetemp() -> Path:
    """pytest `tmp_path` 的根目录，必须固定且位于仓库之外。

    固定：两次 capture 的临时目录布局要一致，避免「结果变化」混入环境噪声。
    仓库之外：`tests/utils/test_gitstore.py` 会检测「工作区是否已在 git 仓库内」，
    把 basetemp 放进仓库会改变这些用例的行为。
    """
    return Path(tempfile.gettempdir()) / "nucleamind-pytest-basetemp"


def _spawn(pytest_args: list[str], label: str) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmp:
        raw = Path(tmp) / "raw.json"
        cmd = [
            sys.executable,
            str(Path(__file__).resolve()),
            "_pytest-run",
            "--raw-out",
            str(raw),
            "--",
            *pytest_args,
        ]
        print(f"[snapshot] {label}: {' '.join(pytest_args)}", flush=True)
        completed = subprocess.run(cmd, cwd=_ROOT)
        if not raw.is_file():
            raise SystemExit(
                f"[snapshot] {label} 未产出结果文件（pytest 子进程退出码 "
                f"{completed.returncode}），基线不可信"
            )
        return json.loads(raw.read_text(encoding="utf-8"))


def cmd_capture(out: Path, pytest_args: list[str]) -> int:
    base_args = [
        "-q",
        "--no-header",
        "-p",
        "no:cacheprovider",
        "--basetemp",
        str(_basetemp()),
        *pytest_args,
    ]

    collect = _spawn(["--collect-only", *base_args], "collect-only")
    full = _spawn(base_args, "full run")

    collect_errors = collect["collect_errors"] + full["collect_errors"]
    if collect_errors:
        print("[snapshot] 存在采集错误，拒绝写出基线：", file=sys.stderr)
        for item in collect_errors:
            print(f"  - {item['nodeid']}", file=sys.stderr)
            print(f"    {item['detail'].splitlines()[-1] if item['detail'] else ''}", file=sys.stderr)
        return 2

    universe = list(dict.fromkeys([*collect["collected"], *full["collected"]]))
    outcomes: dict[str, str] = dict(full["outcomes"])

    tests: dict[str, str] = {}
    collisions: list[str] = []
    for nodeid in universe:
        key = canonical_id(nodeid)
        value = outcomes.get(nodeid, "notrun")
        if key in tests and tests[key] != value:
            collisions.append(key)
        tests[key] = value
    # 只在完整运行中出现（例如动态生成）的用例也要收进来。
    for nodeid, value in outcomes.items():
        tests.setdefault(canonical_id(nodeid), value)

    counts: dict[str, int] = {}
    for value in tests.values():
        counts[value] = counts.get(value, 0) + 1

    snapshot: dict[str, Any] = {
        "version": 1,
        "pytest_args": pytest_args,
        "exit_codes": {"collect": collect["exit_code"], "full": full["exit_code"]},
        "counts": dict(sorted(counts.items())),
        "total": len(tests),
        "collect_errors": [],
        "canonical_collisions": sorted(set(collisions)),
        "tests": dict(sorted(tests.items())),
    }

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(snapshot, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    print(f"[snapshot] 写出 {out}：{snapshot['total']} 个用例 {snapshot['counts']}")
    if snapshot["canonical_collisions"]:
        print(
            f"[snapshot] 警告：{len(snapshot['canonical_collisions'])} 个归一 ID 相撞",
            file=sys.stderr,
        )
        return 3
    return 0


# --------------------------------------------------------------------------
# compare
# --------------------------------------------------------------------------


def cmd_compare(before_path: Path, after_path: Path) -> int:
    before = json.loads(before_path.read_text(encoding="utf-8"))
    after = json.loads(after_path.read_text(encoding="utf-8"))

    before_tests: dict[str, str] = before["tests"]
    after_tests: dict[str, str] = after["tests"]

    missing = sorted(set(before_tests) - set(after_tests))
    added = sorted(set(after_tests) - set(before_tests))
    changed = sorted(
        key for key in set(before_tests) & set(after_tests) if before_tests[key] != after_tests[key]
    )

    def dump(title: str, items: list[str], detail: bool = False) -> None:
        print(f"\n== {title}: {len(items)}")
        for key in items[:200]:
            if detail:
                print(f"  {key}: {before_tests[key]} -> {after_tests[key]}")
            else:
                print(f"  {key}")
        if len(items) > 200:
            print(f"  ... 另有 {len(items) - 200} 条")

    print(f"before: {before['total']} 个用例 {before['counts']}")
    print(f"after : {after['total']} 个用例 {after['counts']}")
    dump("missing（基线中有、当前没有）", missing)
    dump("added（当前有、基线中没有）", added)
    dump("outcome_changed（结果变化）", changed, detail=True)

    if missing or added or changed:
        print("\n[snapshot] 存在差异", file=sys.stderr)
        return 1
    print("\n[snapshot] 逐项一致")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="D00 测试行为基线工具")
    sub = parser.add_subparsers(dest="command", required=True)

    capture = sub.add_parser("capture", help="采集当前基线")
    capture.add_argument("--out", required=True, type=Path)
    capture.add_argument("pytest_args", nargs="*", help="附加 pytest 参数，如 -n auto")

    compare = sub.add_parser("compare", help="比对两份基线")
    compare.add_argument("--before", required=True, type=Path)
    compare.add_argument("--after", required=True, type=Path)

    runner = sub.add_parser("_pytest-run", help="内部：在子进程中跑一次 pytest")
    runner.add_argument("--raw-out", required=True, type=Path)
    runner.add_argument("pytest_args", nargs="*")

    args = parser.parse_args(argv)
    if args.command == "capture":
        return cmd_capture(args.out, list(args.pytest_args))
    if args.command == "compare":
        return cmd_compare(args.before, args.after)
    return _run_pytest(list(args.pytest_args), args.raw_out)


if __name__ == "__main__":
    raise SystemExit(main())
