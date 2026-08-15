# NucleaMind

NucleaMind is an independent Agent Kernel project derived from
[HKUDS/nanobot](https://github.com/HKUDS/nanobot) under the MIT license.

The goal is a small, stable kernel whose optional capabilities are supplied by
plugins. `D35` removed the last of the inherited nanobot implementation, so the
repository now contains only the new architecture.

## Current Status

The kernel is complete and usable: contracts, turn engine, configuration,
observability, routing, plugin runtime, six built-in capabilities, and the `nm`
CLI. Remaining work is capability plugins — Memory, extended tools, and
cron/automation.

- The Python package is `nucleamind`, the distribution is `nucleamind`, and the
  only CLI command is `nm`. No `nanobot` alias is kept.
- Instance data lives in `~/.nucleamind/<instance>/`; configuration is
  snake_case and validated against a generated JSON Schema.
- The project is developed independently and does not submit changes back to the
  upstream nanobot repository.
- NucleaMind is not currently published to PyPI. Installing `nanobot-ai` from
  PyPI installs the upstream project, not this repository.

## Architecture

Six layers, dependencies flow downward only (rules `R1`–`R5`, enforced by
`tests/architecture/`):

```text
src/nucleamind/
├── contracts/   # public data contracts, pure types, zero internal deps
├── kernel/      # mechanism, depends only on contracts
├── sdk/         # the only surface plugins depend on
├── builtins/    # default capabilities, same standing as plugins
├── runtime/     # assembly root + the `nm` executable
└── embed/       # embedded Python SDK
```

Capabilities are registered through one `NucleaAPI` implementation; built-ins and
external plugins share the same load path, permission model, and lifecycle.
Official plugins live in [`plugins/`](./plugins/README.md); runnable minimal
examples are in [`examples/plugins/`](./examples/plugins/README.md).

## Development Setup

Python 3.11 or newer. Work from a local checkout with a virtual environment.

```bash
python -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"

# Plugins are discovered through entry points, so they must actually be
# installed. `--no-deps` keeps platform SDKs out of the test environment on
# purpose: no plugin's test tree may depend on its vendor SDK.
.venv/bin/python -m pip install --no-deps -e examples/plugins/nucleamind-plugin-echo-tool
.venv/bin/python -m pip install --no-deps -e examples/plugins/nucleamind-plugin-session-memory
.venv/bin/python -m pip install --no-deps -e plugins/nucleamind-plugin-openai-api
.venv/bin/python -m pip install --no-deps -e plugins/nucleamind-plugin-anthropic
.venv/bin/python -m pip install --no-deps -e plugins/nucleamind-plugin-discord
.venv/bin/python -m pip install --no-deps -e plugins/nucleamind-plugin-feishu
```

On Windows use `.venv\Scripts\python.exe` instead of `.venv/bin/python`.

## Common Commands

```bash
# Tests
pytest
pytest tests/architecture -q          # layer guards, run as a separate CI job

# Lint. Do not run ruff format.
ruff check src/ plugins/ examples/ scripts/ tests/

# Strict type checking
uv sync --all-extras --dev
uv run --no-sync basedpyright

# First run, then a turn
nm init
nm run

# Headless: serve every enabled Channel plugin
nm serve

# Diagnostics
nm capabilities        # which capabilities actually took effect, and from where
nm plugins list
nm permissions
```

## Documentation

- [Development background](./docs/project/开发背景.md)
- [Repository instructions](./AGENTS.md)
- [Architecture constraints](./.agent/design.md)
- [Security boundaries](./.agent/security.md)
- [Common implementation gotchas](./.agent/gotchas.md)
- [Documentation index](./docs/README.md)
- [Writing a plugin](./docs/plugin-development.md)

User-facing documentation (installation, configuration reference, CLI reference,
deployment) has not been written for the new kernel yet. `nm init` writes a
config with a `$schema` reference, and `nm --help` lists every subcommand.

## Attribution

NucleaMind is based on nanobot and retains the upstream MIT license and required
third-party notices. See [LICENSE](./LICENSE) and
[THIRD_PARTY_NOTICES.md](./THIRD_PARTY_NOTICES.md).
