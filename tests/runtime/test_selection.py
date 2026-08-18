"""运行时能力选择：显式配置 Context Compactor。"""

from __future__ import annotations

import pytest

from nucleamind.contracts import Builtin, CapabilityKind, CompactionResult, ErrorCode, NucleaError
from nucleamind.kernel.config import validate_config
from nucleamind.kernel.plugins import RegisteredContextCompactor
from nucleamind.kernel.registry import CapabilityRegistry
from nucleamind.runtime.selection import select_compactor
from nucleamind.sdk.testing import StaticContextCompactor


def registry_with_compactor() -> tuple[CapabilityRegistry, StaticContextCompactor]:
    registry = CapabilityRegistry()
    compactor = StaticContextCompactor(CompactionResult(through=1, content="摘要"))
    with registry.batch(Builtin()) as batch:
        batch.add(
            CapabilityKind.COMPACTOR,
            "summary",
            RegisteredContextCompactor(compactor=compactor),
        )
    registry.freeze(registry.registrations)
    return registry, compactor


def test_registered_compactor_is_not_enabled_implicitly() -> None:
    registry, _ = registry_with_compactor()
    assert select_compactor(registry, validate_config({})) is None


def test_configured_compactor_is_selected_with_timeout() -> None:
    registry, compactor = registry_with_compactor()
    config = validate_config(
        {"context": {"compactor": "summary", "compactor_timeout_ms": 1234}}
    )

    selected = select_compactor(registry, config)

    assert selected is not None
    assert selected.compactor is compactor
    assert selected.name == "summary"
    assert selected.timeout_ms == 1234


def test_missing_configured_compactor_fails_startup() -> None:
    registry, _ = registry_with_compactor()

    with pytest.raises(NucleaError) as caught:
        select_compactor(registry, validate_config({"context": {"compactor": "missing"}}))

    assert caught.value.code is ErrorCode.CAPABILITY_MISSING
    assert caught.value.detail["pointer"] == "/context/compactor"
