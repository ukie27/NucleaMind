# NucleaMind Technical Documentation

This directory documents the implementation currently inherited from nanobot.
Use it to understand the code before extracting kernel interfaces and moving
feature implementations into plugins.

These documents describe the current source tree, not the final NucleaMind
architecture. Product installation, upstream release, contribution, and
marketing guides have intentionally been removed during the refactoring phase.

## Start Here

| Goal | Document |
|---|---|
| Understand project direction | [`project/开发背景.md`](./project/开发背景.md) |
| Follow repository development rules | [`../AGENTS.md`](../AGENTS.md) |
| Continue current development work | [`project/README.md`](./project/README.md) |
| Read reference-project navigation rules | [`references/README.md`](./references/README.md) |
| Understand current runtime ownership and flow | [`architecture.md`](./architecture.md) |
| Extend the current implementation while it is being migrated | [`development.md`](./development.md) |
| Inspect configuration fields and defaults | [`configuration.md`](./configuration.md) |
| Understand provider selection | [`providers.md`](./providers.md) |
| Understand session and runtime concepts | [`concepts.md`](./concepts.md) |
| Read or migrate the built-in session storage format | [`session-storage.md`](./session-storage.md) |
| Understand the plugin permission model | [`permissions.md`](./permissions.md) |
| Write a plugin | [`plugin-development.md`](./plugin-development.md) |
| Inspect WebSocket behavior | [`websocket.md`](./websocket.md) |
| Inspect the current Python SDK | [`python-sdk.md`](./python-sdk.md) |

Exception: [`session-storage.md`](./session-storage.md) documents the **new** kernel's
built-in session storage format (`builtins/session_jsonl/`), not the inherited one. It is a
published compatibility contract for external implementations, so keep it in sync with
`src/nucleamind/builtins/session_jsonl/codec.py`.

Same exception for [`permissions.md`](./permissions.md): it documents the **new** kernel's
plugin permission model (`kernel/plugins/permissions.py`, `runtime/access/`), including the
`permissions.json` file format and the explicit statement that application-level permissions
are **not** process isolation.

Same exception for [`plugin-development.md`](./plugin-development.md): it is the getting-started
guide for the **new** kernel's plugin system, written against `sdk/` and the two examples under
`examples/plugins/`. Its code blocks are executed by `tests/e2e/test_plugin_docs.py`, so they
cannot drift from the implementation.

## Current Feature References

The following pages remain because they explain behavior that still exists in
the inherited implementation:

- [`chat-apps.md`](./chat-apps.md)
- [`memory.md`](./memory.md)
- [`automations.md`](./automations.md)
- [`image-generation.md`](./image-generation.md)
- [`webui.md`](./webui.md)
- [`openai-api.md`](./openai-api.md)
- [`channel-package-guide.md`](./channel-package-guide.md)

Treat feature-specific ownership described in these pages as current state to be
migrated, not as a permanent kernel boundary.

## Documentation Rules

- Do not point NucleaMind users to the upstream nanobot installer, PyPI package,
  issue tracker, pull requests, releases, community channels, or deployment
  buttons.
- Keep `nanobot` in commands and import paths only while the code still uses that
  name.
- Record upstream attribution in `LICENSE`, `THIRD_PARTY_NOTICES.md`, or an
  explicit historical note, not as current project ownership.
- Update architecture documentation when an ownership boundary moves into or
  out of the kernel.
