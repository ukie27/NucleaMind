"""记录 `nm` 的启动开销指标（技术方案 §12.4 第 6 步）。

常驻脚本。测量两件事：

    import_ms      `import nucleamind` 的耗时（必须保持零副作用、零子模块导入）
    version_ms     `nm --version` 全流程耗时（进程启动 + argv 解析）
    imported       `import nucleamind` 之后进入 sys.modules 的本项目模块清单

第三项是最有价值的：`nucleamind/__init__.py` 承诺「零依赖、零副作用」，一旦有人
在包根加了便利导入，清单会立刻变长，而耗时可能还看不出来。

用法：
    python scripts/check_startup_cost.py               # 人读
    python scripts/check_startup_cost.py --json        # 机读，供 CI 记录
    python scripts/check_startup_cost.py --check       # 越过阈值即非零退出
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import textwrap
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent

# 阈值宽松，只用于拦「数量级劣化」，不做微基准。冷/热缓存与 CI 机器差异都在这之内。
IMPORT_BUDGET_MS = 150.0
VERSION_BUDGET_MS = 2000.0

# `import nucleamind` 之后允许出现在 sys.modules 里的本项目模块。
# 包根之外任何东西被拉进来，都说明有人在 __init__.py 加了便利导入。
ALLOWED_EAGER_MODULES = frozenset({"nucleamind"})

_MEASURE_IMPORT = textwrap.dedent(
    """
    import json, sys, time

    start = time.perf_counter()
    import nucleamind  # noqa: F401
    elapsed_ms = (time.perf_counter() - start) * 1000

    imported = sorted(
        name for name in sys.modules
        if name == "nucleamind" or name.startswith("nucleamind.")
    )
    json.dump({"import_ms": elapsed_ms, "imported": imported}, sys.stdout)
    """
)


def _run_python(code: str) -> str:
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if completed.returncode != 0:
        raise SystemExit(
            f"[startup-cost] 子进程失败（{completed.returncode}）：\n{completed.stderr}"
        )
    return completed.stdout


def measure_import() -> dict[str, object]:
    """在干净子进程中测量 `import nucleamind`（同进程测量会被已导入模块污染）。"""
    return json.loads(_run_python(_MEASURE_IMPORT))


def measure_version() -> float:
    """测量 `nm --version` 全流程；走 `python -m` 以免依赖 console script 已安装。"""
    start = time.perf_counter()
    completed = subprocess.run(
        [sys.executable, "-m", "nucleamind.runtime.cli.main", "--version"],
        cwd=_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    elapsed_ms = (time.perf_counter() - start) * 1000
    if completed.returncode != 0:
        raise SystemExit(
            f"[startup-cost] `nm --version` 失败（{completed.returncode}）：\n{completed.stderr}"
        )
    return elapsed_ms


def collect() -> dict[str, object]:
    result = measure_import()
    return {
        "import_ms": round(float(result["import_ms"]), 2),  # type: ignore[arg-type]
        "version_ms": round(measure_version(), 2),
        "imported": result["imported"],
        "budgets": {"import_ms": IMPORT_BUDGET_MS, "version_ms": VERSION_BUDGET_MS},
    }


def check(data: dict[str, object]) -> list[str]:
    """返回越界说明；全部在预算内时返回空列表。"""
    problems: list[str] = []

    import_ms = float(data["import_ms"])  # type: ignore[arg-type]
    if import_ms > IMPORT_BUDGET_MS:
        problems.append(f"import nucleamind 耗时 {import_ms}ms > {IMPORT_BUDGET_MS}ms")

    version_ms = float(data["version_ms"])  # type: ignore[arg-type]
    if version_ms > VERSION_BUDGET_MS:
        problems.append(f"nm --version 耗时 {version_ms}ms > {VERSION_BUDGET_MS}ms")

    imported = set(data["imported"])  # type: ignore[arg-type]
    unexpected = sorted(imported - ALLOWED_EAGER_MODULES)
    if unexpected:
        problems.append(
            "`import nucleamind` 拉入了额外子模块（包根必须零副作用）："
            + ", ".join(unexpected)
        )

    return problems


def _print_table(data: dict[str, object]) -> None:
    imported = data["imported"]
    assert isinstance(imported, list)
    print("nm 启动开销")
    print("=" * 46)
    print(f"  import nucleamind   {data['import_ms']:>8} ms   (预算 {IMPORT_BUDGET_MS} ms)")
    print(f"  nm --version        {data['version_ms']:>8} ms   (预算 {VERSION_BUDGET_MS} ms)")
    print(f"  急切导入的模块      {len(imported)} 个：{', '.join(imported)}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="记录 nm 启动开销")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    parser.add_argument("--out", type=Path, help="把 JSON 写入文件（隐含 --json）")
    parser.add_argument("--check", action="store_true", help="越过阈值以非零码退出")
    args = parser.parse_args(argv)

    data = collect()

    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"[startup-cost] 写出 {args.out}")
    elif args.json:
        json.dump(data, sys.stdout, indent=2, ensure_ascii=False)
        sys.stdout.write("\n")
    else:
        _print_table(data)

    if args.check:
        problems = check(data)
        if problems:
            print("[startup-cost] 启动开销回归：", file=sys.stderr)
            for line in problems:
                print(f"  {line}", file=sys.stderr)
            return 1
        print("[startup-cost] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
