"""`image` 插件用例的替身与工厂。**模块名带插件前缀**是刻意的。

`testpaths` 一次收集整个 `plugins/`，而 pytest 按模块名去重：两个插件各有一个
`_fakes.py` 时，先导入的会顶掉后一个，另一棵测试树整体 `ImportError`。
**单独跑各自目录看不出来，跑全量才炸**（`D34` 就是这么发现的）。

职责：一个带 `state_dir` 的 `PluginContext`、一个 `ctx.fs` 写入面的替身、
一个记录请求的 `httpx` 处理器，以及构造 `ToolInvocation` 的小工厂。
不负责：断言（在各 `test_image_*.py` 里）。
"""

from __future__ import annotations

import base64
import json
from collections.abc import Mapping
from pathlib import Path

import httpx

from nucleamind.contracts import JsonValue, ToolCall, ToolInvocation
from nucleamind.sdk.testing import FakePluginContext, make_correlation

#: 一张真实的 1×1 PNG。用真图而不是 `b"fake"`：媒体类型与扩展名的判定要有意义。
PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)
PNG_B64 = base64.b64encode(PNG_BYTES).decode("ascii")
PNG_DATA_URL = f"data:image/png;base64,{PNG_B64}"


class ImageContext(FakePluginContext):
    """带真实 `state_dir` 的上下文。"""

    def __init__(
        self,
        state_dir: Path,
        *,
        config: Mapping[str, JsonValue] | None = None,
        secrets: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(
            "image",
            config=config,
            state_dir=state_dir,
            secrets=secrets if secrets is not None else {"api_key": "sk-image-test-key-1234"},
        )


class FakeWorkspace:
    """`ctx.fs` 写入面的替身（`D47`）。

    **为什么不是 `FakePluginContext.fs`**：那个属性按设计抛 `NotImplementedError`，
    而 `sdk.testing` 是冻结表面——为一个插件的方便去改它的语义不划算。插件那边的
    `FileWriter` 窄到只有一个方法，因此这个替身只有几行。

    真的写盘（`tmp_path`）：storage 的正事就是「字节真的落下去了」，一个只记账的替身
    证明不了它。路径按 POSIX 相对路径解释，与 `ctx.fs` 的约定一致。
    """

    def __init__(self, root: Path) -> None:
        self.root = root
        self.writes: list[str] = []

    async def write_bytes(self, path: str, data: bytes) -> None:
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        self.writes.append(path)


class Backend:
    """按脚本回响应的 `httpx` 处理器，同时记录收到的请求。"""

    def __init__(self, *responses: httpx.Response) -> None:
        self._responses = list(responses)
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if not self._responses:
            raise AssertionError("Backend 的脚本已经用完，但又来了一次请求")
        return self._responses.pop(0)

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self)

    def body_of(self, index: int) -> Mapping[str, JsonValue]:
        payload: Mapping[str, JsonValue] = json.loads(self.requests[index].content)
        return payload


def openai_response(*, count: int = 1, url: str = "") -> httpx.Response:
    """`/images/generations` 的回复。给了 `url` 就回 URL 形态，否则回 base64。"""
    if url:
        return httpx.Response(200, json={"data": [{"url": url} for _ in range(count)]})
    return httpx.Response(200, json={"data": [{"b64_json": PNG_B64} for _ in range(count)]})


def openrouter_response(count: int = 1) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "choices": [
                {
                    "message": {
                        "content": "画好了",
                        "images": [
                            {"image_url": {"url": PNG_DATA_URL}} for _ in range(count)
                        ],
                    }
                }
            ]
        },
    )


def png_download() -> httpx.Response:
    return httpx.Response(200, content=PNG_BYTES, headers={"content-type": "image/png"})


def invocation(arguments: Mapping[str, JsonValue]) -> ToolInvocation:
    return ToolInvocation(
        call=ToolCall(call_id="call-1", name="image.generate", arguments=dict(arguments)),
        correlation=make_correlation(),
        timeout_ms=5_000,
    )
