import ast
import subprocess
import sys
from pathlib import Path


def test_config_base_import_does_not_load_config_schema():
    code = """
import sys
from nucleamind.legacy.config_base import Base
print("nucleamind.legacy.config.schema" in sys.modules)
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout.strip() == "False"


def test_builtin_tool_configs_do_not_depend_on_config_schema_base():
    repo = Path(__file__).resolve().parents[3]
    tool_paths = sorted((repo / "src/nucleamind/legacy/agent/tools").glob("*.py"))

    violations = []
    for path in tool_paths:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            if node.module != "nucleamind.legacy.config.schema":
                continue
            if any(alias.name == "Base" for alias in node.names):
                violations.append(str(path.relative_to(repo)))

    assert violations == []
