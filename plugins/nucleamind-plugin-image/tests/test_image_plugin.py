"""`image` 插件的行为用例：工具、注册面、以及 SDK 的契约基类。

全部走 `httpx.MockTransport`，一个 socket 都不开（`conftest.py` 的 autouse 夹具是
那句话的可执行断言）。写盘是真的——落在 `tmp_path` 里。
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from _image_fakes import (
    PNG_BYTES,
    Backend,
    ImageContext,
    invocation,
    openai_response,
    openrouter_response,
    png_download,
)
from nucleamind_plugin_image import (
    CONFIG_SCHEMA,
    GENERATE_TOOL,
    MANIFEST,
    ImageGenerateTool,
    ImageStore,
    generate_spec,
    image_directory,
    register,
    resolve_settings,
)

from nucleamind.contracts import (
    CapabilityKind,
    ErrorCode,
    JsonValue,
    NucleaError,
    PermissionKind,
    RiskLevel,
    SideEffect,
    ToolHandler,
    ToolResult,
    ToolSpec,
)
from nucleamind.sdk.testing import ManualCancel, ToolContract


def _tool(
    tmp_path: Path,
    backend: Backend,
    *,
    config: dict[str, JsonValue] | None = None,
    secrets: dict[str, str] | None = None,
) -> ImageGenerateTool:
    ctx = ImageContext(tmp_path, config=config, secrets=secrets)
    settings = resolve_settings(ctx.config)
    store = ImageStore(image_directory(ctx, settings))
    return ImageGenerateTool(ctx, settings, store, transport=backend.transport)


async def _run(
    tmp_path: Path, backend: Backend, arguments: dict[str, JsonValue], **kwargs: object
) -> ToolResult:
    tool = _tool(tmp_path, backend, **kwargs)  # pyright: ignore[reportArgumentType]
    return await tool.execute(invocation(arguments), ManualCancel())


class TestGenerate:
    async def test_a_generated_image_lands_on_disk(self, tmp_path: Path) -> None:
        result = await _run(tmp_path, Backend(openai_response()), {"prompt": "a cat"})
        assert result.ok is True
        assert result.data is not None
        written = Path(str(result.data["paths"][0]))
        assert written.read_bytes() == PNG_BYTES

    async def test_success_reports_an_occurred_side_effect(self, tmp_path: Path) -> None:
        """文件真的写下去了，而且写成功之后没有可失败的步骤。"""
        result = await _run(tmp_path, Backend(openai_response()), {"prompt": "a cat"})
        assert result.side_effect is SideEffect.OCCURRED

    async def test_the_artifact_points_at_the_file(self, tmp_path: Path) -> None:
        """本插件是全项目 `ToolResult.artifacts` 的第一个生产者。"""
        result = await _run(tmp_path, Backend(openai_response()), {"prompt": "a cat"})
        assert len(result.artifacts) == 1
        assert Path(result.artifacts[0].locator).read_bytes() == PNG_BYTES
        assert result.artifacts[0].media_type == "image/png"

    async def test_the_content_lists_the_paths_for_the_model(self, tmp_path: Path) -> None:
        result = await _run(tmp_path, Backend(openai_response()), {"prompt": "a cat"})
        assert result.data is not None
        assert str(result.data["paths"][0]) in result.content

    async def test_count_reaches_the_backend(self, tmp_path: Path) -> None:
        backend = Backend(openai_response(count=2))
        await _run(tmp_path, backend, {"prompt": "a cat", "count": 2})
        assert backend.body_of(0)["n"] == 2

    async def test_identical_images_collapse_onto_one_file(self, tmp_path: Path) -> None:
        """内容寻址的必然结果，而且是想要的：同样的字节不该占两份磁盘。"""
        result = await _run(
            tmp_path, Backend(openai_response(count=2)), {"prompt": "a cat", "count": 2}
        )
        assert result.data is not None
        assert result.data["count"] == 2
        assert len({str(path) for path in result.data["paths"]}) == 1

    async def test_a_url_response_is_downloaded(self, tmp_path: Path) -> None:
        backend = Backend(openai_response(url="https://cdn.example/a.png"), png_download())
        result = await _run(tmp_path, backend, {"prompt": "a cat"})
        assert result.ok is True
        assert len(backend.requests) == 2
        assert backend.requests[1].method == "GET"

    async def test_a_failed_download_is_a_failed_result(self, tmp_path: Path) -> None:
        backend = Backend(
            openai_response(url="https://cdn.example/a.png"), httpx.Response(404)
        )
        result = await _run(tmp_path, backend, {"prompt": "a cat"})
        assert result.ok is False
        assert result.side_effect is SideEffect.NONE

    async def test_openrouter_reads_images_out_of_the_chat_response(
        self, tmp_path: Path
    ) -> None:
        result = await _run(
            tmp_path,
            Backend(openrouter_response()),
            {"prompt": "a cat"},
            config={"provider": "openrouter"},
        )
        assert result.ok is True
        assert Path(result.artifacts[0].locator).read_bytes() == PNG_BYTES

    async def test_the_credential_reaches_the_backend(self, tmp_path: Path) -> None:
        backend = Backend(openai_response())
        await _run(tmp_path, backend, {"prompt": "a cat"}, secrets={"api_key": "sk-xyz"})
        assert backend.requests[0].headers["authorization"] == "Bearer sk-xyz"


class TestFailuresHappenBeforeAnythingIsWritten:
    """三档判定里本插件只用得到两档。**从不产出 `UNKNOWN`**，这几条是那句话的证据。"""

    async def test_a_missing_credential_writes_nothing(self, tmp_path: Path) -> None:
        result = await _run(tmp_path, Backend(), {"prompt": "a cat"}, secrets={})
        assert result.ok is False
        assert result.error is not None
        assert result.error.code is ErrorCode.CONFIG_SECRET_MISSING
        assert result.side_effect is SideEffect.NONE
        assert not (tmp_path / "images").exists()

    async def test_an_upstream_error_writes_nothing(self, tmp_path: Path) -> None:
        result = await _run(tmp_path, Backend(httpx.Response(429)), {"prompt": "a cat"})
        assert result.error is not None
        assert result.error.retryable is True
        assert result.side_effect is SideEffect.NONE

    async def test_an_empty_response_is_a_failure(self, tmp_path: Path) -> None:
        backend = Backend(httpx.Response(200, json={"data": []}))
        result = await _run(tmp_path, backend, {"prompt": "a cat"})
        assert result.ok is False

    async def test_count_above_the_configured_cap_never_reaches_the_backend(
        self, tmp_path: Path
    ) -> None:
        backend = Backend()
        result = await _run(
            tmp_path, backend, {"prompt": "a cat", "count": 99}, config={"max_count": 2}
        )
        assert result.ok is False
        assert backend.requests == []

    @pytest.mark.parametrize(
        "arguments",
        [{}, {"prompt": "  "}, {"prompt": 5}, {"prompt": "a", "style": "x"},
         {"prompt": "a", "count": 0}],
    )
    async def test_bad_arguments_come_back_as_results(
        self, tmp_path: Path, arguments: dict[str, JsonValue]
    ) -> None:
        result = await _run(tmp_path, Backend(), arguments)
        assert result.ok is False
        assert result.error is not None
        assert result.side_effect is SideEffect.NONE

    async def test_an_ungranted_context_fails_the_call_not_the_process(
        self, tmp_path: Path
    ) -> None:
        ctx = ImageContext(tmp_path, granted=frozenset())
        settings = resolve_settings({})
        tool = ImageGenerateTool(ctx, settings, ImageStore(tmp_path / "images"))
        result = await tool.execute(invocation({"prompt": "a cat"}), ManualCancel())
        assert result.ok is False
        assert result.error is not None
        assert result.error.code is ErrorCode.PERMISSION_DENIED

    async def test_cancellation_at_the_entry_touches_nothing(self, tmp_path: Path) -> None:
        backend = Backend()
        tool = _tool(tmp_path, backend)
        cancel = ManualCancel()
        cancel.request()
        result = await tool.execute(invocation({"prompt": "a cat"}), cancel)
        assert result.ok is False
        assert backend.requests == []
        assert result.side_effect is SideEffect.NONE

    async def test_the_api_key_never_leaks_into_an_error(self, tmp_path: Path) -> None:
        """哨兵长得像密钥，否则「没泄漏」可能只是因为它压根不匹配脱敏形状。"""
        sentinel = "sk-imageplugin0123456789abcdef"
        backend = Backend(httpx.Response(400, json={"error": {"message": sentinel}}))
        result = await _run(
            tmp_path, backend, {"prompt": "a cat"}, secrets={"api_key": sentinel}
        )
        assert result.error is not None
        assert sentinel not in repr(result.error)
        assert sentinel not in result.content


class TestManifest:
    def test_it_declares_exactly_the_tool_it_registers(self) -> None:
        assert {(d.kind, d.name) for d in MANIFEST.capabilities} == {
            (CapabilityKind.TOOL, GENERATE_TOOL)
        }

    def test_it_does_not_declare_a_priority(self) -> None:
        for decl in MANIFEST.capabilities:
            assert "priority" not in decl.model_fields_set

    def test_it_declares_net_fs_write_and_one_named_secret(self) -> None:
        """`fs:write` 是因为 `FileAccess` 没有 `write_bytes`——如实声明而不是绕道。"""
        assert {(p.kind, p.target) for p in MANIFEST.permissions} == {
            (PermissionKind.NET, ""),
            (PermissionKind.FS_WRITE, ""),
            (PermissionKind.SECRET, "api_key"),
        }
        assert all(p.reason.strip() for p in MANIFEST.permissions)

    def test_the_tool_is_not_read_only(self) -> None:
        """它写文件、花钱，而且同一个 prompt 两次调用的产物不同。"""
        spec = generate_spec()
        assert spec.read_only is False
        assert spec.risk is RiskLevel.MUTATING

    def test_the_config_schema_forbids_unknown_keys(self) -> None:
        assert CONFIG_SCHEMA["additionalProperties"] is False

    def test_the_config_schema_matches_what_settings_accepts(self) -> None:
        import jsonschema

        jsonschema.Draft202012Validator.check_schema(CONFIG_SCHEMA)
        sample: dict[str, JsonValue] = {
            "provider": "openrouter",
            "base_url": "https://gw.example/v1",
            "model": "m",
            "size": "512x512",
            "response_format": "b64_json",
            "max_count": 2,
            "timeout_ms": 1000,
            "max_result_chars": 500,
            "dir": "renders",
            "extra_body": {"quality": "high"},
        }
        jsonschema.validate(sample, CONFIG_SCHEMA)
        assert resolve_settings(sample).provider == "openrouter"


class _RecordingApi:
    """只记录注册动作的最小 `NucleaAPI` 替身。"""

    def __init__(self, ctx: ImageContext) -> None:
        self._ctx = ctx
        self.tools: list[tuple[ToolSpec, ToolHandler]] = []

    @property
    def ctx(self) -> ImageContext:
        return self._ctx

    def register_tool(self, spec: ToolSpec, handler: ToolHandler) -> None:
        self.tools.append((spec, handler))


class TestRegistration:
    def test_register_covers_every_declaration(self, tmp_path: Path) -> None:
        ctx = ImageContext(tmp_path)
        api = _RecordingApi(ctx)
        register(api, ctx)  # pyright: ignore[reportArgumentType]
        assert {spec.name for spec, _ in api.tools} == {
            decl.name for decl in MANIFEST.capabilities
        }

    def test_setup_creates_no_directory(self, tmp_path: Path) -> None:
        """为一个可能永远不被调用的工具建目录，是在没人要求的时候动用户的磁盘。"""
        ctx = ImageContext(tmp_path)
        register(_RecordingApi(ctx), ctx)  # pyright: ignore[reportArgumentType]
        assert list(tmp_path.iterdir()) == []

    def test_a_broken_config_stops_registration_entirely(self, tmp_path: Path) -> None:
        ctx = ImageContext(tmp_path, config={"provider": "midjourney"})
        with pytest.raises(NucleaError) as caught:
            register(_RecordingApi(ctx), ctx)  # pyright: ignore[reportArgumentType]
        assert caught.value.code is ErrorCode.CONFIG_INVALID


class TestGenerateToolContract(ToolContract):
    """SDK 的通用工具契约。基类**不 import pytest**，只是普通类 + `assert`。"""

    def make_tool(self) -> tuple[ToolSpec, ToolHandler]:
        # 契约基类不带夹具，因此自己找一个可写目录。用 `ImageStore` 的真实落盘路径，
        # 因为契约要验的正是「一次真实调用的形状」。
        import tempfile

        root = Path(tempfile.mkdtemp(prefix="nm-image-contract-"))
        ctx = ImageContext(root)
        settings = resolve_settings({})
        store = ImageStore(image_directory(ctx, settings))
        backend = Backend(openai_response())
        return generate_spec(), ImageGenerateTool(
            ctx, settings, store, transport=backend.transport
        )

    def valid_arguments(self) -> dict[str, JsonValue]:
        return {"prompt": "a cat"}

    def invalid_arguments(self) -> dict[str, JsonValue]:
        return {"prompt": 42}
