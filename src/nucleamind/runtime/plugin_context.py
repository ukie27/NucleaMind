"""生产级 `PluginContext`：内建与插件在运行期真正拿到的那个受限运行时（技术方案 §7.5）。

职责：把实例的配置块、私有状态目录、事件总线、凭据引用与 `D22` 的两个门面
（`InstanceView` / `TurnControl`）装成一个 `PluginContext`，并按**已批准**的权限挡住四个
资源访问器。
不负责：决定谁被授予什么（`kernel/plugins/permissions.py` 的账本）、实现 `fs` / `net`
/ `shell` 三个门面的行为（`runtime/access/`）、决定谁被加载（`D25`/`D27`）。

**这里是 `R5` 的落点**，与 `wiring.py` / `introspection.py` 同一条理由：`PluginContext`
的类型在 `sdk/`，而 config 块、`InstanceLayout` 与 `EventBus` 在 `kernel/`——全项目只有
`runtime/` 同时看得见两边。一致性靠 `build_plugin_context()` 的返回类型标注静态证明。

**权限 = manifest 声明 ∩ 账本批准**（`D26`）：`PluginGrants` 由装配根从
`PermissionLedger.decide()` 拿到并传进来，本类只问它、不问 manifest。因此「声明了但用户
没批准」与「根本没声明」在这里是同一种结局（`PERMISSION_DENIED`），靠 `detail` 里的
`reason` 区分——两者的补救动作不同：前者敲 `nm permissions grant`，后者要改 manifest。

**三个资源门面是真身**（`runtime/access/`），但它们**不是进程隔离**：同进程 Python 插件
可以绕过它们直接 `import os`。这条诚实声明写在 `sdk/api.py`、`runtime/access/__init__.py`
与技术方案 §13.7，不是隐含前提。六个内建一个都不用它们（`session_jsonl` 用 `pathlib`、
`model_openai` 用 httpx、`tools_shell` 自己起子进程，各自如实声明权限，见 `D17`/`D19`/`D21`）。

**`instance` / `turns` 经一个可变持有者交下来**（`PluginRuntime`）：它们要等 registry 冻结
与 orchestrator 装好之后才存在，而 `PluginContext` 必须在 `setup()` **之前**就交给插件。
`D22` 的 `commands_source` 是 callable 也是同一条理由——那次是测试先发现的
（构造时收快照会让 `/help` 永远为空）。
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Mapping
from dataclasses import dataclass, field
from logging import Logger, getLogger
from pathlib import Path

from nucleamind.contracts import (
    ErrorCode,
    EventName,
    InstanceView,
    JsonValue,
    NucleaError,
    PermissionKind,
    RuntimeEvent,
    SecretStr,
    TurnControl,
)
from nucleamind.kernel.config import resolve_text
from nucleamind.kernel.observability import EventBus, Subscription
from nucleamind.kernel.plugins import PluginGrants
from nucleamind.sdk import EventHandler, FileAccess, HttpAccess, PluginContext, ShellAccess

from .access import GuardedFileAccess, GuardedHttpAccess, GuardedShellAccess

__all__ = [
    "PluginEventBridge",
    "PluginGrants",
    "PluginRuntime",
    "RuntimePluginContext",
    "build_plugin_context",
]


@dataclass(slots=True)
class PluginRuntime:
    """装配根与插件之间的**可变**交接点。

    只有两个成员，且都在 registry 冻结之后才填得上。做成一个共享对象而不是给每个 ctx
    各塞一个 setter，是为了让「实例就绪」这件事只有一个开关。
    """

    instance_view: InstanceView | None = None
    turn_control: TurnControl | None = None

    def ready(self, *, instance_view: InstanceView, turn_control: TurnControl) -> None:
        self.instance_view = instance_view
        self.turn_control = turn_control


class PluginEventBridge:
    """把插件的 handler 接到 `EventBus` 的同步订阅面上。

    `bus.publish()` 是同步的、绝不 await 订阅者（`D12` 的结论），而插件的 handler
    **可以是同步的也可以是协程**（`sdk.EventHandler`）。两种形状各走一条路：

    - **同步 handler 就地跑完**。它与 bus 的原生订阅者形状完全相同，派生一条 Task
      只会把它的异常挪进一个无人认领的地方。
    - **协程 handler 在回调里 `create_task`**，没有运行中的事件循环就记一次丢弃——
      `publish()` 会在没有 loop 的路径上被调用（`instance.starting`、`nm config show`），
      在那里凭空起一个 loop 才是错的。**同步 handler 因此在无 loop 的路径上仍然会跑**，
      这是它相对协程 handler 的实际优势，不是不一致。

    **`D41` 之前只有第二条路**：`handler(event)` 的返回值被无条件喂给 `create_task`，
    同步 handler 于是先被正常调用、再在一条 Task 里 `await None` 抛 `TypeError`。
    官方插件 `feishu` 与 `openai-api` 都撞在这上面。见 `sdk/api.py::EventHandler`。
    """

    def __init__(self, bus: EventBus, plugin_id: str) -> None:
        self._bus = bus
        self._plugin_id = plugin_id
        self._handlers: dict[EventName, list[EventHandler]] = {}
        self._subscription: Subscription | None = None
        #: 没有事件循环时被丢弃的**协程**投递数。查得到才排查得动。
        self.dropped = 0
        #: 已派生的任务，实例停止时由装配根一并取消。
        self.tasks: set[asyncio.Task[None]] = set()

    def subscribe(self, event: EventName, handler: EventHandler) -> None:
        handlers = self._handlers.setdefault(event, [])
        if handler in handlers:
            return
        handlers.append(handler)
        if self._subscription is None:
            self._subscription = self._bus.subscribe(
                self._deliver, name=f"plugin:{self._plugin_id}"
            )

    def close(self) -> None:
        """退订并停止接受新的投递（`EDG-105` 的「取消其事件订阅」）。

        **握着 `Subscription` 就是为了这一刻**：`bus.subscribe()` 返回的句柄是退订的唯一
        途径，丢掉它，一个已停止的插件的 handler 会跟着实例活到进程结束。
        handler 表一并清空——`cancel()` 之后 bus 不再扇出，但清掉它让「停过了」在这个
        对象自己身上也是可判定的。
        """
        if self._subscription is not None:
            self._subscription.cancel()
            self._subscription = None
        self._handlers.clear()

    def _deliver(self, event: RuntimeEvent) -> None:
        handlers = self._handlers.get(event.name)
        if not handlers:
            return
        loop: asyncio.AbstractEventLoop | None
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        for handler in handlers:
            # 同步 handler 的返回值是 `None`，协程 handler 的是 `Awaitable[None]`。
            # **判据是返回值而不是 `iscoroutinefunction(handler)`**：后者认不出
            # `functools.partial`、`__call__` 是 async 的可调用对象，以及返回协程的
            # 普通函数——而这三种都在 `EventHandler` 的类型里。
            pending = handler(event)
            if pending is None:
                continue
            if loop is None:
                self.dropped += 1
                _close_unawaited(pending)
                continue
            task: asyncio.Task[None] = loop.create_task(_as_coroutine(pending))
            self.tasks.add(task)
            task.add_done_callback(self.tasks.discard)


@dataclass(slots=True)
class RuntimePluginContext:
    """`PluginContext` 的生产实现。结构化满足契约，不继承任何宿主基类。"""

    plugin_id_: str
    config_: Mapping[str, JsonValue]
    state_dir_: Path
    grants: PluginGrants
    secret_refs: Mapping[str, str]
    bridge: PluginEventBridge
    runtime: PluginRuntime
    env: Mapping[str, str] | None = None
    #: 资源门面的根：实例的 workspace（与 `tools_fs` 同一个根）。`None` 时三个门面一律
    #: 抛 `CAPABILITY_MISSING`——那只发生在没有布局可言的调用点（测试与 `nm config show`），
    #: 授权与否在此之前已经判过。
    workspace: Path | None = None
    #: `config.json` 的路径。只用来让缺凭据的错误指得出「去改哪个文件」（`BAS-006`）；
    #: 本类**从不打开它**——配置的读取只在 `kernel/config/sources.py` 一处。
    config_path: Path | None = None
    #: 经 `spawn_task()` 派生的任务。实例停止时由装配根取消（`EDG-104`、`EDG-105`）。
    tasks: set[asyncio.Task[None]] = field(default_factory=set)
    #: 是否已进入停止流程。进去之后 `spawn_task()` 一律拒绝——`sdk/api.py` 写死的约定，
    #: 否则一个在 `instance.shutdown` Hook 里派生任务的插件会正好逃过刚刚那轮取消。
    stopping: bool = False

    @property
    def plugin_id(self) -> str:
        return self.plugin_id_

    @property
    def config(self) -> Mapping[str, JsonValue]:
        """**只有自己那一块**（`CFG-002`）：`plugins.<id>.config` 原样交出。"""
        return self.config_

    @property
    def state_dir(self) -> Path:
        """`<instance_dir>/plugins/<id>/`。**这里才创建它**——装配根不为一个可能从未写盘
        的插件先建目录（`nm capabilities` 不该在磁盘上留痕）。"""
        self.state_dir_.mkdir(parents=True, exist_ok=True)
        return self.state_dir_

    @property
    def logger(self) -> Logger:
        return getLogger(f"nucleamind.plugin.{self.plugin_id_}")

    @property
    def events(self) -> PluginEventBridge:
        return self.bridge

    def spawn_task(self, coro: Awaitable[None], *, name: str) -> None:
        """在实例的事件循环上派生一个后台任务。

        **异常约定**：没有运行中的事件循环时抛 `KERNEL_INVARIANT_VIOLATED`——`setup()`
        在装配期同步执行，那时派生后台任务就是在赌一个还不存在的循环。插件已进入停止
        流程时同样抛它（`sdk/api.py` 的约定）：那时派生的任务不在任何一轮取消的覆盖
        范围里，而「停干净了」不能有例外（`EDG-105`）。
        """
        if self.stopping:
            _close_unawaited(coro)
            raise NucleaError(
                ErrorCode.KERNEL_INVARIANT_VIOLATED,
                "插件已进入停止流程，不能再派生后台任务。",
                detail={"plugin": self.plugin_id_, "task": name},
            )
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError as exc:
            raise NucleaError(
                ErrorCode.KERNEL_INVARIANT_VIOLATED,
                "当前没有运行中的事件循环，无法派生后台任务。",
                detail={"plugin": self.plugin_id_, "task": name},
            ) from exc
        task: asyncio.Task[None] = loop.create_task(
            _as_coroutine(coro), name=f"{self.plugin_id_}:{name}"
        )
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    # `NucleaError.capability` 收的是 `CapabilityRef`（kind + name），而这里的主语是**提供方**
    # 而不是某一项能力——`plugin` 键放在 `detail` 里，比硬凑一个 kind 诚实。
    def _require(self, *permissions: PermissionKind) -> None:
        """任意一项被授予即放行。

        `fs` 收两项（`fs:read` / `fs:write`）：只声明了写的插件同样该拿得到门面，读写的
        分别判定在 `GuardedFileAccess` 里逐方法做（`NFR-302` 的读写分离）。
        """
        if any(self.grants.allows(permission) for permission in permissions):
            return
        raise NucleaError(
            ErrorCode.PERMISSION_DENIED,
            "插件未被授予该权限。",
            detail={
                "plugin": self.plugin_id_,
                "permission": "|".join(permission.value for permission in permissions),
                "suggestion": (
                    "manifest 里声明它，并用 "
                    f"`nm permissions grant {self.plugin_id_} <权限>` 批准。"
                ),
            },
        )

    def _root(self, accessor: str) -> Path:
        if self.workspace is None:
            raise NucleaError(
                ErrorCode.CAPABILITY_MISSING,
                f"这个实例没有 workspace，ctx.{accessor} 无处落地。",
                detail={"plugin": self.plugin_id_, "accessor": accessor},
            )
        return self.workspace

    @property
    def fs(self) -> FileAccess:
        self._require(PermissionKind.FS_READ, PermissionKind.FS_WRITE)
        return GuardedFileAccess(self._root("fs"), grants=self.grants, plugin_id=self.plugin_id_)

    @property
    def net(self) -> HttpAccess:
        self._require(PermissionKind.NET)
        return GuardedHttpAccess(
            plugin_id=self.plugin_id_,
            allowed_hosts=self.grants.targets(PermissionKind.NET),
        )

    @property
    def shell(self) -> ShellAccess:
        self._require(PermissionKind.SHELL)
        return GuardedShellAccess(self._root("shell"), plugin_id=self.plugin_id_)

    def secret(self, name: str) -> SecretStr:
        """取一个凭据：`plugins.<id>.secrets.<name>` 的 `${VAR}` 字面量 → 环境变量。

        **未授权与「授权了但没配」必须可区分**（`sdk/api.py` 写死的约定，`D19` 的
        `model_openai` 依赖它把「去改权限」和「去补配置」两种补救分开）。变量名没导出、
        或导出成空串，同样是 `CONFIG_SECRET_MISSING`——由 `resolve_text()` 抛出，
        错误里只有变量名与位置（`EDG-502`）。
        """
        if not self.grants.allows_secret(name):
            raise NucleaError(
                ErrorCode.PERMISSION_DENIED,
                "插件未被授予该凭据。",
                detail={"plugin": self.plugin_id_, "secret": name},
            )
        literal = self.secret_refs.get(name)
        pointer = f"/plugins/{self.plugin_id_}/secrets/{name}"
        if literal is None:
            detail: dict[str, JsonValue] = {
                "plugin": self.plugin_id_,
                "secret": name,
                "pointer": pointer,
                "suggestion": f'在 config.json 里写 {{"secrets": {{"{name}": "${{VAR}}"}}}}。',
            }
            if self.config_path is not None:
                detail["file"] = str(self.config_path)
            raise NucleaError(
                ErrorCode.CONFIG_SECRET_MISSING,
                "配置里没有这个凭据引用。",
                detail=detail,
            )
        resolved = resolve_text(
            literal,
            env=self.env,
            pointer=pointer,
            source="" if self.config_path is None else str(self.config_path),
        )
        # 不含 `${VAR}` 的字面量原样返回 `str`，但它按位置就是一个凭据——包起来，
        # 免得一个直接写死的密钥因为「没有引用」而以明文出现在日志里。
        return resolved if isinstance(resolved, SecretStr) else SecretStr(resolved)

    async def shutdown(self) -> None:
        """本插件的停止动作（`D28`）：退订事件、取消后台任务、等它们回收。

        `EDG-105` 的三项里这里做两项。**第三项「注销能力」不在这里，也不在运行期**：
        registry 解析后只读（`NFR-403`），而首版不热更新（技术方案 §10.4）——一个被
        `plugins.disable` 关掉的插件在**下一次启动**时连 `setup()` 都不会跑，它的能力
        因此从来没进过 registry。运行期把已冻结的能力表改掉是另一件事（P2 的热更新），
        在它存在之前，这句诚实声明比一个只在测试里成立的 `unregister()` 有用。

        **不设自己的超时**：预算由 `stop_plugins()` 统一施加（`EDG-104`），两处各判一次
        会让「到底等了多久」取决于两个数的最小值，而配置里只有一个。

        **异常约定**：不抛。`gather(return_exceptions=True)` 吃掉任务自己的异常——一个
        插件的后台任务崩了不该让它的清理半途而废。
        """
        self.stopping = True
        self.bridge.close()
        pending = [*self.tasks, *self.bridge.tasks]
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

    @property
    def instance(self) -> InstanceView:
        view = self.runtime.instance_view
        if view is None:
            raise self._too_early("instance")
        return view

    @property
    def turns(self) -> TurnControl:
        control = self.runtime.turn_control
        if control is None:
            raise self._too_early("turns")
        return control

    def _too_early(self, accessor: str) -> NucleaError:
        return NucleaError(
            ErrorCode.KERNEL_INVARIANT_VIOLATED,
            f"实例尚未就绪，ctx.{accessor} 在 setup() 期间不可用。",
            detail={"plugin": self.plugin_id_, "accessor": accessor},
        )


async def _as_coroutine(awaitable: Awaitable[None]) -> None:
    """`spawn_task` 收的是 `Awaitable`（契约签名），而 `create_task` 只吃协程。"""
    await awaitable


def _close_unawaited(awaitable: Awaitable[None]) -> None:
    """关掉一个不会被跑的协程，免得解释器在 GC 时刷 "was never awaited"。

    只对协程成立（别的 awaitable 没有 `close()`），因此是 `getattr` 而不是直接调用。
    """
    close = getattr(awaitable, "close", None)
    if callable(close):
        close()


def build_plugin_context(
    plugin_id: str,
    *,
    config: Mapping[str, JsonValue],
    secrets: Mapping[str, str],
    state_dir: Path,
    grants: PluginGrants,
    bus: EventBus,
    runtime: PluginRuntime,
    env: Mapping[str, str] | None = None,
    workspace: Path | None = None,
    config_path: Path | None = None,
) -> PluginContext:
    """装一个受限运行时。返回类型即「它满足契约」的静态证明（见模块 docstring）。"""
    ctx: PluginContext = RuntimePluginContext(
        plugin_id_=plugin_id,
        config_=dict(config),
        state_dir_=state_dir,
        grants=grants,
        secret_refs=dict(secrets),
        bridge=PluginEventBridge(bus, plugin_id),
        runtime=runtime,
        env=env,
        workspace=workspace,
        config_path=config_path,
    )
    return ctx
