"""线格式：怎么拼请求、怎么从响应里把图取出来。全是纯函数。

职责：`ImageSettings` + prompt → 一个 `ImageRequest`；响应字节 → 一组 `ImageSource`。
不负责：发请求与下载（`tool.py`）、落盘（`storage.py`）、读配置（`settings.py`）。

**两个后端的响应形状差得很远**，因此各写各的（`AGENTS.md` 原则 5）：

- `openai` 的 `/images/generations` 回 `{"data": [{"b64_json": …} | {"url": …}]}`。
  两种都要支持：`gpt-image-1` 恒回 base64，`dall-e-3` 默认回一个有期限的 URL。
- `openrouter` 走 `/chat/completions`，图挂在 `choices[].message.images[].image_url.url`
  上，是一个 `data:` URL。

**`ImageSource` 刻意分「内联字节」与「待下载 URL」两态**，而不是在这里就把 URL 拉下来：
下载是 IO，放进纯函数会让这一层再也没法在没有事件循环的情况下逐字节钉住。
"""

from __future__ import annotations

import base64
import binascii
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Final

from nucleamind.contracts import ErrorCode, JsonValue, NucleaError

from .settings import ImageSettings

__all__ = [
    "OPENAI_DEFAULT_BASE_URL",
    "OPENROUTER_DEFAULT_BASE_URL",
    "ImageRequest",
    "ImageSource",
    "build_request",
    "check_status",
    "decode_data_url",
    "extension_for",
    "parse_response",
]

OPENAI_DEFAULT_BASE_URL: Final = "https://api.openai.com/v1"
OPENROUTER_DEFAULT_BASE_URL: Final = "https://openrouter.ai/api/v1"

#: 媒体类型到扩展名。**认不出来就用 `.bin`**，不猜——一个扩展名错了的文件比一个
#: 叫不出名字的文件更难查。
_EXTENSIONS: Final[Mapping[str, str]] = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
}

#: `data:` URL 之外的默认媒体类型。图像端点不声明类型时按 PNG 处理是行业惯例，
#: 但它是**猜**，因此只在没有别的信息时才用。
_DEFAULT_MEDIA_TYPE: Final = "image/png"

_NO_IMAGES: Final = "后端没有返回任何图像。"
_BAD_JSON: Final = "图像后端返回的不是 JSON 对象。"
_BAD_BASE64: Final = "图像后端返回的 base64 数据解不开。"
_BAD_DATA_URL: Final = "图像后端返回的不是合法的 data: URL。"


@dataclass(frozen=True, slots=True)
class ImageRequest:
    """一次生成请求的完整描述。`tool.py` 照着它发，不做任何补充决定。"""

    url: str
    headers: Mapping[str, str] = field(default_factory=dict)
    json_body: Mapping[str, JsonValue] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ImageSource:
    """一张图的来源：要么已经是字节，要么是一个还要去取的 URL。"""

    inline: bytes | None = None
    url: str = ""
    media_type: str = _DEFAULT_MEDIA_TYPE

    @property
    def needs_download(self) -> bool:
        return self.inline is None


def build_request(settings: ImageSettings, prompt: str, count: int, api_key: str) -> ImageRequest:
    """按后端拼出请求。"""
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    if settings.provider == "openrouter":
        base = settings.base_url or OPENROUTER_DEFAULT_BASE_URL
        body: dict[str, JsonValue] = {
            "model": settings.model,
            "messages": [{"role": "user", "content": prompt}],
            "modalities": ["image", "text"],
            "stream": False,
        }
        if settings.size:
            body["image_config"] = {"image_size": settings.size}
        body.update(settings.extra_body)
        return ImageRequest(url=f"{base}/chat/completions", headers=headers, json_body=body)

    base = settings.base_url or OPENAI_DEFAULT_BASE_URL
    payload: dict[str, JsonValue] = {"model": settings.model, "prompt": prompt, "n": count}
    # 三个「留空即不发」的字段。`gpt-image-1` 会拒绝 `response_format`，而 `dall-e-3`
    # 需要它才回 base64——按模型名判断就是在长一张表，交给配置就没有这个问题。
    if settings.size:
        payload["size"] = settings.size
    if settings.response_format:
        payload["response_format"] = settings.response_format
    payload.update(settings.extra_body)
    return ImageRequest(url=f"{base}/images/generations", headers=headers, json_body=payload)


def parse_response(settings: ImageSettings, body: bytes) -> tuple[ImageSource, ...]:
    """把响应体翻成一组图像来源。

    **异常约定**：读不懂或一张图都没有时抛 `EXTERNAL_HTTP_REQUEST`（不可重试）。
    「一张都没有」是错误而不是空结果——用户花了钱、等了几十秒，返回一句「没有图」
    只会让模型再试一次。
    """
    payload = _json_object(body)
    sources = (
        _openrouter_sources(payload)
        if settings.provider == "openrouter"
        else _openai_sources(payload)
    )
    if not sources:
        raise _external(_NO_IMAGES, provider=settings.provider)
    return sources


def check_status(provider: str, status: int) -> None:
    """非 2xx 折成 `NucleaError`。**异常约定**：只抛，不返回。

    分类与 `builtins/model_openai/faults.py` 同一口径：401/403 指向凭据、
    429 与 5xx 可重试、其余 4xx 不可重试。`detail` 里**不放响应正文**——那段自由文本
    会回显 prompt，也可能带着被 echo 回来的凭据（`D19` 的先例）。
    """
    if 200 <= status < 300:
        return
    detail = {"provider": provider, "status": status}
    if status in {401, 403}:
        raise NucleaError(
            ErrorCode.CONFIG_SECRET_MISSING, "图像后端拒绝了凭据。", detail=detail
        )
    if status == 429 or status >= 500:
        raise NucleaError(
            ErrorCode.EXTERNAL_HTTP_REQUEST,
            "图像后端暂时不可用（限速或服务端故障）。",
            detail=detail,
            retryable=True,
        )
    raise NucleaError(ErrorCode.EXTERNAL_HTTP_REQUEST, "图像后端返回了错误。", detail=detail)


def decode_data_url(value: str) -> tuple[bytes, str]:
    """把 `data:image/png;base64,…` 拆成 `(字节, 媒体类型)`。

    只支持 base64 编码的 `data:` URL：图像不可能以百分号编码的形式出现，而支持一种
    没有生产者的写法只会多一条没人走过的分支。
    """
    if not value.startswith("data:"):
        raise _external(_BAD_DATA_URL)
    head, _, encoded = value[len("data:") :].partition(",")
    if not encoded or "base64" not in head.split(";"):
        raise _external(_BAD_DATA_URL)
    media_type = head.split(";", 1)[0].strip() or _DEFAULT_MEDIA_TYPE
    return _decode_base64(encoded), media_type


def extension_for(media_type: str) -> str:
    """媒体类型对应的扩展名，认不出来给 `.bin`。"""
    return _EXTENSIONS.get(media_type.split(";", 1)[0].strip().lower(), ".bin")


# ------------------------------------------------------------------------------ 内部


def _openai_sources(payload: Mapping[str, JsonValue]) -> tuple[ImageSource, ...]:
    sources: list[ImageSource] = []
    for item in _objects(payload.get("data")):
        encoded = item.get("b64_json")
        if isinstance(encoded, str) and encoded:
            sources.append(ImageSource(inline=_decode_base64(encoded)))
            continue
        url = item.get("url")
        if isinstance(url, str) and url:
            # `data:` URL 也可能出现在这里（自建网关常这么回），先当场拆开省一次往返。
            if url.startswith("data:"):
                data, media_type = decode_data_url(url)
                sources.append(ImageSource(inline=data, media_type=media_type))
            else:
                sources.append(ImageSource(url=url))
    return tuple(sources)


def _openrouter_sources(payload: Mapping[str, JsonValue]) -> tuple[ImageSource, ...]:
    sources: list[ImageSource] = []
    for choice in _objects(payload.get("choices")):
        message = choice.get("message")
        if not isinstance(message, Mapping):
            continue
        for image in _objects(message.get("images")):
            holder = image.get("image_url")
            if not isinstance(holder, Mapping):
                continue
            url = holder.get("url")
            if isinstance(url, str) and url.startswith("data:"):
                data, media_type = decode_data_url(url)
                sources.append(ImageSource(inline=data, media_type=media_type))
    return tuple(sources)


def _json_object(body: bytes) -> Mapping[str, JsonValue]:
    try:
        payload: object = json.loads(body.decode("utf-8", errors="replace"))
    except ValueError as error:
        raise _external(_BAD_JSON) from error
    if not isinstance(payload, Mapping):
        raise _external(_BAD_JSON)
    # boundary: `json.loads` 的产物按定义就是 `JsonValue`；上面那条 isinstance 已经把
    # 顶层收窄到映射，值侧的形状由 `_objects` 逐个判定。
    return payload  # pyright: ignore[reportReturnType]


def _objects(value: JsonValue | None) -> tuple[Mapping[str, JsonValue], ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return ()
    return tuple(item for item in value if isinstance(item, Mapping))


def _decode_base64(encoded: str) -> bytes:
    try:
        return base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as error:
        raise _external(_BAD_BASE64) from error


def _external(message: str, **detail: object) -> NucleaError:
    return NucleaError(ErrorCode.EXTERNAL_HTTP_REQUEST, message, detail=detail)
