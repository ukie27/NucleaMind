"""`tests/runtime/` 与 `tests/embed/` 的公共装配：把真实内建清单的模型换成 Fake。

职责：提供 `TEST_MANIFESTS`（真实的 `BUILTIN_MANIFESTS`，但 `model-openai` 换成一个
注册 `FakeModelProvider` 的假插件）、写一份最小 `config.json` 的助手，以及脚本化模型回复
的入口。
不负责：任何断言。

**只换模型这一项**：`D23` 要验的是装配链本身（配置块怎么交下去、能力怎么取回、Channel
泵怎么转），把内建换成 Fake 就等于让这套用例证明一条没人会走的路（`tests/integration/`
的同一条判据）。模型是唯一必须换掉的——它是清单里唯一会出网的那个。

`setup` 用 `"tests.runtime._support:setup_fake_model"` 引用本模块：`import_setup()` 接受
任何 `module:func`，内建与外部插件在这一点上没有区别（`SDK-007`）。
"""

from __future__ import annotations

import json
from pathlib import Path

from nucleamind.builtins.registry import BUILTIN_MANIFESTS
from nucleamind.contracts import CapabilityKind, JsonValue, ModelResponse
from nucleamind.sdk import CapabilityDecl, NucleaAPI, PluginManifest
from nucleamind.sdk.testing import (
    FAKE_MODEL_ID,
    FakeModelProvider,
    text_response,
    tool_call_response,
)

__all__ = [
    "FAKE_MODEL_ID",
    "SCRIPT",
    "TEST_MANIFESTS",
    "manifests_without",
    "setup_fake_model",
    "text_response",
    "tool_call_response",
    "write_config",
]

#: 假模型这次要按顺序返回的响应。用例在 `bootstrap()` **之前**改它。
#: 模块级可变状态在生产代码里是错的，在这里是必需的——`setup(api)` 的签名只有 `api`，
#: 而脚本必须由用例决定。每个用例自己 `SCRIPT[:] = [...]`。
SCRIPT: list[ModelResponse] = []


def setup_fake_model(api: NucleaAPI) -> None:
    """假模型插件的 `setup`。与任何内建同型：拿 Host、注册一次、返回。"""
    api.register_model_provider("fake", FakeModelProvider(list(SCRIPT)))


#: 假模型的 manifest。`critical=True` 与真的 `model-openai` 一致——没有模型的实例
#: 起不来这件事要在用例里同样成立。
FAKE_MODEL: PluginManifest = PluginManifest(
    id="model-openai",
    version="0.1.0",
    sdk_range=">=0.1.0,<0.2.0",
    setup="tests.runtime._support:setup_fake_model",
    capabilities=(CapabilityDecl(kind=CapabilityKind.MODEL, name="fake"),),
    critical=True,
)

#: 真实内建清单，模型换成 Fake。其余六份**原封不动**。
TEST_MANIFESTS: tuple[PluginManifest, ...] = tuple(
    FAKE_MODEL if manifest.id == "model-openai" else manifest for manifest in BUILTIN_MANIFESTS
)


def manifests_without(plugin_id: str) -> tuple[PluginManifest, ...]:
    """去掉某一份 manifest 的清单，用来验「必需能力缺失」。"""
    return tuple(manifest for manifest in TEST_MANIFESTS if manifest.id != plugin_id)


def write_config(root: Path, **sections: JsonValue) -> Path:
    """在实例目录里写一份 `config.json`。默认已经指定了模型。"""
    document: dict[str, JsonValue] = {"model": {"name": FAKE_MODEL_ID, "provider": "fake"}}
    document.update(sections)
    root.mkdir(parents=True, exist_ok=True)
    path = root / "config.json"
    path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    return path
