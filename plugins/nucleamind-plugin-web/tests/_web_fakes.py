"""`web` 插件用例的替身与工厂。**模块名带插件前缀**是刻意的。

`testpaths` 一次收集整个 `plugins/`，而 pytest 按模块名去重：两个插件各有一个
`_fakes.py` 时，先导入的会顶掉后一个，另一棵测试树整体 `ImportError`。
**单独跑各自目录看不出来，跑全量才炸**（`D34` 就是这么发现的）。

职责：一个实现 `sdk.api.HttpAccess` 的出网替身、一个把它接上去的 `PluginContext`、
以及构造 `ToolInvocation` 的小工厂。
不负责：断言（在各 `test_web_*.py` 里）。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from nucleamind.contracts import (
    ErrorCode,
    JsonValue,
    NucleaError,
    PermissionKind,
    ToolCall,
    ToolInvocation,
)
from nucleamind.sdk import HttpResponse
from nucleamind.sdk.testing import FakePluginContext, make_correlation


class RecordedRequest:
    """`StubNet` 收到的一次请求。"""

    __slots__ = ("body", "headers", "method", "timeout_ms", "url")

    def __init__(
        self,
        method: str,
        url: str,
        headers: Mapping[str, str] | None,
        body: bytes | None,
        timeout_ms: int,
    ) -> None:
        self.method = method
        self.url = url
        self.headers = dict(headers or {})
        self.body = body
        self.timeout_ms = timeout_ms


class StubNet:
    """`HttpAccess` 的替身：按脚本回响应，或抛一个预置的错误。

    **刻意不模拟 SSRF 守卫**：那份判定在 `runtime/access/net.py`，有它自己的用例；
    在这里复刻一遍只会变成第二份会漂移的实现。本插件对守卫的全部依赖就是「调它」，
    而那一条由 `test_web_plugin.py::test_fetch_goes_through_the_guarded_facade` 断言。
    """

    def __init__(
        self,
        responses: Sequence[HttpResponse] = (),
        *,
        error: NucleaError | None = None,
    ) -> None:
        self._responses = list(responses)
        self._error = error
        self.requests: list[RecordedRequest] = []

    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        body: bytes | None = None,
        timeout_ms: int = 30_000,
    ) -> HttpResponse:
        self.requests.append(RecordedRequest(method, url, headers, body, timeout_ms))
        if self._error is not None:
            raise self._error
        if not self._responses:
            raise AssertionError("StubNet 的脚本已经用完，但又来了一次请求")
        return self._responses.pop(0)


class WebContext(FakePluginContext):
    """把 `StubNet` 接上 `ctx.net` 的上下文。

    `FakePluginContext.net` 在授权后抛 `NotImplementedError`（`D16` 时它还没有真实现），
    因此这里覆盖那个 property；**权限判定仍然走基类**，未授予 `net` 时照样
    `PERMISSION_DENIED`。
    """

    def __init__(
        self,
        net: StubNet | None = None,
        *,
        config: Mapping[str, JsonValue] | None = None,
        secrets: Mapping[str, str] | None = None,
        granted: frozenset[PermissionKind] = frozenset(
            {PermissionKind.NET, PermissionKind.SECRET}
        ),
    ) -> None:
        super().__init__("web", config=config, granted=granted, secrets=secrets)
        self.stub_net = net if net is not None else StubNet()

    @property
    def net(self) -> StubNet:
        self._require(PermissionKind.NET)
        return self.stub_net


def html_response(
    body: bytes, *, status: int = 200, content_type: str = "text/html; charset=utf-8"
) -> HttpResponse:
    return HttpResponse(status=status, headers={"content-type": content_type}, body=body)


def invocation(name: str, arguments: Mapping[str, JsonValue]) -> ToolInvocation:
    return ToolInvocation(
        call=ToolCall(call_id="call-1", name=name, arguments=dict(arguments)),
        correlation=make_correlation(),
        timeout_ms=5_000,
        granted=frozenset({PermissionKind.NET}),
    )


def missing_secret() -> NucleaError:
    return NucleaError(ErrorCode.CONFIG_SECRET_MISSING, "没配。")
