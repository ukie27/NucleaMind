"""官方插件 `web`：给实例装上「抓网页」与「搜网」两件工具（开发方案 `D36`）。

职责：声明两条 `TOOL` 能力（`web.fetch` / `web.search`），把一次抓取或一次搜索翻成
`ToolResult`。
不负责：决定什么时候调它们（模型与 `kernel/turn/`）、校验参数（kernel 的
`ToolInvoker` 按 `ToolSpec.parameters` 校验）、把结果放进上下文（`kernel/turn/context_builder.py`）。

**它取代的是 `references/nanobot/nanobot/agent/tools/web.py`**，但不是移植：

- 旧实现有 **13 个写死的搜索后端**（duckduckgo / brave / tavily / searxng / jina / kagi /
  exa / bocha / serper / olostep / volcengine / keenable …）。这里只写死四个形状差异大的，
  其余交给可配置的 `custom` 后端。理由与 `D19` 拒掉 `max_tokens_field` slug 表、`D32` 拒掉
  四张版本 gating 表完全相同：**表只会越滚越大，而用户接一个新后端要等我们发版**。
- 旧实现在**凭据缺失时静默回退到 DuckDuckGo**。这里不回退：配了 tavily 却没给 key，
  得到的是一条指名道姓的 `CONFIG_SECRET_MISSING`，而不是一份来自另一个后端、看起来一切
  正常的结果（原则 7「不静默修正坏输入」）。
- 旧实现的 `duckduckgo` 后端依赖第三方包 `ddgs`。这里自己解析 `html.duckduckgo.com/html/`
  的返回，因此**默认后端不引入任何新依赖**。
- 旧实现把 `web_search` 与 `web_fetch` 缠在一个 1186 行的文件里、且两者共用一套 httpx
  调用。这里按**谁决定 URL** 切开出网路径，见下。

**三条如实记着的边界**，写在这里而不是留给用户发现：

- **`web.fetch` 走 `ctx.net`，`web.search` 直接用 httpx**，判据是那个 URL 由谁决定：
  前者整个来自模型（正是 SSRF 守卫存在的理由，`EDG-406`），后者的端点来自运维配置而
  模型只控制 query——自托管 SearXNG 常在私有网段，`ctx.net` 会按设计拒掉它。后一条与内建
  `model_openai` 要连本地 vLLM / Ollama 是同一条先例：门面能力不足时，**如实声明 `net`
  权限**比绕道更符合「应用级权限的价值是让越界意图可审计」。
- **抓回来的正文是不可信数据，而 `ToolResult` 没有 trust 字段。** 契约层的
  `UNTRUSTED_DATA_PREFIX` 包裹（`contracts/context.py::as_model_text`）只作用于
  `ContextFragment`，工具结果不经过那条路径。本插件在正文前加一行横幅
  （`tools.UNTRUSTED_BANNER`），那是**提醒而不是隔离**——一段写着「忽略以上指令」的网页
  仍然会原样进模型。要真正解决它得给 `ToolResult` 一个 trust 槽位，那是冻结表面变更
  （`NFR-104`）。
- **`ctx.net.request` 不能流式**：它一次性返回完整 `body: bytes`，因此超大页面只能**先
  下完再截断**（`fetch.max_bytes` 作用在解码之前，但字节已经进过内存），靠 `timeout_ms`
  兜底。要按字节提前中断得给 `HttpAccess` 加一个流式方法。

**只 import `nucleamind.contracts` 与 `nucleamind.sdk`**（依赖规则 `R4`）；`httpx` 是
`web.search` 的实现细节，在 `tools.py` 里惰性 import。**`MANIFEST` 在模块顶层且导入无副作用**
（技术方案 §7.2）：发现阶段只 import 本模块取那个对象，此时不该发生任何 IO。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from nucleamind.contracts import CapabilityKind, PermissionKind
from nucleamind.sdk import (
    CapabilityDecl,
    NucleaAPI,
    PermissionDecl,
    PluginContext,
    PluginManifest,
)

from .backends import (
    BRAVE_ENDPOINT,
    DUCKDUCKGO_ENDPOINT,
    TAVILY_ENDPOINT,
    SearchHit,
    SearchRequest,
    build_request,
    check_status,
    format_hits,
    parse_response,
)
from .extract import (
    MediaKind,
    Page,
    decode_body,
    html_to_text,
    looks_binary,
    media_kind_of,
    truncate,
)
from .settings import (
    CREDENTIALLESS_PROVIDERS,
    DEFAULT_MAX_RESULTS,
    DEFAULT_PROVIDER,
    DEFAULT_USER_AGENT,
    PROVIDERS,
    SECRET_NAME,
    CustomBackend,
    FetchSettings,
    SearchSettings,
    WebSettings,
    resolve_settings,
)
from .tools import (
    FETCH_TOOL,
    SEARCH_TOOL,
    UNTRUSTED_BANNER,
    WebFetchTool,
    WebSearchTool,
    fetch_spec,
    search_spec,
)

if TYPE_CHECKING:  # pragma: no cover - 仅类型
    import httpx

__all__ = [
    "BRAVE_ENDPOINT",
    "CONFIG_SCHEMA",
    "CREDENTIALLESS_PROVIDERS",
    "DEFAULT_MAX_RESULTS",
    "DEFAULT_PROVIDER",
    "DEFAULT_USER_AGENT",
    "DUCKDUCKGO_ENDPOINT",
    "FETCH_TOOL",
    "MANIFEST",
    "PROVIDERS",
    "SEARCH_TOOL",
    "SECRET_NAME",
    "TAVILY_ENDPOINT",
    "UNTRUSTED_BANNER",
    "CustomBackend",
    "FetchSettings",
    "MediaKind",
    "Page",
    "SearchHit",
    "SearchRequest",
    "SearchSettings",
    "WebFetchTool",
    "WebSearchTool",
    "WebSettings",
    "build_request",
    "check_status",
    "decode_body",
    "fetch_spec",
    "format_hits",
    "html_to_text",
    "looks_binary",
    "media_kind_of",
    "parse_response",
    "register",
    "resolve_settings",
    "search_spec",
    "setup",
    "truncate",
]

#: `plugins.web.config` 的形状。阶段 A 用它校验（`kernel/plugins/loader.py`），
#: `settings.py` 再做它表达不了的那些（枚举可选值、跨字段依赖、上界）。
CONFIG_SCHEMA: Final = {
    "type": "object",
    "properties": {
        "user_agent": {"type": "string", "description": "两个工具共用的 User-Agent。"},
        "fetch": {
            "type": "object",
            "properties": {
                "max_bytes": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "响应体读取上限（字节），超出部分丢弃。",
                },
                "max_result_chars": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "返回给模型的字符上限。",
                },
                "timeout_ms": {"type": "integer", "minimum": 1},
            },
            "additionalProperties": False,
        },
        "search": {
            "type": "object",
            "properties": {
                "provider": {
                    "type": "string",
                    "enum": list(PROVIDERS),
                    "description": "搜索后端。searxng 与 custom 必须同时配 base_url。",
                },
                "base_url": {
                    "type": "string",
                    "description": "自托管或自定义端点。留空时内置后端用各自的官方地址。",
                },
                "max_results": {"type": "integer", "minimum": 1},
                "timeout_ms": {"type": "integer", "minimum": 1},
                "max_result_chars": {"type": "integer", "minimum": 1},
                "custom": {
                    "type": "object",
                    "description": "provider=custom 时怎么拼请求、怎么读响应。",
                    "properties": {
                        "method": {"type": "string", "enum": ["GET", "POST"]},
                        "query_field": {"type": "string"},
                        "count_field": {"type": "string"},
                        "headers": {
                            "type": "object",
                            "additionalProperties": {"type": "string"},
                            "description": "值里的 {api_key} 会被替换成配置的凭据。",
                        },
                        "results_path": {
                            "type": "string",
                            "description": "结果数组的点分路径，如 data.results。",
                        },
                        "title_field": {"type": "string"},
                        "url_field": {"type": "string"},
                        "snippet_field": {"type": "string"},
                    },
                    "additionalProperties": False,
                },
            },
            "additionalProperties": False,
        },
    },
    "additionalProperties": False,
}

MANIFEST: Final = PluginManifest(
    id="web",
    version="0.1.0",
    sdk_range=">=0.1.0,<0.2.0",
    setup="nucleamind_plugin_web:setup",
    capabilities=(
        CapabilityDecl(kind=CapabilityKind.TOOL, name=FETCH_TOOL),
        CapabilityDecl(kind=CapabilityKind.TOOL, name=SEARCH_TOOL),
    ),
    permissions=(
        # `web.fetch` 经 `ctx.net`、`web.search` 直接用 httpx——两者都是出网，因此都在这一条
        # 声明底下。声明的是**意图**，不是「用了哪个门面」。
        PermissionDecl(
            kind=PermissionKind.NET,
            reason="web.fetch 抓取模型给出的网页；web.search 访问配置好的搜索后端。",
        ),
        PermissionDecl(
            kind=PermissionKind.SECRET,
            target=SECRET_NAME,
            reason="需要凭据的搜索后端（tavily / brave / custom）用它鉴权。",
        ),
    ),
    config_schema=CONFIG_SCHEMA,
    # `critical=False`：没有网页工具的 Agent 仍然能对话，这与「没有模型」不是一回事。
    critical=False,
)


def register(
    api: NucleaAPI,
    ctx: PluginContext,
    *,
    transport: "httpx.AsyncBaseTransport | None" = None,
) -> WebSettings:
    """真正的注册体。`transport` 只有测试会传（`web.search` 的 httpx 传输层替身）。

    与 `setup()` 分开是为了让用例能在不构造整个装配根的情况下驱动它，同时保证
    生产路径与测试路径**注册的是同一组对象**。
    """
    settings = resolve_settings(ctx.config)
    api.register_tool(fetch_spec(), WebFetchTool(ctx, settings))
    api.register_tool(search_spec(), WebSearchTool(ctx, settings, transport=transport))
    return settings


def setup(api: NucleaAPI) -> None:
    """注册入口。manifest 的 `setup` 字段指向它。

    **配置在这里一次校验完**（`resolve_settings` 会抛 `CONFIG_INVALID`）：一份写错的配置
    应当在 `nm plugins list` 里以 `PLUGIN_LOAD_FAILED` 看得见，而不是等到模型第一次调工具
    时才变成一条工具失败。**凭据不在这里取**，理由见 `settings.py` 的模块 docstring。

    **在返回前完成全部注册**：注册先进暂存批次，`setup` 正常返回才一次性并入 registry；
    中途抛异常则整批丢弃（`EDG-103`）。
    """
    register(api, api.ctx)
