"""`image.generate` 的执行体。本包唯一碰网络的模块。

职责：把一次调用翻成一次后端请求、把回来的图落盘、构造 `ToolResult`。
不负责：线格式（`wire.py`）、落盘细节（`storage.py`）、读配置（`settings.py`）。

**直接用 httpx 而不是 `ctx.net`**：图像端点由**运维配置**（`base_url` 要能指到本地
ollama、自建网关或代理），而 `ctx.net` 的 SSRF 守卫按设计拒绝私有地址与回环。
与内建 `model_openai` 要连本地 vLLM / Ollama 是同一条先例：门面能力不足时，如实声明
直接使用适合该端点的客户端。模型在这里**决定不了任何地址**，它只给 prompt。

**`side_effect` 三档判定只在 `execute()` 一处**（`builtins/tools_shell/executor.py::_fold`
的同一条判据）：落盘**之前**失败（参数非法 / 凭据缺失 / 请求失败 / 响应读不懂）→ `NONE`；
写成功 → `OCCURRED`。**本工具不产出 `UNKNOWN`**——`storage.py` 的替换成功之后没有可失败
的步骤，而替换之前一个字节都没落到目标路径上。
"""

from __future__ import annotations

import time
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Final

from nucleamind.contracts import (
    ArtifactRef,
    AttachmentRef,
    CancelSignal,
    ErrorCode,
    JsonValue,
    NucleaError,
    RiskLevel,
    SideEffect,
    ToolInvocation,
    ToolResult,
    ToolSpec,
    TrustLevel,
)
from nucleamind.sdk import PluginContext

from .settings import SECRET_NAME, ImageSettings
from .storage import ImageStore, SavedImage
from .wire import ImageSource, build_request, check_status, parse_response

if TYPE_CHECKING:  # pragma: no cover - 仅类型
    import httpx

__all__ = ["GENERATE_TOOL", "ImageGenerateTool", "generate_spec"]

GENERATE_TOOL: Final = "image.generate"

#: 下载一张已生成图的超时。与生成本身分开：生成要等模型跑，下载只是取一个已经存在的
#: 对象，用同一个上限意味着一次卡住的下载能把整次调用拖满两分钟。
_DOWNLOAD_TIMEOUT_MS: Final = 60_000

_TOO_MANY: Final = "请求的张数超过了配置上限。"
_DOWNLOAD_FAILED: Final = "取回生成的图像失败。"


def generate_spec() -> ToolSpec:
    """`image.generate` 的声明。"""
    return ToolSpec(
        name=GENERATE_TOOL,
        description=(
            "按文字描述生成图像并保存到本地，返回文件路径。"
            "会调用外部收费接口并写入文件。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "对要生成的图像的描述。"},
                "count": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "生成几张，不给则生成一张。",
                },
            },
            "required": ["prompt"],
            "additionalProperties": False,
        },
        # 不是只读：它写文件、花钱，而且同一个 prompt 两次调用的产物不同。
        read_only=False,
        risk=RiskLevel.MUTATING,
    )


class ImageGenerateTool:
    """生成图像并落盘。"""

    __slots__ = ("_ctx", "_settings", "_store", "_transport")

    def __init__(
        self,
        ctx: PluginContext,
        settings: ImageSettings,
        store: ImageStore,
        *,
        transport: "httpx.AsyncBaseTransport | None" = None,
    ) -> None:
        self._ctx = ctx
        self._settings = settings
        self._store = store
        # 可注入的传输层：用例全部走 `httpx.MockTransport`，一个 socket 都不开。
        self._transport = transport

    async def execute(self, invocation: ToolInvocation, cancel: CancelSignal) -> ToolResult:
        """**约定不抛**。逸出的异常会被 Kernel 记成 `side_effect=UNKNOWN`，而本工具
        总是知道自己写没写盘（见模块 docstring）。

        **取消语义**：入口检查一次，落盘之前再检查一次。已经落盘的图**不会被删掉**——
        取消不是回滚，而那些字节是用户已经付过钱的。
        """
        started = time.perf_counter()
        try:
            cancel.raise_if_requested()
            saved = await self._run(invocation, cancel)
        except NucleaError as error:
            return _failure(invocation, error, started, self._settings.max_result_chars)
        return _success(invocation, saved, started, self._settings.max_result_chars)

    async def _run(
        self, invocation: ToolInvocation, cancel: CancelSignal
    ) -> tuple[SavedImage, ...]:
        arguments = invocation.call.arguments
        _reject_unknown(arguments, {"prompt", "count"})
        prompt = _require_str(arguments, "prompt")
        count = _optional_int(arguments, "count", 1)
        if count > self._settings.max_count:
            raise NucleaError(
                ErrorCode.INPUT_MALFORMED,
                _TOO_MANY,
                detail={"requested": count, "max_count": self._settings.max_count},
            )

        sources = await self._generate(prompt, count)
        cancel.raise_if_requested()
        saved: list[SavedImage] = []
        for source in sources[:count]:
            data, media_type = await self._materialise(source)
            saved.append(await self._store.save(data, media_type))
        return tuple(saved)

    async def _generate(self, prompt: str, count: int) -> tuple[ImageSource, ...]:
        import httpx  # noqa: PLC0415 - 惰性：不生成图的实例不该为它付导入开销

        settings = self._settings
        request = build_request(settings, prompt, count, self._credential())
        async with httpx.AsyncClient(
            transport=self._transport, timeout=settings.timeout_ms / 1000
        ) as client:
            response = await _send(
                client, "POST", request.url, headers=request.headers, json=dict(request.json_body)
            )
        check_status(settings.provider, response.status_code)
        return parse_response(settings, response.content)

    async def _materialise(self, source: ImageSource) -> tuple[bytes, str]:
        """把一个来源变成字节。内联的直接返回，URL 的去取一次。"""
        if source.inline is not None:
            return source.inline, source.media_type
        import httpx  # noqa: PLC0415 - 同上

        async with httpx.AsyncClient(
            transport=self._transport, timeout=_DOWNLOAD_TIMEOUT_MS / 1000
        ) as client:
            response = await _send(client, "GET", source.url)
        if not 200 <= response.status_code < 300:
            raise NucleaError(
                ErrorCode.EXTERNAL_HTTP_REQUEST,
                _DOWNLOAD_FAILED,
                detail={"status": response.status_code},
                retryable=response.status_code >= 500,
            )
        media_type = response.headers.get("content-type", source.media_type)
        return response.content, media_type.split(";", 1)[0].strip() or source.media_type

    def _credential(self) -> str:
        """取凭据。

        **每次调用都取一遍**：`ctx.secret()` 只是查一次已经在内存里的配置 + 环境变量，
        缓存住它意味着用户改了变量要重启实例。缺失时抛 `CONFIG_SECRET_MISSING`，
        由 `execute()` 折成这一次调用的失败——而那时**一个字节都还没落盘**。
        """
        return self._ctx.secret(SECRET_NAME).reveal()


# ------------------------------------------------------------------------ 结果构造


def _success(
    invocation: ToolInvocation, saved: Sequence[SavedImage], started: float, limit: int
) -> ToolResult:
    lines = [f"已生成 {len(saved)} 张图像："]
    lines.extend(f"{index}. {item.locator}" for index, item in enumerate(saved, 1))
    content = "\n".join(lines)
    artifacts: tuple[ArtifactRef, ...] = tuple(item.artifact for item in saved)
    # 只有 workspace 落点交得出附件（`AttachmentRef` 拒绝绝对路径），因此这里可能是空的
    # ——那不是失败，是运维把 `dir` 配成了绝对路径。正文里的路径仍然在。
    attachments: tuple[AttachmentRef, ...] = tuple(
        item.attachment for item in saved if item.attachment is not None
    )
    data: Mapping[str, JsonValue] = {
        "count": len(saved),
        "paths": [item.locator for item in saved],
        "bytes": [item.size_bytes for item in saved],
    }
    return ToolResult(
        call_id=invocation.call.call_id,
        ok=True,
        content=content[:limit],
        truncated=len(content) > limit,
        # 文件真的写下去了，而且写成功之后没有可失败的步骤。
        side_effect=SideEffect.OCCURRED,
        data=data,
        artifacts=artifacts,
        attachments=attachments,
        duration_ms=_elapsed_ms(started),
        # 正文是本工具自己的话（几行「已生成 N 张图像」加落盘路径）。**图像字节本身
        # 从不进上下文**，它们经 `artifacts` / `attachments` 引用（`D42`、`D47`）。
        trust=TrustLevel.SYSTEM,
    )


def _failure(
    invocation: ToolInvocation, error: NucleaError, started: float, limit: int
) -> ToolResult:
    message = error.user_message
    return ToolResult(
        call_id=invocation.call.call_id,
        ok=False,
        content=message[:limit],
        truncated=len(message) > limit,
        # 全部失败路径都在落盘**之前**（见模块 docstring）。
        side_effect=SideEffect.NONE,
        error=error,
        duration_ms=_elapsed_ms(started),
        trust=TrustLevel.SYSTEM,
    )


# ------------------------------------------------------------------------------ 参数


async def _send(
    client: "httpx.AsyncClient",
    method: str,
    url: str,
    *,
    headers: Mapping[str, str] | None = None,
    json: Mapping[str, JsonValue] | None = None,
) -> "httpx.Response":
    """发一次请求，把 httpx 的异常折成 `NucleaError`。"""
    import httpx  # noqa: PLC0415 - 同上

    try:
        return await client.request(method, url, headers=dict(headers or {}), json=json)
    except httpx.TimeoutException as error:
        raise NucleaError(
            ErrorCode.TIMEOUT_HTTP_REQUEST, "图像请求超时。", detail={"method": method}
        ) from error
    except httpx.HTTPError as error:
        raise NucleaError(
            ErrorCode.EXTERNAL_HTTP_REQUEST,
            "图像请求失败。",
            # 只放异常**类型名**，不放消息——第三方库的异常文本可能带上完整 URL，
            # 而自建网关的 URL 里可能有 query string 形态的凭据。
            detail={"method": method, "cause": type(error).__name__},
            retryable=True,
        ) from error


def _reject_unknown(arguments: Mapping[str, JsonValue], allowed: set[str]) -> None:
    unknown = sorted(set(arguments) - allowed)
    if unknown:
        raise NucleaError(
            ErrorCode.INPUT_MALFORMED,
            "出现了未知参数。",
            detail={"unknown": unknown, "allowed": sorted(allowed)},
        )


def _require_str(arguments: Mapping[str, JsonValue], key: str) -> str:
    value = arguments.get(key)
    if not isinstance(value, str) or not value.strip():
        raise NucleaError(
            ErrorCode.INPUT_MALFORMED,
            "缺少必填参数或类型不对（应为非空字符串）。",
            detail={"argument": key, "actual_type": type(value).__name__},
        )
    return value.strip()


def _optional_int(arguments: Mapping[str, JsonValue], key: str, default: int) -> int:
    value = arguments.get(key)
    if value is None:
        return default
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise NucleaError(
            ErrorCode.INPUT_MALFORMED,
            "参数类型不对或超出范围（应为正整数）。",
            detail={"argument": key, "actual_type": type(value).__name__},
        )
    return value


def _elapsed_ms(started: float) -> int:
    return max(0, int((time.perf_counter() - started) * 1000))
