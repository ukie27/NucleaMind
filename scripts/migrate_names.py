"""D00 一次性脚本：把遗留代码中的包名与发行名机械重写到新位置。

只做**受限的命名迁移**（技术方案 §4.5）：

    导入前缀   nanobot.<mod>      ->  nucleamind.legacy.<mod>
    导入语句   from nanobot ...   ->  from nucleamind.legacy ...
    包资源名   files("nanobot")   ->  files("nucleamind.legacy")
    日志域     logger.enable("nanobot") -> logger.enable("nucleamind.legacy")
    发行名     nanobot-ai         ->  nucleamind

**不处理**（迁移期 `legacy/` 的运行契约保持不变）：
`NANOBOT_*` 环境变量、`~/.nanobot/` 实例目录、camelCase 配置别名、
面向用户的帮助文本与 User-Agent 等历史叙述。

构建资源路径、`pyproject.toml`、`parents[N]` 层级等少量位置由 A3 手工处理——
它们各自只有一两处，机械规则的误伤风险高于收益。

D00 完成后删除本脚本。

用法：
    python scripts/migrate_names.py --apply
    python scripts/migrate_names.py --check     # 只报告残留，不改文件
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent

_TEXT_SUFFIXES = {".py", ".pyi", ".toml", ".cfg", ".ini", ".txt"}

# 参考源码目录只读，且 `references/nanobot` 就是上游本体，绝不能改。
_EXCLUDED_PREFIXES = (
    "references/",
    "webui/node_modules/",
    "docs/",
    ".agent/",
)

_EXCLUDED_FILES = {
    # 该脚本自身与参考索引工具都合法地提到 "nanobot" 字面量。
    "scripts/migrate_names.py",
    "scripts/test_snapshot.py",
    "scripts/reference_index.py",
    # A3 整体重写，机械规则会误伤 entry point 组名与构建路径。
    "pyproject.toml",
}

Rule = tuple[str, re.Pattern[str], str]

_RULES: tuple[Rule, ...] = (
    # `from nanobot import X` / `from nanobot.pkg import X`
    ("from-import", re.compile(r"(?<![\w.])from nanobot(?=[.\s])"), "from nucleamind.legacy"),
    # 点号模块路径：`nanobot.config.schema`、mock.patch 字符串、docstring 引用。
    # 要求后面紧跟小写标识符字符，避免命中句末的 "... nanobot." 与 `~/.nanobot/`。
    ("module-path", re.compile(r"(?<![\w.])nanobot\.(?=[a-z_])"), "nucleamind.legacy."),
    # 包资源根：importlib.resources.files("nanobot")
    (
        "resource-root",
        re.compile(r"(?<![\w.])(files|pkg_files)\(\s*\"nanobot\"\s*\)"),
        r'\1("nucleamind.legacy")',
    ),
    # loguru 日志域按模块名前缀匹配，必须跟着包名一起改。
    (
        "logger-domain",
        re.compile(r"(logger\.(?:enable|disable))\(\s*\"nanobot\"\s*\)"),
        r'\1("nucleamind.legacy")',
    ),
    ("sys-modules", re.compile(r"sys\.modules\[\s*\"nanobot\"\s*\]"), 'sys.modules["nucleamind.legacy"]'),
    # 发行名（importlib.metadata 查询与 pip install 目标）
    ("dist-name", re.compile(r"\"nanobot-ai\""), '"nucleamind"'),
    ("dist-extra", re.compile(r"nanobot-ai\["), "nucleamind["),
)

# `--check` 阶段允许保留的旧名：迁移期 `legacy/` 的运行契约与历史叙述。
_ALLOWED_RESIDUAL = re.compile(
    r"""
      NANOBOT_[A-Z0-9_]+          # 环境变量
    | (?<![\w])\.nanobot(?![\w])  # ~/.nanobot 实例目录
    | \.nanobot\b                 # 相对导入 `.nanobot`（legacy/nanobot.py 门面）
    | Nanobot                     # 门面类名 Nanobot / NanobotDingTalkHandler
    | nanobot-gateway             # 服务名
    | nanobot_                    # 遗留标识符前缀
    """,
    re.VERBOSE,
)


def _tracked_files() -> list[Path]:
    raw_out = subprocess.run(
        ["git", "ls-files", "-z"], cwd=_ROOT, capture_output=True, check=True
    ).stdout
    out = raw_out.decode("utf-8")
    files: list[Path] = []
    for raw in out.split("\0"):
        if not raw:
            continue
        rel = raw.replace("\\", "/")
        if rel.startswith(_EXCLUDED_PREFIXES) or rel in _EXCLUDED_FILES:
            continue
        path = _ROOT / rel
        if path.suffix in _TEXT_SUFFIXES and path.is_file():
            files.append(path)
    return files


def _rewrite(text: str, counts: Counter[str]) -> str:
    for name, pattern, replacement in _RULES:
        text, hits = pattern.subn(replacement, text)
        if hits:
            counts[name] += hits
    return text


def _read(path: Path) -> str:
    # newline="" 保留原始行尾，避免机械改写顺带把 CRLF 变成 LF。
    with path.open("r", encoding="utf-8", newline="") as handle:
        return handle.read()


def _write(path: Path, text: str) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(text)


def run_apply() -> int:
    counts: Counter[str] = Counter()
    changed = 0
    for path in _tracked_files():
        original = _read(path)
        updated = _rewrite(original, counts)
        if updated != original:
            _write(path, updated)
            changed += 1
    print(f"[migrate] 改写 {changed} 个文件")
    for name, _pattern, _replacement in _RULES:
        print(f"  {name:<14} {counts.get(name, 0)}")
    print(f"  {'合计':<12} {sum(counts.values())}")
    return 0


def run_check() -> int:
    residual: list[tuple[str, int, str]] = []
    for path in _tracked_files():
        rel = path.relative_to(_ROOT).as_posix()
        for lineno, line in enumerate(_read(path).splitlines(), 1):
            if not re.search(r"nanobot", line, re.IGNORECASE):
                continue
            if _ALLOWED_RESIDUAL.sub("", line).lower().count("nanobot") == 0:
                continue
            residual.append((rel, lineno, line.strip()[:140]))

    print(f"[migrate] 需人工确认的旧名残留：{len(residual)} 处")
    for rel, lineno, line in residual:
        print(f"  {rel}:{lineno}: {line}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="D00 包名机械迁移")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--apply", action="store_true", help="就地改写")
    group.add_argument("--check", action="store_true", help="只报告残留")
    args = parser.parse_args(argv)
    return run_apply() if args.apply else run_check()


if __name__ == "__main__":
    sys.exit(main())
