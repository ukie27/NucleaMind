"""工具契约：声明、调用、结果与副作用（需求 §10.5、`TOL-001`–`TOL-004`）。

职责：定义工具声明 `ToolSpec`、模型发出的 `ToolCall`、带执行上下文的 `ToolInvocation`、
产物引用 `ArtifactRef` 与结果 `ToolResult`，以及权限、风险、并发与副作用四组枚举。
不负责：执行工具、判定权限、截断内容、调度并发——那些在 `kernel/tools/`（`D11`）与
`builtins/tools/`（`D19`–`D21`）；本模块不含任何 IO。

两条不肯让步的规则：

- `side_effect` 必填且没有默认值。中断与超时场景下「副作用是否已经发生」是一等状态
  （`EDG-401`、`EDG-407`），给默认值等于允许构造点不表态，而不表态的代价由用户承担。
- `ok=False` 必须带 `error`。§10.5 末段要求 Tool 错误不得伪装为普通成功文本，
  在类型层堵住比在评审里提醒可靠。
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Final

from .context import TrustLevel, wrap_untrusted
from .errors import ErrorCode, NucleaError
from .ids import Correlation, validate_identifier
from .metadata import EMPTY_METADATA, normalize_metadata

if TYPE_CHECKING:  # pragma: no cover - 仅为注解，运行时不导入，避免与包根成环。
    from . import JsonSchema, JsonValue

__all__ = [
    "MAX_TOOL_RESULT_LENGTH",
    "ArtifactRef",
    "Concurrency",
    "PermissionKind",
    "RiskLevel",
    "SideEffect",
    "ToolCall",
    "ToolInvocation",
    "ToolResult",
    "ToolSpec",
]

#: 供模型消费的结果文本上限（字符）。超出由 Kernel 截断并置 `truncated=True`
#: （`TOL-003`、`EDG-403`）；契约层只拦住「截断没做」的情况。
MAX_TOOL_RESULT_LENGTH: Final = 64 * 1024

#: 工具名形状：小写、点分命名空间，如 `fs.read`、`shell.exec`（技术方案 §8.2）。
_TOOL_NAME_PATTERN: Final = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$")


#: 工具结果允许的两档可信度。`OPERATOR` / `USER` 在这里没有意义——工具结果既不是运维
#: 写下的配置，也不是用户说的话；放行它们只会让 `trust` 这个字段有四种读法而只有两种后果。
_TOOL_RESULT_TRUST: Final = frozenset({TrustLevel.SYSTEM, TrustLevel.UNTRUSTED})


class PermissionKind(StrEnum):
    """声明式权限（技术方案 §7.5）。

    首版是「声明 + 应用级强制」，不承诺进程隔离——同进程 Python 插件可以绕过门面。
    它的价值是让越界意图可审计、在评审与测试中可见。
    """

    FS_READ = "fs:read"
    FS_WRITE = "fs:write"
    NET = "net"
    SHELL = "shell"
    SECRET = "secret"


class RiskLevel(StrEnum):
    """风险等级（`TOL-004`、技术方案 §5.2）。确认策略按它分档。"""

    SAFE = "safe"
    MUTATING = "mutating"
    DESTRUCTIVE = "destructive"


class Concurrency(StrEnum):
    """并发语义。`EXCLUSIVE` 的工具在一个 turn 内串行执行（技术方案 §6.2 调度）。"""

    PARALLEL = "parallel"
    EXCLUSIVE = "exclusive"


class SideEffect(StrEnum):
    """副作用状态（§10.5、`EDG-401`、`EDG-407`）。

    `UNKNOWN` 是一等状态而不是兜底：工具超时、进程崩溃或取消宽限期用尽时，Kernel
    确实不知道外部世界变了没有，此时谎报 `NONE` 会让用户据此重试并造成重复副作用。
    """

    NONE = "none"
    OCCURRED = "occurred"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """工具声明（`TOL-001`）：名称、描述、输入 schema、输出语义与权限需求。

    `read_only` 与 `risk` 冗余但不重复：前者是给调度与缓存看的硬事实，后者是给确认
    策略看的分档。两者矛盾（只读却声称会破坏）时构造直接失败，不猜哪个是真的。
    """

    name: str
    description: str
    parameters: JsonSchema
    permissions: frozenset[PermissionKind] = frozenset()
    read_only: bool = False
    risk: RiskLevel = RiskLevel.MUTATING
    concurrency: Concurrency = Concurrency.PARALLEL

    def __post_init__(self) -> None:
        if not _TOOL_NAME_PATTERN.match(self.name):
            raise NucleaError(
                ErrorCode.INPUT_MALFORMED,
                "工具名形状非法（应形如 fs.read）。",
                detail={"name": self.name},
            )
        if not self.description:
            raise NucleaError(
                ErrorCode.INPUT_MALFORMED,
                "工具必须有描述——模型只能靠它决定是否调用。",
                detail={"name": self.name},
            )
        if self.read_only and self.risk is not RiskLevel.SAFE:
            raise NucleaError(
                ErrorCode.INPUT_MALFORMED,
                "只读工具的风险等级必须是 SAFE。",
                detail={"name": self.name, "risk": self.risk.value},
            )
        if self.read_only and PermissionKind.FS_WRITE in self.permissions:
            raise NucleaError(
                ErrorCode.INPUT_MALFORMED,
                "只读工具不得申请写权限。",
                detail={"name": self.name},
            )


@dataclass(frozen=True, slots=True)
class ToolCall:
    """模型发出的一次调用（§10.5「调用 ID / Tool 标识 / 符合 schema 的参数」）。

    刻意不含 `Correlation` 与超时：它要能原样放进 `ModelResponse`，而那里不该出现
    执行上下文。执行上下文由 `ToolInvocation` 承载。
    """

    call_id: str
    name: str
    arguments: Mapping[str, JsonValue] = EMPTY_METADATA

    def __post_init__(self) -> None:
        validate_identifier("tool_call.call_id", self.call_id)
        if not _TOOL_NAME_PATTERN.match(self.name):
            raise NucleaError(
                ErrorCode.INPUT_MALFORMED,
                "工具名形状非法（应形如 fs.read）。",
                detail={"call_id": self.call_id, "name": self.name},
            )
        object.__setattr__(
            self, "arguments", normalize_metadata(self.arguments, field="tool_call.arguments")
        )


@dataclass(frozen=True, slots=True)
class ToolInvocation:
    """一次调用的完整执行上下文（§10.5「Turn、Session 和调用方关联信息」）。

    `idempotency_key` 对应 `EDG-402`：可能重复提交的工具要么带幂等键，要么禁止自动
    重试。为 None 时执行器不得自动重试。
    """

    call: ToolCall
    correlation: Correlation
    timeout_ms: int
    granted: frozenset[PermissionKind] = frozenset()
    idempotency_key: str | None = None

    def __post_init__(self) -> None:
        if self.timeout_ms <= 0:
            raise NucleaError(
                ErrorCode.INPUT_MALFORMED,
                "工具超时必须为正——没有「永不超时」这个选项（KER-009）。",
                detail={"call_id": self.call.call_id, "timeout_ms": self.timeout_ms},
            )
        if self.idempotency_key is not None:
            validate_identifier("tool_invocation.idempotency_key", self.idempotency_key)

    @property
    def auto_retry_allowed(self) -> bool:
        """没有幂等键就不允许自动重试（`EDG-402`）。"""
        return self.idempotency_key is not None


@dataclass(frozen=True, slots=True)
class ArtifactRef:
    """工具产出的外部产物引用（§10.5「外部产物引用」）。

    与消息附件分开定义：附件面向 Channel 投递，产物面向 Workspace 与后续工具，
    合并成一个类型只会让两边都多出用不上的字段。
    """

    locator: str
    media_type: str
    description: str = ""
    size_bytes: int | None = None

    def __post_init__(self) -> None:
        validate_identifier("artifact.locator", self.locator, max_length=4096)
        if not self.media_type:
            raise NucleaError(
                ErrorCode.INPUT_UNSUPPORTED_MEDIA,
                "产物必须声明媒体类型。",
                detail={"locator": self.locator},
            )
        if self.size_bytes is not None and self.size_bytes < 0:
            raise NucleaError(
                ErrorCode.INPUT_MALFORMED,
                "产物大小不得为负。",
                detail={"locator": self.locator},
            )


@dataclass(frozen=True, slots=True)
class ToolResult:
    """一次调用的结果（§10.5 输出七条）。

    `content` 是**已经截断**的、供模型消费的有界文本；`data` 是可选的机器可读数据；
    `artifacts` 指向不适合进上下文的大产物（`TOL-003`）。
    `duration_ms` 与 `error.detail` 构成「安全的诊断信息」——堆栈不进这里，
    `NucleaError` 在构造时已完成脱敏。

    **`trust` 决定 `content` 进模型时要不要被包成不可信数据块**（`D42`）。
    在它之前，工具结果一律以裸文本进入 tool 消息，于是 `web.fetch` 抓回来的网页与
    `memory.recall` 召回的记录只能靠工具自己在正文里加一行**提醒性**横幅——
    那挡不住「忽略以上指令」，两个官方插件的 README 里都如实写着「是提醒不是隔离」。
    现在隔离由契约层完成（与 `ContextFragment` 同一个 `wrap_untrusted`），
    工具因此没有「自己拼一段文本混进去」的绕行路径。
    """

    call_id: str
    ok: bool
    content: str
    truncated: bool
    side_effect: SideEffect
    data: Mapping[str, JsonValue] | None = None
    artifacts: tuple[ArtifactRef, ...] = ()
    error: NucleaError | None = None
    duration_ms: int = 0
    #: **默认不可信**，因为绝大多数工具的产出里有外部内容（文件、命令输出、网页、
    #: 远端服务的响应）。默认值必须是安全的那一个：一个忘了表态的工具应当被包起来，
    #: 而不是默认拿到裸文本待遇。工具确信正文是自己的话时显式写 `SYSTEM`。
    trust: TrustLevel = TrustLevel.UNTRUSTED

    def __post_init__(self) -> None:
        validate_identifier("tool_result.call_id", self.call_id)
        if self.trust not in _TOOL_RESULT_TRUST:
            raise NucleaError(
                ErrorCode.INPUT_MALFORMED,
                "工具结果的 trust 只能是 SYSTEM 或 UNTRUSTED。",
                detail={"call_id": self.call_id, "trust": self.trust.value},
            )
        if self.ok != (self.error is None):
            raise NucleaError(
                ErrorCode.KERNEL_INVARIANT_VIOLATED,
                "工具结果的 ok 与 error 必须一致：失败必须带 error，成功不得带 error。",
                detail={"call_id": self.call_id, "ok": self.ok},
            )
        if len(self.content) > MAX_TOOL_RESULT_LENGTH:
            raise NucleaError(
                ErrorCode.INPUT_TOO_LARGE,
                "工具结果文本超过上限，应在执行器侧截断后再构造。",
                detail={
                    "call_id": self.call_id,
                    "length": len(self.content),
                    "limit": MAX_TOOL_RESULT_LENGTH,
                },
            )
        if self.duration_ms < 0:
            raise NucleaError(
                ErrorCode.KERNEL_INVARIANT_VIOLATED,
                "工具执行耗时不得为负。",
                detail={"call_id": self.call_id, "duration_ms": self.duration_ms},
            )
        if self.data is not None:
            object.__setattr__(
                self, "data", normalize_metadata(self.data, field="tool_result.data")
            )

    def as_model_text(self, *, source: str) -> str:
        """交给模型的最终文本。`UNTRUSTED` 的结果包成带来源标注的数据块。

        与 `ContextFragment.as_model_text()` 共用 `wrap_untrusted`，因此两条通路上的
        「不可信内容」在模型眼里长得一模一样——`EDG-306` 要的正是这个。

        **`source` 由调用方给，不是工具自己写的字段。** 折叠这条结果的是 Kernel，
        它知道这次调用的工具名（`ToolCall.name`）；让工具自报来源，等于把数据块上那句
        「这段东西是谁给的」也交给不可信的一方。

        **包裹在截断之后发生**，因此最终文本会比 `tool_result_max_bytes` 长出包装那几行。
        反过来（先包再截）会把闭合标记截掉，而一个没有闭合的数据块正是它要防的东西。
        """
        if self.trust is not TrustLevel.UNTRUSTED:
            return self.content
        return wrap_untrusted(self.content, source=source)
