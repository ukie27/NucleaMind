"""官方插件 `image`：按文字描述生成图像并落盘（开发方案 `D37`）。

职责：声明一条 `TOOL` 能力 `image.generate`，调用图像后端、把回来的图写进磁盘、
交出 `ArtifactRef`。
不负责：把图发到聊天平台（见下面第一条边界）、图像编辑与识别、语音转写。

**它取代的是 `references/nanobot` 的 `agent/tools/image_generation.py` +
`providers/image_generation.py`**，但不是移植：

- 旧实现有**按模型名分支的尺寸换算表**（aihubmix 的 `_aihubmix_size`、ollama 的
  `_ollama_dimensions` 与 `_round_to_multiple`）。一张都没搬。对应物是三个显式配置项
  `size` / `response_format` / `extra_body`，**留空即不发这个字段**。理由与 `D19` 拒掉
  `max_tokens_field` slug 表、`D32` 拒掉四张版本 gating 表完全相同。
- 旧实现有三个后端类（openrouter / aihubmix / ollama）。这里写死两个形状差异大的
  （`openai` 的专用图像端点、`openrouter` 的 chat-with-image），第三家用
  `provider="openai"` + `base_url` 接上——aihubmix 与多数网关本来就是 OpenAI 兼容的。
- 旧实现把图写进一个全局 media 目录并把 data URL 回给模型。这里写进插件自己的状态目录、
  用**内容寻址**的文件名，只把路径回给模型（见下面第二条边界）。

**三条如实记着的边界**，写在这里而不是留给用户发现：

- **`ToolResult.artifacts` 今天在全项目零消费者，本插件是它的第一个生产者。**
  生成的图只能由用户到目录里去看：`OutboundMessage` 的附件路径没有生产者，
  因此没有任何 Channel 能把这些字节发出去。（`D42` 给 `FileAccess` 补了
  `read_bytes` / `write_bytes`，**这条边界没有因此变化**——缺的从来不是读字节的方法，
  是出站侧的附件通路。）
- **不用 `ctx.fs`，如实声明 `fs:write` 并直接用 `pathlib`。** `ctx.fs` 的根是实例的
  workspace，而图落在插件自己的 state_dir——这不是缺个方法，是两个目录树，详见
  `storage.py`。`builtins/session_jsonl/` 的同一条先例：门面够不着的地方，
  诚实声明比绕道更符合权限模型的意义。
- **不用 `ctx.net`，如实声明 `net` 并直接用 httpx。** 图像端点由运维配置（要能指到本地
  ollama 与自建网关），而 SSRF 守卫按设计拒绝私有地址。**模型在这里决定不了任何地址**，
  它只给 prompt——这与 `web.fetch` 恰好相反，那一条必须走守卫。

**只 import `nucleamind.contracts` 与 `nucleamind.sdk`**（依赖规则 `R4`）；`httpx` 在
`tool.py` 里惰性 import。**`MANIFEST` 在模块顶层且导入无副作用**（技术方案 §7.2）。
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Final

from nucleamind.contracts import CapabilityKind, PermissionKind
from nucleamind.sdk import (
    CapabilityDecl,
    ManifestJsonSchema,
    NucleaAPI,
    PermissionDecl,
    PluginContext,
    PluginManifest,
)

from .settings import (
    DEFAULT_MAX_COUNT,
    DEFAULT_MODEL,
    DEFAULT_PROVIDER,
    IMAGE_DIR_NAME,
    PROVIDERS,
    SECRET_NAME,
    ImageSettings,
    resolve_settings,
)
from .storage import ImageStore, SavedImage, digest_name
from .tool import GENERATE_TOOL, ImageGenerateTool, generate_spec
from .wire import (
    OPENAI_DEFAULT_BASE_URL,
    OPENROUTER_DEFAULT_BASE_URL,
    ImageRequest,
    ImageSource,
    build_request,
    check_status,
    decode_data_url,
    extension_for,
    parse_response,
)

if TYPE_CHECKING:  # pragma: no cover - 仅类型
    import httpx

__all__ = [
    "CONFIG_SCHEMA",
    "DEFAULT_MAX_COUNT",
    "DEFAULT_MODEL",
    "DEFAULT_PROVIDER",
    "GENERATE_TOOL",
    "IMAGE_DIR_NAME",
    "MANIFEST",
    "OPENAI_DEFAULT_BASE_URL",
    "OPENROUTER_DEFAULT_BASE_URL",
    "PROVIDERS",
    "SECRET_NAME",
    "ImageGenerateTool",
    "ImageRequest",
    "ImageSettings",
    "ImageSource",
    "ImageStore",
    "SavedImage",
    "build_request",
    "check_status",
    "decode_data_url",
    "digest_name",
    "extension_for",
    "generate_spec",
    "image_directory",
    "parse_response",
    "register",
    "resolve_settings",
    "setup",
]

#: `plugins.image.config` 的形状。阶段 A 用它校验，`settings.py` 再做它表达不了的那些。
#: 标注成 `ManifestJsonSchema` 而不是 `contracts.JsonSchema`：契约那个类型进不了
#: pydantic 模型（会 `RecursionError`），细节见 `sdk/manifest.py::ManifestJsonValue`。
CONFIG_SCHEMA: Final[ManifestJsonSchema] = {
    "type": "object",
    "properties": {
        "provider": {"type": "string", "enum": list(PROVIDERS)},
        "base_url": {
            "type": "string",
            "description": "自建网关或本地端点。留空时用后端各自的官方地址。",
        },
        "model": {"type": "string"},
        "size": {
            "type": "string",
            "description": "留空即不发这个字段，由后端用它自己的默认值。",
        },
        "response_format": {
            "type": "string",
            "enum": ["b64_json", "url"],
            "description": (
                "留空即不发。gpt-image-1 恒回 base64 且会拒绝这个字段；"
                "dall-e-3 需要 b64_json 才不回一个有期限的 URL。"
            ),
        },
        "max_count": {"type": "integer", "minimum": 1, "description": "单次调用的张数上限。"},
        "timeout_ms": {"type": "integer", "minimum": 1},
        "max_result_chars": {"type": "integer", "minimum": 1},
        "dir": {
            "type": "string",
            "description": "落盘目录。相对路径按插件状态目录解析，留空即 <state_dir>/images。",
        },
        "extra_body": {
            "type": "object",
            "description": "透传给后端的额外请求字段（标量或数组）。",
        },
    },
    "additionalProperties": False,
}

MANIFEST: Final = PluginManifest(
    id="image",
    version="0.1.0",
    sdk_range=">=1.0.0,<2.0.0",
    setup="nucleamind_plugin_image:setup",
    capabilities=(CapabilityDecl(kind=CapabilityKind.TOOL, name=GENERATE_TOOL),),
    permissions=(
        PermissionDecl(
            kind=PermissionKind.NET,
            reason="调用配置好的图像生成端点，并取回它返回的图像。",
        ),
        PermissionDecl(
            kind=PermissionKind.FS_WRITE,
            reason="把生成的图像写进插件自己的状态目录（在 ctx.fs 的 workspace 根之外）。",
        ),
        PermissionDecl(
            kind=PermissionKind.SECRET,
            target=SECRET_NAME,
            reason="图像后端的 API key。",
        ),
    ),
    config_schema=CONFIG_SCHEMA,
    # `critical=False`：没有图像工具的 Agent 仍然能对话。配置错误因此只表现为
    # `nm plugins` 里的一行 `PLUGIN_LOAD_FAILED`，所以校验必须在 `setup()` 里一次做完
    # 而不是拖到第一次调用（`D32` anthropic 的同一条理由）。
    critical=False,
)


def image_directory(ctx: PluginContext, settings: ImageSettings) -> Path:
    """落点：配置的 `dir`，没配就是 `<state_dir>/images`。

    **相对路径按状态目录解析**而不是按进程 cwd：`nm` 从哪个目录启动不该改变图存到哪里。
    绝对路径原样采纳——运维显式写下的绝对路径就是他要的那个位置。
    """
    if not settings.directory:
        return ctx.state_dir / IMAGE_DIR_NAME
    configured = Path(settings.directory)
    return configured if configured.is_absolute() else ctx.state_dir / configured


def register(
    api: NucleaAPI,
    ctx: PluginContext,
    *,
    transport: "httpx.AsyncBaseTransport | None" = None,
) -> ImageSettings:
    """真正的注册体。`transport` 只有测试会传（httpx 传输层替身）。

    与 `setup()` 分开是为了让用例能在不构造整个装配根的情况下驱动它，同时保证
    生产路径与测试路径**注册的是同一个对象**。
    """
    settings = resolve_settings(ctx.config)
    store = ImageStore(image_directory(ctx, settings))
    api.register_tool(
        generate_spec(), ImageGenerateTool(ctx, settings, store, transport=transport)
    )
    return settings


def setup(api: NucleaAPI) -> None:
    """注册入口。manifest 的 `setup` 字段指向它。

    **配置在这里一次校验完**（`resolve_settings` 会抛 `CONFIG_INVALID`）；
    **凭据不在这里取**——一个还没导出 API key 的实例照样应当起得来，缺凭据的表现是
    那一次调用失败而不是插件加载失败。**目录也不在这里创建**：`setup()` 为一个可能
    永远不被调用的工具建目录，是在没人要求的时候动用户的磁盘。
    """
    register(api, api.ctx)
