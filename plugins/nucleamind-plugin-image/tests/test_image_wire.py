"""`wire.py` 与 `settings.py` 的纯函数用例：请求怎么拼、响应怎么读、配置怎么校验。

一个 IO 都不做，因此每条规则都能逐字节钉住。
"""

from __future__ import annotations

import base64
import json

import pytest
from _image_fakes import PNG_B64, PNG_BYTES, PNG_DATA_URL
from nucleamind_plugin_image.settings import (
    DEFAULT_MODEL,
    DEFAULT_PROVIDER,
    PROVIDERS,
    ImageSettings,
    resolve_settings,
)
from nucleamind_plugin_image.wire import (
    OPENAI_DEFAULT_BASE_URL,
    OPENROUTER_DEFAULT_BASE_URL,
    build_request,
    check_status,
    decode_data_url,
    extension_for,
    parse_response,
)

from nucleamind.contracts import ErrorCode, JsonValue, NucleaError


class TestSettings:
    def test_an_empty_block_is_valid(self) -> None:
        settings = resolve_settings({})
        assert (settings.provider, settings.model) == (DEFAULT_PROVIDER, DEFAULT_MODEL)

    def test_an_unknown_provider_lists_the_choices(self) -> None:
        with pytest.raises(NucleaError) as caught:
            resolve_settings({"provider": "midjourney"})
        assert caught.value.code is ErrorCode.CONFIG_INVALID
        assert caught.value.detail["choices"] == list(PROVIDERS)

    def test_response_format_is_an_enum(self) -> None:
        with pytest.raises(NucleaError):
            resolve_settings({"response_format": "png"})

    def test_true_is_not_a_positive_integer(self) -> None:
        with pytest.raises(NucleaError):
            resolve_settings({"max_count": True})

    def test_extra_body_rejects_nested_objects(self) -> None:
        """放行嵌套对象等于邀请用户把整个请求体重写一遍。"""
        with pytest.raises(NucleaError):
            resolve_settings({"extra_body": {"a": {"b": 1}}})

    def test_extra_body_accepts_scalars_and_arrays(self) -> None:
        settings = resolve_settings({"extra_body": {"quality": "high", "tags": [1, 2]}})
        assert settings.extra_body == {"quality": "high", "tags": [1, 2]}

    @pytest.mark.parametrize(
        "config", [{"provider": 1}, {"model": []}, {"timeout_ms": 0}, {"extra_body": "x"}]
    )
    def test_rejected_shapes(self, config: dict[str, JsonValue]) -> None:
        with pytest.raises(NucleaError):
            resolve_settings(config)


class TestBuildRequest:
    def test_openai_hits_the_images_endpoint(self) -> None:
        request = build_request(resolve_settings({}), "a cat", 2, "k")
        assert request.url == f"{OPENAI_DEFAULT_BASE_URL}/images/generations"
        assert request.headers["Authorization"] == "Bearer k"
        assert request.json_body == {"model": DEFAULT_MODEL, "prompt": "a cat", "n": 2}

    def test_empty_optional_fields_are_not_sent(self) -> None:
        """`gpt-image-1` 会**拒绝** `response_format`；留空即不发是这条设计的全部意义。"""
        body = build_request(resolve_settings({}), "a cat", 1, "k").json_body
        assert "size" not in body
        assert "response_format" not in body

    def test_configured_optional_fields_are_sent(self) -> None:
        settings = resolve_settings({"size": "512x512", "response_format": "b64_json"})
        body = build_request(settings, "a cat", 1, "k").json_body
        assert body["size"] == "512x512"
        assert body["response_format"] == "b64_json"

    def test_extra_body_is_merged_last(self) -> None:
        """它是「不长厂商特例表」的兜底，因此必须压得过我们自己填的值。"""
        settings = resolve_settings({"size": "512x512", "extra_body": {"size": "1024x1024"}})
        assert build_request(settings, "a cat", 1, "k").json_body["size"] == "1024x1024"

    def test_openrouter_goes_through_chat_completions(self) -> None:
        settings = resolve_settings({"provider": "openrouter"})
        request = build_request(settings, "a cat", 1, "k")
        assert request.url == f"{OPENROUTER_DEFAULT_BASE_URL}/chat/completions"
        assert request.json_body["modalities"] == ["image", "text"]
        assert request.json_body["stream"] is False

    def test_base_url_overrides_the_official_endpoint(self) -> None:
        settings = resolve_settings({"base_url": "http://127.0.0.1:11434/v1/"})
        assert build_request(settings, "a cat", 1, "k").url == (
            "http://127.0.0.1:11434/v1/images/generations"
        )


class TestParseResponse:
    def test_openai_base64(self) -> None:
        body = json.dumps({"data": [{"b64_json": PNG_B64}]}).encode()
        sources = parse_response(resolve_settings({}), body)
        assert sources[0].inline == PNG_BYTES
        assert sources[0].needs_download is False

    def test_openai_url_is_left_for_download(self) -> None:
        body = json.dumps({"data": [{"url": "https://cdn.example/a.png"}]}).encode()
        sources = parse_response(resolve_settings({}), body)
        assert sources[0].needs_download is True
        assert sources[0].url == "https://cdn.example/a.png"

    def test_a_data_url_in_the_url_field_is_unwrapped_on_the_spot(self) -> None:
        """自建网关常这么回。当场拆开省一次往返。"""
        body = json.dumps({"data": [{"url": PNG_DATA_URL}]}).encode()
        sources = parse_response(resolve_settings({}), body)
        assert sources[0].inline == PNG_BYTES

    def test_openrouter_reads_the_nested_images(self) -> None:
        settings = resolve_settings({"provider": "openrouter"})
        body = json.dumps(
            {"choices": [{"message": {"images": [{"image_url": {"url": PNG_DATA_URL}}]}}]}
        ).encode()
        assert parse_response(settings, body)[0].inline == PNG_BYTES

    def test_no_images_is_an_error_not_an_empty_result(self) -> None:
        """用户花了钱、等了几十秒；返回「没有图」只会让模型再试一次。"""
        with pytest.raises(NucleaError) as caught:
            parse_response(resolve_settings({}), b'{"data": []}')
        assert caught.value.code is ErrorCode.EXTERNAL_HTTP_REQUEST
        assert caught.value.retryable is False

    def test_broken_base64_is_reported_not_silently_dropped(self) -> None:
        body = json.dumps({"data": [{"b64_json": "!!!not base64!!!"}]}).encode()
        with pytest.raises(NucleaError):
            parse_response(resolve_settings({}), body)

    def test_non_json_is_an_error(self) -> None:
        with pytest.raises(NucleaError):
            parse_response(resolve_settings({}), b"<html>gateway error</html>")


class TestDataUrl:
    def test_round_trip(self) -> None:
        data, media_type = decode_data_url(PNG_DATA_URL)
        assert (data, media_type) == (PNG_BYTES, "image/png")

    @pytest.mark.parametrize(
        "value",
        [
            "https://example.com/a.png",
            "data:image/png,notbase64",
            "data:image/png;base64,",
        ],
    )
    def test_rejected_forms(self, value: str) -> None:
        with pytest.raises(NucleaError):
            decode_data_url(value)

    def test_a_missing_media_type_falls_back_to_png(self) -> None:
        encoded = base64.b64encode(b"x").decode("ascii")
        assert decode_data_url(f"data:;base64,{encoded}")[1] == "image/png"


class TestExtensions:
    @pytest.mark.parametrize(
        ("media_type", "expected"),
        [
            ("image/png", ".png"),
            ("image/jpeg", ".jpg"),
            ("image/webp", ".webp"),
            ("IMAGE/PNG; charset=binary", ".png"),
        ],
    )
    def test_known_types(self, media_type: str, expected: str) -> None:
        assert extension_for(media_type) == expected

    def test_an_unknown_type_is_not_guessed(self) -> None:
        """一个扩展名错了的文件比一个叫不出名字的文件更难查。"""
        assert extension_for("image/x-nonesuch") == ".bin"


class TestCheckStatus:
    def test_2xx_passes(self) -> None:
        check_status("openai", 200)

    @pytest.mark.parametrize("status", [401, 403])
    def test_auth_failures_point_at_the_credential(self, status: int) -> None:
        with pytest.raises(NucleaError) as caught:
            check_status("openai", status)
        assert caught.value.code is ErrorCode.CONFIG_SECRET_MISSING

    @pytest.mark.parametrize("status", [429, 500])
    def test_transient_failures_are_retryable(self, status: int) -> None:
        with pytest.raises(NucleaError) as caught:
            check_status("openai", status)
        assert caught.value.retryable is True

    def test_the_response_body_never_reaches_the_detail(self) -> None:
        """那段自由文本会回显 prompt，也可能带着被 echo 回来的凭据。"""
        with pytest.raises(NucleaError) as caught:
            check_status("openai", 400)
        assert set(caught.value.detail) == {"provider", "status"}


def test_settings_is_frozen() -> None:
    """设置是不可变的：同一份对象会被并发调用共享（`Concurrency.PARALLEL`）。"""
    with pytest.raises(AttributeError):
        ImageSettings().model = "x"  # pyright: ignore[reportAttributeAccessIssue]
