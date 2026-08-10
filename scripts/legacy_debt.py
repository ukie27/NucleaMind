"""统计 `legacy/` 隔离区的债务指标。

常驻脚本（不随 D00 删除）：`legacy/` 的文件数与行数只允许下降，上升即说明有人
在往隔离区加东西。`D01` 把本脚本接入 CI 与 `tests/architecture/test_legacy_debt.py`。

用法：
    python scripts/legacy_debt.py                 # 人读表格
    python scripts/legacy_debt.py --json          # 机读，供 CI 与守卫测试消费
    python scripts/legacy_debt.py --json --out legacy-debt.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_LEGACY = _ROOT / "src" / "nucleamind" / "legacy"

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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="统计 legacy/ 债务指标")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    parser.add_argument("--out", type=Path, help="把 JSON 写入文件（隐含 --json）")
    args = parser.parse_args(argv)

    data = collect()
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
