"""内建能力的静态清单（技术方案 §7.1、§8）。

职责：以 `BUILTIN_MANIFESTS` 声明全部内建能力的 manifest——这是内建能力**唯一**的发现来源。
不负责：导入任何 `setup` 实现、决定加载顺序、判定权限、注册能力本身。

**manifest 写在这里而不是各内建子包里**，因为读 manifest 不该导入实现（§7.1「发现与启用
分离」）：`import nucleamind.builtins.registry` 只需要 pydantic 与几个字面量，
`session_jsonl` 的 `setup` 只在真正加载它时才被 `import_setup()` 拉进来。

**内建不享受特权**（`BAS-005`）：这里的每一条都是普通的 `PluginManifest`，与外部插件同型，
同样要声明 `capabilities` 与 `permissions`，同样经 `runtime/wiring.py` 翻译成 `LoadRequest`
后走 `kernel/plugins/host.py` 那**一个** Host 注册。本目录受 `R4` 约束，只能 import
`sdk/` 与 `contracts/`，因此这里连 registry 长什么样都看不见。

**`priority` 一律不写**：`CapabilityDecl.priority` 的默认值是 100，而内建的基准是 0
（技术方案 §6.1 规则 1）。写了就会被原样采纳，「内建排在插件前」与「内建最后被裁」会同时
静默失效——`to_declaration()` 靠 pydantic 的 `model_fields_set` 判断作者到底写没写。
"""

from __future__ import annotations

from typing import Final

from nucleamind.contracts import CapabilityKind, PermissionKind
from nucleamind.sdk import CapabilityDecl, PermissionDecl, PluginManifest

__all__ = [
    "BUILTIN_MANIFESTS",
    "CONTEXT_BASIC",
    "MODEL_OPENAI",
    "SESSION_JSONL",
    "TOOLS_FS",
    "TOOLS_SHELL",
]

#: `D17` 内建 Session（技术方案 §8.1）。
#:
#: `critical=True`：没有会话存储就没有历史，而 `SES-003` 不允许把持久化失败伪装成成功。
#: 它加载失败时实例应当直接启动失败，而不是带着一个「说完就忘」的 Agent 继续跑。
#: `critical` 是**提供方级**的，同一份 manifest 里的全部能力共享它（`D16` 的结论）。
#:
#: 声明 `fs:read` / `fs:write` 而不用 `ctx.fs`：`FileAccess` 没有追加、`fsync` 与原子替换，
#: 用它实现追加写等于每次重写整个会话文件。应用级权限的意义是让越界意图**可审计**
#: （`sdk/api.py` 写死的诚实声明），因此如实声明比绕道更符合它。
SESSION_JSONL: Final = PluginManifest(
    id="session-jsonl",
    version="0.1.0",
    sdk_range=">=0.1.0,<0.2.0",
    setup="nucleamind.builtins.session_jsonl:setup",
    capabilities=(CapabilityDecl(kind=CapabilityKind.SESSION_STORE, name="jsonl"),),
    permissions=(
        PermissionDecl(kind=PermissionKind.FS_READ, reason="读取实例目录下的会话历史与元数据。"),
        PermissionDecl(kind=PermissionKind.FS_WRITE, reason="追加会话历史并原子替换会话元数据。"),
    ),
    config_schema={
        "type": "object",
        "properties": {
            "dir": {
                "type": "string",
                "description": "会话文件所在目录。缺省时使用本插件的私有状态目录；"
                "装配根会把实例布局的 sessions/ 目录填在这里。",
            }
        },
        "additionalProperties": False,
    },
    critical=True,
)

#: `D18` 内建 Context Provider（技术方案 §8.1）。
#:
#: `critical=True`：它是 `CTX-006` 的兜底——没有它、也没装任何 Memory 或检索插件时，
#: 模型将拿不到任何系统指令。一份写错的配置（`resolve_settings` 抛 `CONFIG_INVALID`）
#: 应当让实例启动失败，而不是让一个「没人告诉它自己是谁」的 Agent 上线。
#:
#: **一个权限也不声明**：本内建纯内存、不读盘、不出网（技术方案 §14 的「Provider 只读
#: 不写」）。声明一条用不到的权限就是把「越界意图可审计」这件事变得不可审计。
CONTEXT_BASIC: Final = PluginManifest(
    id="context-basic",
    version="0.1.0",
    sdk_range=">=0.1.0,<0.2.0",
    setup="nucleamind.builtins.context_basic:setup",
    capabilities=(CapabilityDecl(kind=CapabilityKind.CONTEXT, name="basic"),),
    config_schema={
        "type": "object",
        "properties": {
            "instructions": {
                "description": "运维自定义的指令文本。它以 TrustLevel.OPERATOR 进入上下文，"
                "不占据系统指令位置（`CMD-005`）。",
                "anyOf": [
                    {"type": "string"},
                    {"type": "array", "items": {"type": "string"}},
                ],
            },
            "use_baseline_instructions": {
                "type": "boolean",
                "default": True,
                "description": "是否附上内建基线系统指令。关掉它就必须提供 instructions。",
            },
            "include_runtime_facts": {
                "type": "boolean",
                "default": True,
                "description": "是否附上当前时间、会话身份与历史条数这几项运行时事实。",
            },
        },
        "additionalProperties": False,
    },
    critical=True,
)

#: `D19` 内建 Model Provider（技术方案 §8.1、§15 第 5 项）。
#:
#: `critical=True`：没有模型就没有 Agent。一份写错的 `base_url`、一个没导出的
#: `OPENAI_API_KEY`，都应当在启动时被指出来，而不是等用户发出第一条消息才炸。
#:
#: **两条权限都如实声明**：
#: - `net`：直接用 httpx 而不是 `ctx.net`。`HttpAccess` 的 SSRF 守卫会拒绝私有网段，
#:   而本内建的交付要点就包含本地 vLLM / Ollama / LM Studio。与 `session_jsonl` 用
#:   `pathlib` 是同一条先例——门面能力不足时，诚实声明比绕道更符合「让越界意图可审计」。
#: - `secret:api_key`：凭据只从 `ctx.secret("api_key")` 来，配置块里根本没有这个键，
#:   `CFG-003`「明文不进配置文档」因此是结构性成立的而不是靠流程遵守。
#:   密钥名固定为 `SECRET_NAME` 常量——做成可配置会让这条 `target` 变成一句谎话。
MODEL_OPENAI: Final = PluginManifest(
    id="model-openai",
    version="0.1.0",
    sdk_range=">=0.1.0,<0.2.0",
    setup="nucleamind.builtins.model_openai:setup",
    capabilities=(CapabilityDecl(kind=CapabilityKind.MODEL, name="openai"),),
    permissions=(
        PermissionDecl(
            kind=PermissionKind.NET,
            reason="调用 OpenAI 兼容的 Chat Completions 端点；地址由运维在配置里显式指定，"
            "可以是本地的 vLLM / Ollama / LM Studio。",
        ),
        PermissionDecl(
            kind=PermissionKind.SECRET,
            target="api_key",
            reason="向模型端点认证。auth=\"none\" 时（本地模型服务）不会取用。",
        ),
    ),
    config_schema={
        "type": "object",
        "properties": {
            "base_url": {
                "type": "string",
                "default": "https://api.openai.com/v1",
                "description": "端点根，原样使用不追加 /v1——各家后缀差异极大"
                "（OpenVINO 是 /v3，vLLM 没有约定）。",
            },
            "auth": {
                "type": "string",
                "enum": ["bearer", "api_key_header", "none"],
                "default": "bearer",
                "description": "认证形态：Authorization: Bearer / Azure 的 api-key 头 / "
                "无凭据（本地模型服务）。",
            },
            "models": {
                "type": "object",
                "description": "按模型标识列举窗口、上限与线格式偏好。"
                "非空即为白名单：不在其中的模型 describe() 会报能力缺失。",
                "additionalProperties": {
                    "type": "object",
                    "properties": {
                        "context_window_tokens": {"type": "integer", "minimum": 1},
                        "max_output_tokens": {"type": "integer", "minimum": 1},
                        "capabilities": {"type": "array", "items": {"type": "string"}},
                        "max_tokens_field": {
                            "type": "string",
                            "enum": ["max_tokens", "max_completion_tokens"],
                        },
                        "supports_temperature": {"type": "boolean"},
                    },
                    "additionalProperties": False,
                },
            },
            "default_context_window_tokens": {
                "type": "integer",
                "minimum": 1,
                "default": 128000,
                "description": "models 未覆盖时的上下文窗口，Context 预算由它推导。",
            },
            "default_max_output_tokens": {
                "type": "integer",
                "minimum": 1,
                "default": 4096,
                "description": "models 未覆盖时的单次输出上限。",
            },
            "capabilities": {
                "type": "array",
                "items": {"type": "string"},
                "default": ["tool_calls", "streaming"],
                "description": "显式列出支持项（MOD-005）。不在表里的能力一律报缺失，"
                "不静默降级。",
            },
            "max_tokens_field": {
                "type": "string",
                "enum": ["max_tokens", "max_completion_tokens"],
                "default": "max_tokens",
                "description": "输出上限的字段名。gpt-5、o1/o3/o4 只认后者。",
            },
            "supports_temperature": {
                "type": "boolean",
                "default": True,
                "description": "关掉后 temperature 被省略而不是钳值——推理模型对它直接 400。",
            },
            "request_timeout_ms": {
                "type": "integer",
                "minimum": 1,
                "default": 120000,
                "description": "ModelRequest.timeout_ms 为 0（不限）时的兜底。",
            },
            "stream_idle_timeout_ms": {
                "type": "integer",
                "minimum": 1,
                "default": 60000,
                "description": "流打开后卡住的看门狗。请求级超时保护不了一个开了口"
                "就不再吐字的流。",
            },
            "include_usage": {
                "type": "boolean",
                "default": False,
                "description": "流式请求是否携带 stream_options.include_usage。"
                "默认关：不少兼容端点会对未知字段 400。",
            },
        },
        "additionalProperties": False,
    },
    critical=True,
)

#: `D20` 内建文件工具（技术方案 §8.2 的冻结清单，`shell.exec` 是 `D21`）。
#:
#: `critical=False`：没有文件工具的 Agent 仍然能对话，这与「没有模型」「没有会话存储」
#: 不是一回事。一份写错的 workspace 路径应当让这一项加载失败并留下诊断，而不是把整个
#: 实例拽下水。
#:
#: **五条声明必须与 `tools_fs.TOOL_NAMES` 逐一对应**，由测试对照。被 `disable` 关掉的
#: 工具**不会**被注册，因此装配根必须用同一份配置过滤这里的声明
#: （`runtime/wiring.py` 的 `keep` 参数 + `tools_fs.enabled_tool_names()`）——否则
#: `D16` 的 `CapabilityHost.finish()` 会以 `PLUGIN_LOAD_FAILED` 拒绝加载，而那个报错是对的。
#:
#: 两条权限如实声明而不用 `ctx.fs`：`FileAccess` 只有 `read_text` / `write_text` /
#: `list_dir`，没有目录遍历、没有原子替换、没有按字节数截断的读，用它实现本内建等于
#: 重写一遍它。与 `session_jsonl` 同一条先例——门面能力不足时，诚实声明比绕道更符合
#: 「让越界意图可审计」。
TOOLS_FS: Final = PluginManifest(
    id="tools-fs",
    version="0.1.0",
    sdk_range=">=0.1.0,<0.2.0",
    setup="nucleamind.builtins.tools_fs:setup",
    capabilities=(
        CapabilityDecl(kind=CapabilityKind.TOOL, name="fs.read"),
        CapabilityDecl(kind=CapabilityKind.TOOL, name="fs.write"),
        CapabilityDecl(kind=CapabilityKind.TOOL, name="fs.edit"),
        CapabilityDecl(kind=CapabilityKind.TOOL, name="fs.list"),
        CapabilityDecl(kind=CapabilityKind.TOOL, name="fs.grep"),
    ),
    permissions=(
        PermissionDecl(
            kind=PermissionKind.FS_READ,
            reason="读取 workspace 内的文件与目录，供 fs.read / fs.list / fs.grep 使用。",
        ),
        PermissionDecl(
            kind=PermissionKind.FS_WRITE,
            reason="原子写入 workspace 内的文件，供 fs.write / fs.edit 使用。",
        ),
    ),
    config_schema={
        "type": "object",
        "properties": {
            "workspace": {
                "type": "string",
                "description": "全部路径解析的根。缺省时使用本插件的私有状态目录；"
                "装配根会把配置里的 workspace.root 填在这里。",
            },
            "disable": {
                "type": "array",
                "items": {"type": "string"},
                "description": "要关掉的工具名（TOL-006）。被关掉的工具不会注册，"
                "因此也不出现在模型可见的工具列表里。表外的名字会被拒绝。",
            },
            "max_read_bytes": {
                "type": "integer",
                "minimum": 1,
                "default": 1048576,
                "description": "单次从磁盘读取的字节上限。超出是截断而不是失败。",
            },
            "max_result_chars": {
                "type": "integer",
                "minimum": 1,
                "default": 32768,
                "description": "单个工具结果的字符上限，不得超过契约的 65536。",
            },
            "max_entries": {
                "type": "integer",
                "minimum": 1,
                "default": 500,
                "description": "fs.list 单次返回的条目数上限。",
            },
            "max_matches": {
                "type": "integer",
                "minimum": 1,
                "default": 200,
                "description": "fs.grep 单次返回的匹配数上限。",
            },
        },
        "additionalProperties": False,
    },
    critical=False,
)

#: `D21` 内建 shell 工具（技术方案 §8.2 冻结清单的第 6 项，至此六件套齐）。
#:
#: `critical=False`：没有 shell 工具的 Agent 仍然能对话，与 `tools_fs` 同一条理由。
#:
#: **只声明一条 `shell` 权限**。它是全部五种权限里最强的一个——一条命令能读能写能出网，
#: `fs:read` / `fs:write` / `net` 在它面前都是子集，再声明一遍只会让「这个插件到底要什么」
#: 变模糊。`NFR-307` 的「默认保守」由两件事兑现：整条权限可以不授予（那时本内建不注册），
#: 以及子进程的环境变量默认一个都不继承（`environ.py` 是白名单，不是黑名单）。
TOOLS_SHELL: Final = PluginManifest(
    id="tools-shell",
    version="0.1.0",
    sdk_range=">=0.1.0,<0.2.0",
    setup="nucleamind.builtins.tools_shell:setup",
    capabilities=(CapabilityDecl(kind=CapabilityKind.TOOL, name="shell.exec"),),
    permissions=(
        PermissionDecl(
            kind=PermissionKind.SHELL,
            reason="在 workspace 内执行运维与开发命令；cwd 限定在 workspace 根内，"
            "子进程默认不继承父进程的任何环境变量。",
        ),
    ),
    config_schema={
        "type": "object",
        "properties": {
            "workspace": {
                "type": "string",
                "description": "命令的默认 cwd，也是 cwd 参数必须落在其内的根。"
                "缺省时使用本插件的私有状态目录；装配根会把配置里的 workspace.root 填在这里。",
            },
            "disable": {
                "type": "array",
                "items": {"type": "string"},
                "description": "要关掉的工具名（TOL-006）。被关掉的工具不会注册，"
                "因此也不出现在模型可见的工具列表里。表外的名字会被拒绝。",
            },
            "timeout_ms": {
                "type": "integer",
                "minimum": 1,
                "default": 120000,
                "description": "单次命令的执行超时。实际生效值是它与 "
                "ToolInvocation.timeout_ms 的较小者。",
            },
            "max_output_chars": {
                "type": "integer",
                "minimum": 1,
                "default": 32768,
                "description": "单个工具结果的字符上限，不得超过契约的 65536。",
            },
            "pass_env": {
                "type": "array",
                "items": {"type": "string"},
                "description": "额外从父进程转发给子进程的环境变量名。"
                "默认一个都不转发（NFR-307）；父进程里没有的名字会被静默跳过。",
            },
            "env": {
                "type": "object",
                "additionalProperties": {"type": "string"},
                "description": "显式写死的环境变量，覆盖平台基线与 pass_env。",
            },
            "shell": {
                "type": "string",
                "description": "shell 程序路径。缺省时 POSIX 用 /bin/sh、Windows 用 %ComSpec%。",
            },
        },
        "additionalProperties": False,
    },
    critical=False,
)

#: 全部内建能力的 manifest。`D22` 逐个追加（commands_core / cli_entry）。
BUILTIN_MANIFESTS: Final[tuple[PluginManifest, ...]] = (
    SESSION_JSONL,
    CONTEXT_BASIC,
    MODEL_OPENAI,
    TOOLS_FS,
    TOOLS_SHELL,
)
