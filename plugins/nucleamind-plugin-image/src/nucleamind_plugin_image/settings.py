"""配置解析与一次性校验（`CFG-002`：插件只看得见自己那一块）。

职责：把 `plugins.image.config` 变成一个不可变设置对象，并在 `setup()` 里把能查的错一次查完。
不负责：读取凭据（`tool.py`）、发请求（`tool.py`）、拼包与解包（`wire.py`）。

**这里刻意没有「按模型名决定发哪些字段」的表。** 参考实现按模型 slug 决定尺寸参数名、
按模型名判断支不支持 `response_format`；`D19` 拒过 `max_tokens_field` slug 表、`D32` 拒过
四张版本 gating 表，理由一个字没变：**表只会越滚越大，而用户换一个新模型要等我们发版**。
这里的对应物是三个显式配置项——`size` / `response_format` / `extra_body`，
留空即**不发这个字段**。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Final

from nucleamind.contracts import ErrorCode, JsonValue, NucleaError

__all__ = [
    "DEFAULT_MAX_COUNT",
    "DEFAULT_MODEL",
    "DEFAULT_PROVIDER",
    "IMAGE_DIR_NAME",
    "PROVIDERS",
    "SECRET_NAME",
    "ImageSettings",
    "resolve_settings",
]

#: 凭据名。固定常量而不是可配置项——manifest 的 `PermissionDecl(SECRET, "api_key")` 声明的
#: 就是这个名字，做成可配置会让那条声明变成一句谎话（`D19` 的同一条理由）。
SECRET_NAME: Final = "api_key"

#: 支持的后端。两个形状差异大的代表：`openai` 是专用的图像端点，`openrouter` 是把图放在
#: chat 响应里。第三家多半能用 `openai` + `base_url` 接上。
PROVIDERS: Final[tuple[str, ...]] = ("openai", "openrouter")

DEFAULT_PROVIDER: Final = "openai"
DEFAULT_MODEL: Final = "gpt-image-1"
DEFAULT_MAX_COUNT: Final = 4

#: workspace 下的默认子目录（`D47` 起；在它之前是 `ctx.state_dir` 下的子目录名）。
#: 用 `/` 拼是因为它要同时充当 `ctx.fs` 的路径与 `AttachmentRef` 的 locator。
IMAGE_DIR_NAME: Final = "artifacts/images"

_DEFAULT_TIMEOUT_MS: Final = 120_000
_DEFAULT_MAX_RESULT_CHARS: Final = 4_000

_NOT_AN_OBJECT: Final = "这个配置项必须是对象。"
_NOT_A_STRING: Final = "这个配置项必须是字符串。"
_NOT_A_POSITIVE_INT: Final = "这个配置项必须是正整数。"
_UNKNOWN_PROVIDER: Final = "未知的图像后端。"
_BAD_RESPONSE_FORMAT: Final = "response_format 只能是 b64_json 或 url。"
_BAD_EXTRA_BODY: Final = "extra_body 的每个值都必须是 JSON 标量或数组。"


@dataclass(frozen=True, slots=True)
class ImageSettings:
    """本插件的全部设置。"""

    provider: str = DEFAULT_PROVIDER
    base_url: str = ""
    model: str = DEFAULT_MODEL
    size: str = ""
    response_format: str = ""
    max_count: int = DEFAULT_MAX_COUNT
    timeout_ms: int = _DEFAULT_TIMEOUT_MS
    max_result_chars: int = _DEFAULT_MAX_RESULT_CHARS
    directory: str = ""
    extra_body: Mapping[str, JsonValue] = field(default_factory=dict[str, JsonValue])


def resolve_settings(config: Mapping[str, JsonValue]) -> ImageSettings:
    """解析 `plugins.image.config`。**异常约定**：任何问题一律 `CONFIG_INVALID` 并带键路径。

    manifest 的 `config_schema` 已经在阶段 A 校验过**形状**，这里做的是它表达不了的那些：
    枚举取值要给出「你可以写哪几个」、以及跨字段的一致性。
    """
    provider = _string(config, "provider", DEFAULT_PROVIDER).strip().lower()
    if provider not in PROVIDERS:
        raise _invalid(
            _UNKNOWN_PROVIDER, "provider", provider=provider, choices=list(PROVIDERS)
        )
    response_format = _string(config, "response_format", "").strip()
    if response_format and response_format not in {"b64_json", "url"}:
        raise _invalid(_BAD_RESPONSE_FORMAT, "response_format", value=response_format)
    return ImageSettings(
        provider=provider,
        base_url=_string(config, "base_url", "").strip().rstrip("/"),
        model=_string(config, "model", DEFAULT_MODEL).strip() or DEFAULT_MODEL,
        size=_string(config, "size", "").strip(),
        response_format=response_format,
        max_count=_positive_int(config, "max_count", DEFAULT_MAX_COUNT),
        timeout_ms=_positive_int(config, "timeout_ms", _DEFAULT_TIMEOUT_MS),
        max_result_chars=_positive_int(config, "max_result_chars", _DEFAULT_MAX_RESULT_CHARS),
        directory=_string(config, "dir", "").strip(),
        extra_body=_extra_body(config),
    )


def _extra_body(config: Mapping[str, JsonValue]) -> Mapping[str, JsonValue]:
    """透传给后端的额外字段。

    它是「不长厂商特例表」的兜底：某家需要一个我们没听说过的字段时，用户自己写上去，
    不必等我们发版。**只接受标量与数组**——嵌套对象在这里没有已知用例，而放行它等于
    邀请用户把整个请求体重写一遍。
    """
    value = config.get("extra_body")
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise _invalid(_NOT_AN_OBJECT, "extra_body")
    result: dict[str, JsonValue] = {}
    for key, item in value.items():
        if isinstance(item, Mapping):
            raise _invalid(_BAD_EXTRA_BODY, f"extra_body.{key}")
        result[key] = item
    return result


def _string(config: Mapping[str, JsonValue], key: str, default: str) -> str:
    value = config.get(key)
    if value is None:
        return default
    if not isinstance(value, str):
        raise _invalid(_NOT_A_STRING, key)
    return value


def _positive_int(config: Mapping[str, JsonValue], key: str, default: int) -> int:
    value = config.get(key)
    if value is None:
        return default
    # `True` 是 `int` 的实例，放行它会让 `timeout_ms: true` 变成 1 毫秒。
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise _invalid(_NOT_A_POSITIVE_INT, key)
    return value


def _invalid(message: str, key: str, **detail: object) -> NucleaError:
    return NucleaError(
        ErrorCode.CONFIG_INVALID,
        message,
        detail={"key": f"plugins.image.config.{key}", **detail},
    )
