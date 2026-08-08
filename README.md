# NucleaMind

NucleaMind is an independent Agent Kernel project derived from
[HKUDS/nanobot](https://github.com/HKUDS/nanobot) under the MIT license.

The repository currently retains much of nanobot's runtime, channels, tools,
memory, and WebUI while the architecture is being reworked. The target is a
small, stable kernel whose optional capabilities are supplied by plugins.

## Current Status

NucleaMind is in an architecture and large-scale refactoring phase.

- The Python package, import paths, CLI command, and local data directory still
  use the `nanobot` name.
- The project is developed independently and does not submit changes back to
  the upstream nanobot repository.
- NucleaMind is not currently published as a separate PyPI package.
- Installing or upgrading `nanobot-ai` from PyPI installs the upstream project,
  not this repository.
- Existing nanobot features remain available only as the current implementation
  baseline. Their presence does not mean they will remain part of the kernel.

Do not introduce a `nucleamind` Python package or mix `nucleamind` imports with
existing `nanobot` imports until the package migration is designed explicitly.

## Direction

The kernel is expected to retain only the mechanisms required to run and extend
an agent:

- agent execution loop;
- model abstraction;
- unified message contracts and bus;
- session management;
- context interfaces;
- capability and tool registration;
- plugin runtime and lifecycle;
- base configuration.

Feature implementations such as channels, memory backends, browser access, MCP,
WebUI, automation, workflows, and multi-agent systems are candidates for
official or third-party plugins.

See [开发背景.md](./开发背景.md) for the project vision and [AGENTS.md](./AGENTS.md)
for repository development rules.

## Development Setup

Python 3.11 or newer is required. Work from a local checkout and use a virtual
environment.

On Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m scripts.install_channel_dependencies --all-channels
```

On Linux or macOS:

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install -e ".[dev]"
./.venv/bin/python -m scripts.install_channel_dependencies --all-channels
```

The repository does not provide a supported one-command installer during the
refactoring phase.

## Common Commands

```bash
# Focused Python test
pytest tests/test_openai_api.py::test_function -v

# Lint. Do not run ruff format.
ruff check nanobot/

# Strict type checking
uv sync --all-extras --dev
uv run --no-sync python -m scripts.install_channel_dependencies --all-channels
uv run --no-sync basedpyright

# WebUI
cd webui
bun run dev
bun run build
bun run test

# Current gateway command
nanobot gateway
```

When `.venv` exists, use its Python executable for Python commands.

## Documentation

- [Development background](./开发背景.md)
- [Repository instructions](./AGENTS.md)
- [Architecture constraints](./.agent/design.md)
- [Security boundaries](./.agent/security.md)
- [Common implementation gotchas](./.agent/gotchas.md)
- [Technical documentation index](./docs/README.md)
- [Current runtime architecture](./docs/architecture.md)
- [Current configuration reference](./docs/configuration.md)

Documentation under `docs/` describes the inherited implementation where it is
still useful for analysis. It is not a product promise for the future kernel.

## Attribution

NucleaMind is based on nanobot and retains the upstream MIT license and required
third-party notices. See [LICENSE](./LICENSE) and
[THIRD_PARTY_NOTICES.md](./THIRD_PARTY_NOTICES.md).
