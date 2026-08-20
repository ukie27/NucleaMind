"""`image` 插件的端到端用例（开发方案 `D37`）：在**真实装配的实例**上生成一张图。

职责：验「装上 image 插件之后，模型真的能调它，而那张图真的落到了插件自己的状态目录里」。
不负责：线格式与落盘细节（`plugins/nucleamind-plugin-image/tests/`）。

**这里唯一的替身仍然是传输层**（`conftest.recorder`）：模型供应商、注册路径、
`ToolExecutor`、资源服务、插件的状态目录分配全是生产实现。因此本文件要求 image 插件
已经装进当前环境：

    pip install -e plugins/nucleamind-plugin-image
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

import httpx
import pytest

from nucleamind.kernel.plugins import installed_entry_points
from nucleamind.kernel.turn import CancelToken
from nucleamind.runtime.bootstrap import bootstrap
from nucleamind.runtime.first_run import MODEL_API_KEY_ENV, MODEL_PLUGIN_ID, MODEL_SECRET_NAME
from nucleamind.runtime.inspect import inspect_capabilities

from ._support import say, use_tool
from .conftest import Recorder

IMAGE_PLUGIN = "image"

#: 默认落点，workspace 相对（`D47`）。与插件的 `IMAGE_DIR_NAME` 是同一个字符串。
IMAGE_DIR = "artifacts/images"
GENERATE_TOOL = "image.generate"

SENTINEL_KEY = "sk-img0123456789abcdefghij"

#: 一张真实的 1×1 PNG。
_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


@pytest.fixture
def instance_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """一台「全新机器」：空实例目录 + 临时 HOME + 没有导出任何凭据。"""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.delenv(MODEL_API_KEY_ENV, raising=False)
    return tmp_path / "instance"


def _write_config(instance_dir: Path, plugins: dict[str, object]) -> None:
    instance_dir.mkdir(parents=True, exist_ok=True)
    document = {
        "model": {"name": "gpt-4o-mini", "provider": "openai"},
        "plugins": {
            MODEL_PLUGIN_ID: {"secrets": {MODEL_SECRET_NAME: f"${{{MODEL_API_KEY_ENV}}}"}},
            **plugins,
        },
    }
    (instance_dir / "config.json").write_text(
        json.dumps(document, ensure_ascii=False), encoding="utf-8"
    )


def _enable_image(instance_dir: Path) -> None:
    _write_config(
        instance_dir,
        {
            "enabled": [IMAGE_PLUGIN],
            IMAGE_PLUGIN: {"secrets": {"api_key": "${IMAGE_API_KEY}"}},
        },
    )


async def _run_prompt(instance_dir: Path, prompt: str) -> int:
    instance = await bootstrap(instance_dir=instance_dir)
    try:
        return await instance.run_cli(["-p", prompt], CancelToken())
    finally:
        await instance.stop()


def _image_response(_: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200, json={"data": [{"b64_json": base64.b64encode(_PNG).decode("ascii")}]}
    )


def test_the_image_plugin_is_installed_as_an_entry_point() -> None:
    """整套用例的前提。**单独成一条**：装漏了要看到一句能照做的话。"""
    names = {name for name, _ in installed_entry_points()}
    assert IMAGE_PLUGIN in names, (
        "image 插件没装。请先跑 `pip install -e plugins/nucleamind-plugin-image`"
    )


async def test_the_tool_reaches_the_registry(instance_dir: Path) -> None:
    _enable_image(instance_dir)

    report = (await inspect_capabilities(instance_dir=instance_dir)).report

    assert GENERATE_TOOL in {entry["name"] for entry in report.to_json()["active"]}


async def test_a_real_turn_writes_a_real_file(
    instance_dir: Path,
    recorder: Recorder,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """一次完整 turn：模型调 `image.generate` → 插件打图像后端 → 图落盘 → 模型作答 →
    附件出现在终帧上。

    **落点是 workspace**（`<instance>/workspace/artifacts/images/`，`D47` 起）：插件经
    `ctx.fs` 写，而 `ctx.fs` 的根由装配根交下来——这条用例同时验了那条交接真的接上了，
    以及那张图真的以附件形态到了 Channel 手里（CLI 把它印成一行 `[附件] <相对路径>`）。
    """
    monkeypatch.setenv(MODEL_API_KEY_ENV, SENTINEL_KEY)
    monkeypatch.setenv("IMAGE_API_KEY", "sk-image0123456789abcdef")
    _enable_image(instance_dir)
    recorder.script(
        use_tool(GENERATE_TOOL, {"prompt": "一只猫"}),
        _image_response,
        say("画好了。"),
    )

    assert await _run_prompt(instance_dir, "画一只猫") == 0

    written = sorted((instance_dir / "workspace" / IMAGE_DIR).glob("image-*.png"))
    assert len(written) == 1
    assert written[0].read_bytes() == _PNG

    # 工具结果里必须带着那条路径——它就是交付物本身。
    follow_up = json.loads(recorder.requests[2].content)
    tools = [m for m in follow_up["messages"] if m.get("role") == "tool"]
    assert written[0].name in str(tools[-1]["content"])

    # 而它必须真的作为**附件**到达 Channel（`D47`）：CLI 把终帧的附件印成一行。
    # 断言在这一层而不是单测里，因为这条路要穿过工具 → TurnState → 终帧 → deliver
    # 四段，其中任何一段漏掉附件，单测都仍然是绿的。
    printed = capsys.readouterr().out
    assert f"{IMAGE_DIR}/{written[0].name}" in printed


async def test_a_missing_credential_is_a_tool_failure_not_a_startup_failure(
    instance_dir: Path, recorder: Recorder, monkeypatch: pytest.MonkeyPatch
) -> None:
    """凭据不在 `setup()` 里取：没导出 `IMAGE_API_KEY` 的实例照样起得来、工具照样在
    生效集合里，只有那一次调用失败。"""
    monkeypatch.setenv(MODEL_API_KEY_ENV, SENTINEL_KEY)
    monkeypatch.delenv("IMAGE_API_KEY", raising=False)
    _enable_image(instance_dir)

    report = (await inspect_capabilities(instance_dir=instance_dir)).report
    assert GENERATE_TOOL in {entry["name"] for entry in report.to_json()["active"]}

    recorder.script(use_tool(GENERATE_TOOL, {"prompt": "一只猫"}), say("画不了。"))
    assert await _run_prompt(instance_dir, "画一只猫") == 0

    # 一个字节都没落盘（`SideEffect.NONE` 的可观察形态）。
    assert not (instance_dir / "workspace" / IMAGE_DIR).exists()
