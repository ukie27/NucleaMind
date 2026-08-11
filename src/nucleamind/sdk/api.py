"""Host API：插件与 Kernel 之间的注册面与受限运行时（技术方案 §7.5）。

职责：声明 `NucleaAPI`（恰好 9 个注册方法 + `ctx`）、受限的 `PluginContext` 及其四个
资源访问器 Protocol（`fs` / `net` / `shell` / `secret`），以及配套的 `SecretStr`、
`HttpResponse`、`ShellResult`。
不负责：实现注册与冲突判定（`kernel/registry/`，`D06`）、构造 `PluginContext` 与执行
权限判定（`kernel/plugins/`，`D26`）、决定谁被加载（`D27`）。本模块只有签名与两个纯数据
类型，函数体一律是 docstring + `...`。

三件必须在这一层说清楚的事：

- **9 个注册方法与 `CapabilityKind` 的 9 个取值一一对应**，不多不少。多出一个方法就等于
  多出一类没有冲突语义的能力（`CAPABILITY_ARITY` 会 KeyError），少一个就等于某类能力
  只能靠 Kernel 内部特权注册——那正是 `BAS-005`「内建能力不享受特权」要堵的路。
- **权限是声明式 + 应用级强制，不是进程隔离**。访问器只在 manifest 声明且配置授权后
  才会被构造，否则属性访问抛 `PERMISSION_DENIED`。但同进程 Python 插件可以绕过这些门面
  直接 `import os`——这不是隐含前提，是必须写在文档里的诚实声明（技术方案 §7.5、§13.7）。
  它的价值是让越界意图可审计、在评审与测试中可见，真正的隔离要等 P2 的子进程插件宿主。
- **后台任务只能经 `ctx.spawn_task()` 创建**。Host API 不暴露裸 `asyncio.create_task`，
  否则「这个任务是谁的」在禁用插件时就无从判定，`EDG-105` 的痕迹清理也就无从谈起。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from logging import Logger
from pathlib import Path
from typing import Protocol, runtime_checkable

from nucleamind.contracts import (
    Channel,
    CliEntry,
    CommandHandler,
    CommandSpec,
    ContextProvider,
    EventName,
    HookHandler,
    HookName,
    JsonValue,
    MemoryProvider,
    ModelProvider,
    RuntimeEvent,
    SessionStore,
    ToolHandler,
    ToolSpec,
)
from nucleamind.contracts.errors import MASK

__all__ = [
    "EventHandler",
    "EventSubscriber",
    "FileAccess",
    "HttpAccess",
    "HttpResponse",
    "NucleaAPI",
    "PluginContext",
    "SecretStr",
    "ShellAccess",
    "ShellResult",
]

#: 事件订阅的回调形状。返回 `None` 的协程：订阅者是观察者，没有可被采纳的返回值。
EventHandler = Callable[[RuntimeEvent], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class SecretStr:
    """密钥的包装类型：默认渲染为掩码，明文只能经 `reveal()` 取出。

    自己定义而不是复用 pydantic 的同名类型：`contracts.errors` 用 `MASK` 作为全局统一
    掩码，两套掩码会让「哨兵值扫全部 sink 输出」这条 CI 检查出现第二种期望值。

    它**不是**安全边界——插件当然可以 `reveal()` 之后随手打印。它防的是最常见的那条
    泄漏路径：顺手把凭据拼进日志、prompt 或异常消息。`reveal()` 的调用点同时是审计与
    grep 的抓手：明文从哪里开始流动是可查的。
    """

    _value: str

    def reveal(self) -> str:
        """取出明文。调用点即「这里开始承担泄漏风险」的标记。"""
        return self._value

    def __str__(self) -> str:
        return MASK

    def __repr__(self) -> str:
        return f"SecretStr({MASK})"


@dataclass(frozen=True, slots=True)
class HttpResponse:
    """一次 HTTP 往返的结果（经 SSRF 守卫后）。

    `body` 保持 `bytes`：解码是调用方的事，替它猜编码只会在非 UTF-8 站点上悄悄出错。
    """

    status: int
    headers: Mapping[str, str]
    body: bytes


@dataclass(frozen=True, slots=True)
class ShellResult:
    """一次子进程执行的结果。

    `timed_out=True` 时 `exit_code` 无意义——进程是被杀掉的，不是自己退出的，
    副作用是否已经发生同样不可知（对应 `SideEffect.UNKNOWN` 的判断依据）。
    """

    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False


@runtime_checkable
class FileAccess(Protocol):
    """文件访问门面，需要 `fs:read` / `fs:write` 权限（§7.5、`EDG-405`）。

    所有路径都相对于插件被授予的根，解析后必须落在允许根内（`realpath` 之后重新校验，
    覆盖符号链接、`..`、Windows 大小写与重解析点）。绝对路径一律拒绝——接受绝对路径就
    等于把「根在哪」的决定权交给了调用方。
    """

    async def read_text(self, path: str) -> str:
        """读取文本文件（UTF-8）。

        **异常约定**：越界抛 `PERMISSION_PATH_OUTSIDE_WORKSPACE`；未授权抛
        `PERMISSION_DENIED`；不存在或读失败抛 `PERSISTENCE_READ_FAILED`。
        """
        ...

    async def write_text(self, path: str, content: str) -> None:
        """原子写入文本文件（临时文件 + 替换），需要 `fs:write`。

        **异常约定**：同 `read_text()` 的越界与授权规则；写失败抛
        `PERSISTENCE_WRITE_FAILED`。不得留下半份文件。
        """
        ...

    async def list_dir(self, path: str) -> tuple[str, ...]:
        """列出目录下的条目名（不递归）。

        **异常约定**：同 `read_text()`。目录不存在抛 `PERSISTENCE_READ_FAILED`，
        空目录返回空元组——「空」和「没有」是两回事。
        """
        ...


@runtime_checkable
class HttpAccess(Protocol):
    """出网门面，需要 `net` 权限，内部走 SSRF 守卫（§7.5、`EDG-406`）。"""

    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        body: bytes | None = None,
        timeout_ms: int = 30_000,
    ) -> HttpResponse:
        """发起一次 HTTP 请求。

        解析出的 IP 与**每一次重定向**的目标都会被重新校验，私有网段与云元数据地址一律
        拒绝。这是插件唯一的出网路径：直接用 httpx 当然也能连出去，但那样就绕过了守卫，
        评审时能一眼看见（这正是应用级权限的意义）。

        **异常约定**：未授权抛 `PERMISSION_DENIED`；目标被守卫拒绝抛
        `PERMISSION_DENIED` 并在 `detail` 说明原因；网络失败抛 `EXTERNAL_SERVICE` 类错误
        并如实标注 `retryable`；超时抛 `TIMEOUT` 类错误。**非 2xx 不是异常**——它是结果，
        由调用方按业务判断。
        """
        ...


@runtime_checkable
class ShellAccess(Protocol):
    """子进程门面，需要 `shell` 权限（§7.5、`EDG-404`、`NFR-605`）。"""

    async def run(
        self,
        command: Sequence[str],
        *,
        cwd: str | None = None,
        timeout_ms: int = 60_000,
    ) -> ShellResult:
        """执行一条命令。参数是**列表**而不是命令行字符串，因此不存在 shell 注入面。

        默认 cwd 限定在 workspace，默认不继承敏感环境变量。Windows 与 Linux 的命令构造
        分别实现，但对外行为契约一致：同样的参数给出同样的退出码语义、同样的输出截断
        规则、同样的超时行为。

        **异常约定**：未授权抛 `PERMISSION_DENIED`；cwd 越界抛
        `PERMISSION_PATH_OUTSIDE_WORKSPACE`；**非零退出码不是异常**，它在
        `ShellResult.exit_code` 里。超时同样不抛，返回 `timed_out=True` 的结果——
        调用方需要拿到超时前已产生的输出。
        """
        ...


@runtime_checkable
class EventSubscriber(Protocol):
    """事件订阅面（技术方案 §6.8）。订阅在插件被禁用时由 Kernel 统一取消（`EDG-105`）。"""

    def subscribe(self, event: EventName, handler: EventHandler) -> None:
        """订阅一个事件名。同一 handler 重复订阅同一事件视为一次。

        没有 `unsubscribe`：订阅的生命周期就是插件的生命周期，让插件自行退订只会多出
        「退订了但任务还在跑」这种中间状态。需要临时静音就在 handler 里判断。

        **异常约定**：事件名未登记抛 `INPUT_MALFORMED`（`EventName` 是冻结枚举，
        传进来的一定是它的成员，因此这条只在跨版本反序列化时才可能触发）。
        handler 自身的异常由 Kernel 隔离并记 `PLUGIN_FAILURE`，不影响事件发布。
        """
        ...


@runtime_checkable
class PluginContext(Protocol):
    """插件拿到的受限运行时（§7.5）。

    四个资源访问器是 `property` 而不是方法：**未授权时属性访问就抛**
    `PERMISSION_DENIED`，插件拿不到一个「看起来能用、调用才失败」的对象。这让越权在
    第一次触碰时就暴露，而不是在某个罕见分支里。
    """

    @property
    def plugin_id(self) -> str:
        """本插件的稳定 id，与 manifest 一致。"""
        ...

    @property
    def config(self) -> Mapping[str, JsonValue]:
        """**只有自己那一块**配置（`CFG-002`）。没有读取他人配置的 API，也不打算有。"""
        ...

    @property
    def state_dir(self) -> Path:
        """`<instance_dir>/plugins/<id>/`，已创建。插件的持久化数据只应写在这里，
        卸载时按 `state_version` 与用户选择整体处理（`EDG-105`、§10.5）。"""
        ...

    @property
    def logger(self) -> Logger:
        """已绑定 `plugin_id` 的 logger，输出自动脱敏（`contracts.errors` 的规则）。"""
        ...

    @property
    def events(self) -> EventSubscriber:
        """事件订阅面。它不需要权限声明：事件流是只读的可观测性，不是资源访问。"""
        ...

    def spawn_task(self, coro: Awaitable[None], *, name: str) -> None:
        """在本插件的 task group 下创建后台任务。

        这是插件创建后台任务的**唯一**途径。`name` 必填且会出现在诊断里——一个匿名的
        挂起任务和一个没有任务是同一种排查体验。

        **异常约定**：插件已进入停止流程时抛 `KERNEL_INVARIANT_VIOLATED`。任务自身的
        异常由 Kernel 捕获并记 `PLUGIN_FAILURE`，不会冒泡到别的插件或 turn。
        **取消语义**：插件被停止或禁用时，其全部任务被 `cancel()`，随后按
        `plugin_stop_timeout_ms` 等待，超时即放弃等待并继续停止流程（`EDG-104`）。
        """
        ...

    @property
    def fs(self) -> FileAccess:
        """文件访问器。需要 `fs:read` / `fs:write` 权限，否则**属性访问**抛
        `PERMISSION_DENIED`。"""
        ...

    @property
    def net(self) -> HttpAccess:
        """出网访问器。需要 `net` 权限，否则属性访问抛 `PERMISSION_DENIED`。"""
        ...

    @property
    def shell(self) -> ShellAccess:
        """子进程访问器。需要 `shell` 权限，否则属性访问抛 `PERMISSION_DENIED`。"""
        ...

    def secret(self, name: str) -> SecretStr:
        """取一个凭据。需要 `secret:<name>` 权限。

        **异常约定**：未声明或未授权抛 `PERMISSION_DENIED`；已授权但配置里没有该值抛
        `CONFIG_SECRET_MISSING`——两者必须可区分，否则用户不知道该去改权限还是去补配置。
        返回值默认渲染为掩码，明文需 `reveal()`。
        """
        ...


@runtime_checkable
class NucleaAPI(Protocol):
    """插件的注册面（§7.5）。**恰好 9 个注册方法 + `ctx`**。

    形态对应 Pi 的 `ExtensionAPI`：`setup(api)` 拿到它，在**同步返回前**完成全部注册。
    注册先进 `RegistrationBatch` 暂存区，`setup` 正常返回才一次性并入 registry；中途抛
    异常则整批丢弃，registry 不留半注册状态（`EDG-103`）。因此「注册」不是立即生效的
    副作用，插件也不该在 `setup` 之后再回头注册——那时批次已经提交，registry 已冻结。

    声明式扩展（`SDK-006`）不需要新方法：Skill、Prompt 片段与斜杠命令的文本模板都通过
    `register_context_provider` / `register_command` 承载，内容以 `ContextFragment` 形式
    提交，因此天然受 `trust`、`priority` 与预算约束（`CMD-004`、`CMD-005`）。
    """

    @property
    def ctx(self) -> PluginContext:
        """本插件的受限运行时。"""
        ...

    def register_tool(self, spec: ToolSpec, handler: ToolHandler) -> None:
        """注册一个工具（`CapabilityKind.TOOL`，MULTI_UNIQUE）。

        能力名取自 `spec.name`，因此工具的声明与注册不可能对不上。

        **异常约定**：名字冲突且未在 manifest 声明 `overrides` 时抛
        `PLUGIN_REGISTRATION_CONFLICT`；批次已提交后再注册抛 `KERNEL_INVARIANT_VIOLATED`。
        """
        ...

    def register_command(self, spec: CommandSpec, handler: CommandHandler) -> None:
        """注册一个斜杠命令（`CapabilityKind.COMMAND`，MULTI_UNIQUE）。

        `spec.all_names`（命令名 + 别名）整体参与冲突检查（`CMD-002`）。

        **异常约定**：同 `register_tool()`。
        """
        ...

    def register_context_provider(self, name: str, provider: ContextProvider) -> None:
        """注册一个上下文贡献者（`CapabilityKind.CONTEXT`，MULTI）。

        MULTI 意味着同名可以并存、全部生效，按 `(priority, provider)` 排序，
        因此这里的 `name` 是诊断标签而不是唯一键。

        **异常约定**：批次已提交后再注册抛 `KERNEL_INVARIANT_VIOLATED`。
        """
        ...

    def register_model_provider(self, name: str, provider: ModelProvider) -> None:
        """注册一个模型供应商（`CapabilityKind.MODEL`，MULTI_UNIQUE）。

        **异常约定**：同 `register_tool()`。
        """
        ...

    def register_channel(self, name: str, channel: Channel) -> None:
        """注册一个外部平台接入（`CapabilityKind.CHANNEL`，MULTI_UNIQUE）。

        Channel 是长生命周期服务：注册只是登记，`start()` 由 Runtime 在阶段 D 按拓扑序
        调用，插件不应在 `setup` 里自己连线。

        **异常约定**：同 `register_tool()`。
        """
        ...

    def register_memory_provider(self, name: str, provider: MemoryProvider) -> None:
        """注册一个长期记忆实现（`CapabilityKind.MEMORY`，MULTI_UNIQUE）。

        带 `name` 即意味着可以并存多个具名实现：`MEM-003` 的降级要求换一个后端不必先
        卸载现有的。

        **异常约定**：同 `register_tool()`。
        """
        ...

    def register_session_store(self, name: str, store: SessionStore) -> None:
        """注册会话存储实现（`CapabilityKind.SESSION_STORE`，SINGLETON）。

        SINGLETON：全实例只有一个生效实现，替换必须在 manifest 显式声明 `overrides`。
        会话历史是用户资产，「装上就换掉」这种语义不该由加载顺序决定。

        **异常约定**：已有实现且未声明覆盖时抛 `PLUGIN_REGISTRATION_CONFLICT`。
        """
        ...

    def register_cli_entry(self, name: str, entry: CliEntry) -> None:
        """注册本地命令行入口（`CapabilityKind.CLI_ENTRY`，SINGLETON）。

        CLI 入口不可禁用（`BAS-009`、`BAS-010`）：不装任何 Channel 插件也必须存在本地
        交互入口。插件可以覆盖内建实现，但覆盖实现加载失败时 Runtime 强制回落到内建实现
        而不是让实例失去入口（`EDG-108`）。

        **异常约定**：同 `register_session_store()`。
        """
        ...

    def on(self, hook: HookName, handler: HookHandler, *, priority: int = 100) -> None:
        """订阅一个 Hook（`CapabilityKind.HOOK`，MULTI）。

        `hook` 是冻结的 10 个之一；它是 observer 还是 interceptor 由 `HOOK_KINDS` 决定，
        不由注册方选择——同一个 Hook 对不同插件有不同语义，失败隔离规则就无法自洽。

        **异常约定**：批次已提交后再注册抛 `KERNEL_INVARIANT_VIOLATED`。
        handler 自身的异常由 Kernel 按 `HookKind` 与插件的 `critical` 隔离处理
        （`NFR-204`、`PLG-004`），不在注册时体现。
        """
        ...
