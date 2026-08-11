"""能力接口：Kernel 与能力实现之间唯一的行为契约（技术方案 §5.1、需求 §9.3 `SDK-001`）。

职责：声明 8 个能力 Protocol（`ModelProvider` / `ToolHandler` / `ContextProvider` /
`SessionStore` / `MemoryProvider` / `Channel` / `CommandHandler` / `HookHandler`）与支撑用的
只读 `CancelSignal`，并在每个方法的 docstring 上固定写明**异常约定**与**取消语义**。
不负责：提供任何实现、决定调用顺序与重试、执行超时——实现在 `builtins/` 与 `plugins/`，
调度在 `kernel/`；本模块只有签名，函数体一律是 docstring + `...`。

三条本模块自身的规则：

- **结构化子类型，插件不继承宿主基类**。这是 `PLG-002`（插件不得通过导入 Kernel 私有
  模块获得隐式能力）在类型层的前提：能力实现只要形状对得上就能注册。
- **`runtime_checkable` 只用于诊断输出，不用于控制流**。它只查属性存在性，不查签名；
  拿它做分支等于把类型错误推迟到调用点。
- **取消一律通过 `CancelSignal` 观测，而不是捕获 `asyncio.CancelledError`**
  （技术方案 §6.4）。`CancelledError` 会在任意 await 点抛出，「保存已产生内容并标记为
  取消」这个语义在它下面无法实现。能力实现方拿到的只有观测面——`request()` 与
  `child()` 在 Kernel 侧的 `CancelToken`（`D08`）上，能力实现无权取消整个 turn。
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping, Sequence
from typing import Protocol, runtime_checkable

from .capability import HookContext, HookOutcome
from .command import CommandInvocation, CommandResult
from .context import ContextFragment, FragmentScope
from .ids import Correlation, SessionKey
from .message import InboundMessage, OutboundMessage
from .model import ModelChunk, ModelInfo, ModelRequest, ModelResponse
from .session import SessionMessage, SessionSnapshot
from .tool import ToolInvocation, ToolResult

__all__ = [
    "CancelSignal",
    "Channel",
    "CommandHandler",
    "ContextProvider",
    "HookHandler",
    "MemoryProvider",
    "ModelProvider",
    "SessionStore",
    "ToolHandler",
]


@runtime_checkable
class CancelSignal(Protocol):
    """取消信号的只读观测面（技术方案 §6.4）。

    `D08` 的 `kernel/turn/cancel.py::CancelToken` 结构化满足本 Protocol，并额外提供
    `request()` 与 `child()`。分成两个面是刻意的：能力实现需要知道「该停了」，
    但不该有能力替 Kernel 决定整个 turn 的终态。
    """

    @property
    def requested(self) -> bool:
        """是否已被请求取消。幂等查询，不抛异常。"""
        ...

    def raise_if_requested(self) -> None:
        """已请求取消则抛 `NucleaError(CANCELLED_BY_USER | CANCELLED_BY_BUDGET)`。

        **异常约定**：只抛 `CANCELLED` 类的 `NucleaError`，不抛其他类型。
        """
        ...


@runtime_checkable
class ModelProvider(Protocol):
    """模型供应商（需求 §9.5 `MOD-001`–`MOD-005`）。

    Provider 不得决定 Session、Memory 或 Channel 行为（`MOD-004`）：它拿到的是一份
    已经组装好的 `ModelRequest`，交回的是文本、Tool Call、终止原因与用量。
    """

    def describe(self, model_id: str) -> ModelInfo:
        """声明该模型的能力与窗口大小（`MOD-001`）。

        不具备的能力必须缺席 `ModelInfo.capabilities`，不得静默降级后假装支持
        （`MOD-005`）。

        **异常约定**：模型不存在抛 `CAPABILITY_MISSING`；配置缺失抛 `CONFIG_INVALID`。
        本方法是纯查询，不得发起网络请求——它在 turn 的预算推导路径上（`CTX-003`）。
        **取消语义**：同步方法，不涉及取消。
        """
        ...

    async def complete(self, request: ModelRequest, cancel: CancelSignal) -> ModelResponse:
        """一次非流式请求。

        **异常约定**：限流、超时、认证失败与内容过滤必须转换为可分类的 `NucleaError`
        （`MOD-003`）——分别是 `EXTERNAL_MODEL_PROVIDER`（`retryable` 如实标注）、
        `TIMEOUT_MODEL_REQUEST`、`CONFIG_SECRET_MISSING` / `PERMISSION_DENIED`，
        以及 `StopReason.CONTENT_FILTER` 的正常响应（内容过滤是结果不是异常）。
        供应商 SDK 的原生异常不得逸出本方法（`MSG-004` 的同类要求）。
        **取消语义**：进入网络调用前检查 `cancel`；调用期间被取消时抛
        `CANCELLED` 类错误，此时不得返回半份响应。
        """
        ...

    def stream(self, request: ModelRequest, cancel: CancelSignal) -> AsyncIterator[ModelChunk]:
        """一次流式请求，逐片产出增量。

        声明为普通 `def` 返回 `AsyncIterator` 而不是 `async def`，实现方因此可以直接
        写成异步生成器（`async def` + `yield`），不必额外包一层。

        **异常约定**：同 `complete()`；已经 yield 过分片后再失败，必须先 yield 一个
        `ChunkKind.DONE`（`stop_reason=ERROR`）再抛，让消费方能把已收到的文本按
        `interrupted=True` 持久化（技术方案 §6.4 检查点 3）。
        模型不支持流式时抛 `CAPABILITY_MISSING`，不得自行降级为一次性返回（`MOD-005`）。
        **取消语义**：每产出一片前检查 `cancel`；被取消时结束迭代并抛 `CANCELLED` 类
        错误，已 yield 的分片由调用方保留。
        """
        ...


@runtime_checkable
class ToolHandler(Protocol):
    """一个工具的执行体（需求 §9.9 `TOL-001`–`TOL-007`）。"""

    async def execute(self, invocation: ToolInvocation, cancel: CancelSignal) -> ToolResult:
        """执行一次调用并返回结果。

        **异常约定**：**约定不抛**。失败是一等结果，应返回
        `ToolResult(ok=False, error=...)`——`ok=False` 必须带 `error` 已由契约强制。
        确实逸出的异常会被 Kernel 记为 `ToolResult(ok=False, side_effect=UNKNOWN)`：
        Kernel 无从判断外部世界变了没有，只能如实说不知道（`EDG-401`、`EDG-407`）。
        堆栈不得进入 `content`——它是模型可见文本（§10.5 末段）。
        **取消语义**：在每个可能长时间阻塞的步骤前检查 `cancel`。取消后仍必须返回
        `ToolResult`，并如实标注 `side_effect`：确定没做返回 `NONE`，做了一半或不确定
        返回 `UNKNOWN`。Kernel 只等待 `tool_cancel_grace_ms`（默认 2000），超时后会
        自行写入 `tool.cancel_timeout` 结果并把本协程登记为孤儿任务（`EDG-407`）。
        """
        ...


@runtime_checkable
class ContextProvider(Protocol):
    """上下文片段的贡献者（需求 §9.6 `CTX-001`–`CTX-006`）。"""

    async def provide(
        self,
        snapshot: SessionSnapshot,
        correlation: Correlation,
        cancel: CancelSignal,
    ) -> tuple[ContextFragment, ...]:
        """为本次 turn 贡献片段。返回空元组表示无贡献，这不是错误。

        Provider 交出的是**片段**而不是最终文本：`trust`、`priority`、`sensitivity`
        与预算约束因此无法被绕过（`CMD-004`、`CMD-005`）。裁剪与排序由组装器负责，
        Provider 只需保证单个片段不超长并如实填写 `estimated_tokens`。

        **异常约定**：可以抛 `NucleaError`。是否致命由插件的 `critical` 决定：
        关键插件的异常让 turn `FAILED`，否则跳过本 Provider 并记录原因（`CTX-005`）。
        **取消语义**：在每个外部查询前检查 `cancel`；被取消时抛 `CANCELLED` 类错误，
        本次贡献整体作废——半份上下文比没有上下文更危险。
        """
        ...


@runtime_checkable
class SessionStore(Protocol):
    """会话历史的持久化实现（需求 §9.7 `SES-001`–`SES-006`）。

    同一 Session 的写入由 Kernel 的 session 锁保证单一写者（`KER-008`），因此实现方
    不需要自己做跨进程以外的并发控制，但**必须**保证单次写入的顺序与原子性
    （`SES-002`）。
    """

    async def load(self, key: SessionKey) -> SessionSnapshot:
        """读取会话全量视图。

        **异常约定**：会话不存在时返回空快照（`SessionSnapshot(session_key=key)`），
        **不抛**——「第一次说话」不是错误。读取失败或记录损坏抛 `PERSISTENCE_READ_FAILED`
        / `PERSISTENCE_RECORD_CORRUPT`，不得返回空快照冒充「没有历史」，那会让一次读盘
        故障静默清空用户的上下文。
        **取消语义**：读操作短暂，不接受取消。
        """
        ...

    async def append(self, key: SessionKey, messages: Sequence[SessionMessage]) -> None:
        """顺序追加记录，整批原子生效。

        **异常约定**：失败抛 `PERSISTENCE_WRITE_FAILED`，turn 随之标记 `FAILED`；
        不得吞掉异常伪装成功（`SES-003`）。部分写入必须回滚或以整体失败呈现。
        **取消语义**：写操作不接受取消——中途放弃会留下半份历史。
        """
        ...

    async def compact(self, key: SessionKey, through: int, summary: SessionMessage) -> None:
        """把前 `through` 条记录替换为摘要，推进压缩水位（`SES-005`）。

        原始记录是否物理删除由实现决定，但 `load()` 之后
        `SessionSnapshot.compacted_through` 必须等于 `through`。

        **异常约定**：`through` 越界抛 `INPUT_MALFORMED`；写失败同 `append()`。
        **取消语义**：不接受取消。
        """
        ...

    async def delete(self, key: SessionKey) -> bool:
        """删除会话，返回是否真的存在过（`SES-005`）。

        **异常约定**：不存在返回 `False`，不抛；删除失败抛 `PERSISTENCE_WRITE_FAILED`。
        **取消语义**：不接受取消。
        """
        ...

    async def list_keys(self) -> tuple[SessionKey, ...]:
        """列出全部会话标识，供 `/session` 命令与迁移工具使用（`SES-004`）。

        **异常约定**：读取失败抛 `PERSISTENCE_READ_FAILED`；单条记录损坏应跳过并记录，
        不得让一条坏记录使整个列表不可用。
        **取消语义**：不接受取消。
        """
        ...


@runtime_checkable
class MemoryProvider(Protocol):
    """跨 Session 的长期记忆（需求 §9.8 `MEM-001`–`MEM-005`）。

    Kernel 只依赖本接口，不假设文件、向量或图数据库（`MEM-001`）。写入与检索的载荷
    都是 `ContextFragment`：它自带 `source`、`trust`、`scope`、`sensitivity` 与
    `expires_at`，恰好覆盖 `MEM-002`（范围）与 `MEM-004`（来源与可信度标记），
    而且召回结果可以直接进上下文，不需要中间形态。
    """

    async def remember(self, fragment: ContextFragment, cancel: CancelSignal) -> str:
        """写入一条记忆，返回稳定的记录标识。

        **异常约定**：写失败抛 `PERSISTENCE_WRITE_FAILED`。模型生成内容应以
        `trust=UNTRUSTED` 写入——召回时会被包裹为数据块，不获得指令优先级（`EDG-306`）。
        **取消语义**：写操作不接受取消。
        """
        ...

    async def recall(
        self,
        query: str,
        *,
        scope: FragmentScope,
        limit: int,
        cancel: CancelSignal,
    ) -> Mapping[str, ContextFragment]:
        """按相关性召回记忆，返回 `记录标识 -> 片段` 的有序映射。

        用映射而不是元组，是为了让调用方在不引入第三个类型的前提下拿到记录标识
        （`MEM-005` 的「查询、修正、删除」都需要它）。**顺序即相关性排序**，
        实现方必须按相关性从高到低插入。

        **异常约定**：后端不可用抛 `EXTERNAL_SERVICE` 类错误；Kernel 按配置降级为
        无长期记忆模式继续对话（`MEM-003`），因此本方法不得为了「保证可用」而返回空结果
        掩盖故障。
        **取消语义**：检索前与每次外部往返后检查 `cancel`，被取消时抛 `CANCELLED` 类错误。
        """
        ...

    async def forget(self, record_id: str) -> bool:
        """删除一条记忆，返回是否真的存在过（`MEM-005`）。

        「修正」不单列方法：`forget()` + `remember()` 的组合语义明确，而原地修改会让
        「这条记忆是什么时候、由谁写的」变得不可追溯。

        **异常约定**：不存在返回 `False`，不抛；删除失败抛 `PERSISTENCE_WRITE_FAILED`。
        **取消语义**：不接受取消。
        """
        ...


@runtime_checkable
class Channel(Protocol):
    """外部平台接入（需求 §9.4 `MSG-001`–`MSG-007`）。

    归一化在 Channel 边界完成：原始 SDK 对象不得进入 Kernel（`MSG-004`）。
    入站用**拉模型**（`receive()` 产出异步迭代器）而不是回调注册，因为拉模型让
    「谁在消费、什么时候停」直接由 Kernel 的任务结构表达，不需要再定义一个提交回调
    Protocol 和它的错误语义。
    """

    @property
    def channel_id(self) -> str:
        """本 Channel 的稳定标识，构成 `SessionKey.channel_id`（`SES-001`）。"""
        ...

    async def start(self) -> None:
        """建立与平台的连接。

        **异常约定**：失败抛 `EXTERNAL_CHANNEL`；实例是否因此启动失败由插件的
        `critical` 决定（`PLG-004`）。
        **取消语义**：不接受取消；连接失败应快速返回而不是无限重试。
        """
        ...

    async def stop(self) -> None:
        """断开连接并释放资源。

        **异常约定**：**约定不抛**。停止阶段的异常只会拖住整个实例退出；实现应内部
        记录并返回。Kernel 对每个能力的停止有独立超时，超时即放弃等待（`EDG-104`）。
        **取消语义**：不接受取消。
        """
        ...

    def receive(self) -> AsyncIterator[InboundMessage]:
        """产出归一化后的入站消息，直到 `stop()` 被调用。

        **异常约定**：平台侧的可恢复错误应内部重试并继续迭代；不可恢复错误抛
        `EXTERNAL_CHANNEL` 并结束迭代。畸形消息应丢弃并记录，不得让一条坏消息终止整个
        Channel（`MSG-004`）。
        **取消语义**：迭代由 `stop()` 或消费方取消结束，不接受 `CancelSignal`——
        它是实例级长生命周期服务，不属于任何单个 turn。
        """
        ...

    async def deliver(self, message: OutboundMessage) -> None:
        """投递一条出站消息。

        消息自带 `channel_id + conversation_id + turn_id`，实现方不需要维护自己的
        Session 映射（`MSG-006`）。平台长度上限、附件限制与流式能力差异由实现方处理，
        必要时降级为分段或只发最终结果（`MSG-003`、`MSG-005`）。
        `message.is_complete_answer` 为假时必须附加明确标记，不得渲染成完整回答
        （`EDG-304`）。

        **异常约定**：投递失败抛 `EXTERNAL_CHANNEL` 并如实标注 `retryable`。
        **取消语义**：不接受取消——投递是 turn 的最后一步，此时取消只会让用户什么也收不到。
        """
        ...


@runtime_checkable
class CommandHandler(Protocol):
    """斜杠命令的执行体（需求 §9.13 `CMD-001`–`CMD-005`）。"""

    async def handle(self, invocation: CommandInvocation, cancel: CancelSignal) -> CommandResult:
        """执行命令。

        **异常约定**：**约定不抛**。失败应返回
        `CommandResult(disposition=REJECTED, error=...)`——命令处理失败不得导致实例退出，
        必须返回可诊断错误并保持会话可用（`CMD-003`）。逸出的异常由 Kernel 捕获为同形状的
        结果，但那样就丢掉了实现方本可以给出的具体说明。
        **取消语义**：命令通常短暂；长耗时命令应在每步前检查 `cancel`，被取消时返回
        `REJECTED` 并在 `error` 中说明，而不是抛出。
        """
        ...


@runtime_checkable
class HookHandler(Protocol):
    """生命周期与流水线扩展点（技术方案 §6.6）。"""

    async def handle(self, context: HookContext) -> HookOutcome | None:
        """处理一次 Hook 分发。返回 `None` 等价于 `HookAction.CONTINUE`。

        Observer 的返回值一律被忽略——它按定义不影响 turn，所以最自然的实现就是返回
        `None`。Interceptor 的返回值按 `HookAction` 采纳，具体取哪一份载荷见
        `HookAction.REPLACE` 的说明。

        **异常约定**：**handler 不应抛出异常，抛出被视为插件故障并被隔离。**
        Observer 的异常与超时只记 `PLUGIN_FAILURE` 事件，不影响 turn 结果（`NFR-204`）；
        Interceptor 的异常按插件关键性区分：`critical=true` 让 turn `FAILED`，否则跳过
        该 handler、记录原因后继续（`PLG-004`、`EDG-106`、`CTX-005`）。
        **取消语义**：不接受 `CancelSignal`。Hook 有自己的独立超时
        （observer 2000ms / interceptor 5000ms），超时即按上面的隔离规则处理；
        把 turn 的取消信号交给 Hook 只会诱导它在 `turn_end` 这类清理点提前退出。
        """
        ...
