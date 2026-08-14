"""Tests for lazy provider exports from nucleamind.legacy.providers."""

from __future__ import annotations

import importlib
import sys


def test_importing_providers_package_is_lazy(monkeypatch) -> None:
    original_package = sys.modules["nucleamind.legacy.providers"]
    monkeypatch.delitem(sys.modules, "nucleamind.legacy.providers", raising=False)
    monkeypatch.delitem(sys.modules, "nucleamind.legacy.providers.openai_compat_provider", raising=False)
    monkeypatch.delitem(sys.modules, "nucleamind.legacy.providers.openai_codex_provider", raising=False)
    monkeypatch.delitem(sys.modules, "nucleamind.legacy.providers.xai_oauth", raising=False)
    monkeypatch.delitem(sys.modules, "nucleamind.legacy.providers.xai_grok_provider", raising=False)
    monkeypatch.delitem(sys.modules, "nucleamind.legacy.providers.github_copilot_provider", raising=False)
    monkeypatch.delitem(sys.modules, "nucleamind.legacy.providers.azure_openai_provider", raising=False)
    monkeypatch.delitem(sys.modules, "nucleamind.legacy.providers.bedrock_provider", raising=False)

    try:
        providers = importlib.import_module("nucleamind.legacy.providers")

        assert "nucleamind.legacy.providers.openai_compat_provider" not in sys.modules
        assert "nucleamind.legacy.providers.openai_codex_provider" not in sys.modules
        assert "nucleamind.legacy.providers.xai_oauth" not in sys.modules
        assert "nucleamind.legacy.providers.xai_grok_provider" not in sys.modules
        assert "nucleamind.legacy.providers.github_copilot_provider" not in sys.modules
        assert "nucleamind.legacy.providers.azure_openai_provider" not in sys.modules
        assert "nucleamind.legacy.providers.bedrock_provider" not in sys.modules
        assert providers.__all__ == [
            "LLMProvider",
            "LLMResponse",
            "OpenAICompatProvider",
            "OpenAICodexProvider",
            "XAIGrokProvider",
            "GitHubCopilotProvider",
            "AzureOpenAIProvider",
            "BedrockProvider",
        ]
    finally:
        # Importing a replacement subpackage also replaces nucleamind.legacy.providers on the
        # parent package. Restore both views so this isolation test cannot pollute
        # later tests that resolve a module through a dotted monkeypatch target.
        monkeypatch.undo()
        setattr(sys.modules["nucleamind.legacy"], "providers", original_package)


def test_explicit_provider_import_still_works(monkeypatch) -> None:
    original_package = sys.modules["nucleamind.legacy.providers"]
    monkeypatch.delitem(sys.modules, "nucleamind.legacy.providers", raising=False)
    monkeypatch.delitem(sys.modules, "nucleamind.legacy.providers.bedrock_provider", raising=False)

    try:
        namespace: dict[str, object] = {}
        exec("from nucleamind.legacy.providers import BedrockProvider", namespace)

        assert namespace["BedrockProvider"].__name__ == "BedrockProvider"
        assert "nucleamind.legacy.providers.bedrock_provider" in sys.modules
    finally:
        monkeypatch.undo()
        setattr(sys.modules["nucleamind.legacy"], "providers", original_package)


def test_openai_codex_supports_progress_deltas() -> None:
    from nucleamind.legacy.providers.openai_codex_provider import OpenAICodexProvider

    assert OpenAICodexProvider.supports_progress_deltas is True
