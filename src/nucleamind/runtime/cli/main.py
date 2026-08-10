"""`nm` 进程入口：argv 解析与子命令派发。

职责：解析顶层 argv，暴露 `nm --version` 与迁移期的 `nm legacy`。
不负责：实现子命令行为，也不组装 Agent 实例——真正的子命令在 D23 落地。
"""

from __future__ import annotations

import sys
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _dist_version

_USAGE = """Usage: nm <command> [args...]

Commands:
  legacy <args...>   Run the migration-period legacy CLI (removed with legacy/agent/)

Options:
  -V, --version      Print the version
  -h, --help         Print this help

The real subcommands (run / plugins / capabilities / config / session) are not
implemented yet.
"""


def resolve_version() -> str:
    try:
        return _dist_version("nucleamind")
    except PackageNotFoundError:
        return "0+unknown"


def app(argv: list[str] | None = None) -> int:
    """`nm` 的进程入口。返回值即进程退出码（console_scripts 包装为 sys.exit）。"""
    args = list(sys.argv[1:] if argv is None else argv)

    if not args or args[0] in ("-h", "--help"):
        sys.stdout.write(_USAGE)
        return 0

    if args[0] in ("-V", "--version"):
        sys.stdout.write(f"nucleamind {resolve_version()}\n")
        return 0

    if args[0] == "legacy":
        # 迁移期唯一的遗留入口。延迟导入：不让遗留依赖进入 `nm --version` 路径。
        from nucleamind.runtime.legacy_entry import run_legacy

        return run_legacy(args[1:])

    sys.stderr.write(f"nm: unknown command {args[0]!r}\n\n{_USAGE}")
    return 2


def main() -> None:
    """`python -m nucleamind.runtime.cli.main` 入口。"""
    raise SystemExit(app())


if __name__ == "__main__":
    main()
