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

__all__ = ["BUILTIN_MANIFESTS", "SESSION_JSONL"]

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

#: 全部内建能力的 manifest。`D18`–`D22` 逐个追加（context_basic / model_openai /
#: tools_fs / tools_shell / commands_core / cli_entry）。
BUILTIN_MANIFESTS: Final[tuple[PluginManifest, ...]] = (SESSION_JSONL,)
