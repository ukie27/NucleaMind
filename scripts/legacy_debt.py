"""统计 `legacy/` 隔离区的债务指标。

常驻脚本（不随 D00 删除）：`legacy/` 的文件数与行数只允许下降，上升即说明有人
在往隔离区加东西。`D01` 把本脚本接入 CI 与 `tests/architecture/test_legacy_debt.py`。

用法：
    python scripts/legacy_debt.py                 # 人读表格
    python scripts/legacy_debt.py --json          # 机读，供 CI 与守卫测试消费
    python scripts/legacy_debt.py --json --out legacy-debt.json
    python scripts/legacy_debt.py --check         # 棘轮：超过基线即非零退出
    python scripts/legacy_debt.py --lower-baseline  # 迁移完一个模块后下调基线
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_LEGACY = _ROOT / "src" / "nucleamind" / "legacy"
# 棘轮基线。只允许下调：迁完一个模块并删除对应目录后，用 --lower-baseline 更新。
_BASELINE = Path(__file__).resolve().parent / "legacy_debt_baseline.json"

# 只统计源码；生成物与缓存不算债务。
_COUNTED_SUFFIXES = (".py",)
_SKIPPED_DIR_NAMES = {"__pycache__", "web", "dist", "node_modules"}


def _iter_python_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix not in _COUNTED_SUFFIXES:
            continue
        if any(part in _SKIPPED_DIR_NAMES for part in path.relative_to(root).parts[:-1]):
            continue
        files.append(path)
    return files


def collect() -> dict[str, object]:
    if not _LEGACY.is_dir():
        # legacy/ 清空后本脚本与 R6 守卫一并删除；在那之前空目录也是合法状态。
        return {"root": "src/nucleamind/legacy", "exists": False, "files": 0, "lines": 0, "by_dir": {}}

    files = _iter_python_files(_LEGACY)
    lines = 0
    by_dir: dict[str, dict[str, int]] = {}
    for path in files:
        count = len(path.read_bytes().splitlines())
        lines += count
        parts = path.relative_to(_LEGACY).parts
        top = parts[0] if len(parts) > 1 else "."
        bucket = by_dir.setdefault(top, {"files": 0, "lines": 0})
        bucket["files"] += 1
        bucket["lines"] += count

    return {
        "root": "src/nucleamind/legacy",
        "exists": True,
        "files": len(files),
        "lines": lines,
        "by_dir": dict(sorted(by_dir.items(), key=lambda item: -item[1]["lines"])),
    }


def _print_table(data: dict[str, object]) -> None:
    by_dir = data["by_dir"]
    assert isinstance(by_dir, dict)
    print(f"legacy 债务基线（{data['root']}）")
    print("=" * 46)
    print(f"  {'目录':<22} {'文件':>6} {'行数':>9}")
    for name, bucket in by_dir.items():
        print(f"  {name + '/':<22} {bucket['files']:>6} {bucket['lines']:>9}")
    print("-" * 46)
    print(f"  {'合计':<22} {data['files']:>6} {data['lines']:>9}")
    print()
    print("  这两个数字只允许下降。上升即说明有新文件进入隔离区。")


def load_baseline(path: Path = _BASELINE) -> dict[str, int]:
    """读取棘轮基线；缺失时返回空 dict（`--check` 会拒绝在无基线时通过）。"""
    if not path.is_file():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {"files": int(raw["files"]), "lines": int(raw["lines"])}


def check_against_baseline(data: dict[str, object], baseline: dict[str, int]) -> list[str]:
    """返回违反棘轮的说明；数字持平或下降时返回空列表。"""
    problems: list[str] = []
    for key in ("files", "lines"):
        current = int(data[key])  # type: ignore[call-overload]
        allowed = baseline[key]
        if current > allowed:
            problems.append(
                f"{key}: {current} > 基线 {allowed}（+{current - allowed}）"
                "——有新文件或新代码进入了隔离区"
            )
    return problems


def _write_baseline(data: dict[str, object]) -> None:
    payload = {"files": data["files"], "lines": data["lines"]}
    # newline="\n"：基线文件入库，Windows 下的 CRLF 转换会制造无意义 diff。
    _BASELINE.write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8", newline="\n"
    )


def _run_lower_baseline(data: dict[str, object]) -> int:
    baseline = load_baseline()
    if baseline:
        if check_against_baseline(data, baseline):
            print("[legacy-debt] 拒绝：当前数字高于基线，棘轮只能下调", file=sys.stderr)
            return 1
        if (data["files"], data["lines"]) == (baseline["files"], baseline["lines"]):
            print("[legacy-debt] 与基线一致，无需更新")
            return 0
    _write_baseline(data)
    print(f"[legacy-debt] 基线下调为 files={data['files']} lines={data['lines']}")
    return 0


def _run_check(data: dict[str, object]) -> int:
    baseline = load_baseline()
    if not baseline:
        print(f"[legacy-debt] 缺少基线文件 {_BASELINE}", file=sys.stderr)
        return 1
    problems = check_against_baseline(data, baseline)
    if problems:
        print("[legacy-debt] 债务棘轮失败：", file=sys.stderr)
        for line in problems:
            print(f"  {line}", file=sys.stderr)
        return 1
    print(
        f"[legacy-debt] OK  files={data['files']}/{baseline['files']}  "
        f"lines={data['lines']}/{baseline['lines']}"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="统计 legacy/ 债务指标")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    parser.add_argument("--out", type=Path, help="把 JSON 写入文件（隐含 --json）")
    parser.add_argument(
        "--check",
        action="store_true",
        help="与棘轮基线比对，超过基线以非零码退出（CI 门禁）",
    )
    parser.add_argument(
        "--lower-baseline",
        action="store_true",
        help="把基线下调到当前值；数字未下降时拒绝写入",
    )
    args = parser.parse_args(argv)

    data = collect()
    if args.lower_baseline:
        return _run_lower_baseline(data)
    if args.check:
        return _run_check(data)
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"[legacy-debt] 写出 {args.out}")
        return 0
    if args.json:
        json.dump(data, sys.stdout, indent=2, ensure_ascii=False)
        sys.stdout.write("\n")
        return 0
    _print_table(data)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
