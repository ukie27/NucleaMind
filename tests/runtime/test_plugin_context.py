"""`D23` 生产级 `PluginContext`：配置块、状态目录、凭据、事件桥与两个门面。

职责：验权限判定（未声明即 `PERMISSION_DENIED`）、`ctx.secret()` 的三种结局、事件桥
把同步 bus 接到异步 handler 上的规则、`instance` / `turns` 在就绪之前不可用。
不负责：验装配根怎么构造它（`test_bootstrap.py`）。

**哨兵贯穿全文**：明文凭据不得出现在任何一条错误、`repr` 或事件序列化里（`MOD-002`）。
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from nucleamind.contracts import (
    ErrorCode,
    EventName,
    InstanceId,
    NucleaError,
    PermissionKind,
    RuntimeEvent,
    SecretStr,
)
from nucleamind.kernel.observability import EventBus
from nucleamind.runtime.plugin_context import (
    PluginGrants,
    PluginRuntime,
    RuntimePluginContext,
    build_plugin_context,
)

#: 形状匹配 `errors.py::_SECRET_VALUE_PATTERNS` 的哨兵，`sk-` + 16 位以上。
SENTINEL = "sk-0123456789abcdef"


def make_ctx(
    tmp_path: Path,
    *,
    grants: PluginGrants | None = None,
    secrets: dict[str, str] | None = None,
    env: dict[str, str] | None = None,
    runtime: PluginRuntime | None = None,
) -> RuntimePluginContext:
    ctx = build_plugin_context(
        "probe",
        config={"a": 1},
        secrets=secrets or {},
        state_dir=tmp_path / "plugins" / "probe",
        grants=grants or PluginGrants(),
        bus=EventBus(InstanceId("test")),
        runtime=runtime or PluginRuntime(),
        env=env,
    )
    assert isinstance(ctx, RuntimePluginContext)
    return ctx


# ------------------------------------------------------------------ 配置与状态目录


def test_the_config_block_is_handed_over_untouched(tmp_path: Path) -> None:
    assert make_ctx(tmp_path).config == {"a": 1}


def test_the_state_dir_is_created_on_first_access(tmp_path: Path) -> None:
    """装配根不为一个可能从未写盘的插件先建目录。"""
    ctx = make_ctx(tmp_path)
    assert not (tmp_path / "plugins" / "probe").exists()
    assert ctx.state_dir.is_dir()


# ---------------------------------------------------------------------- 权限


@pytest.mark.parametrize("accessor", ["fs", "net", "shell"])
def test_an_undeclared_accessor_is_denied(tmp_path: Path, accessor: str) -> None:
    """未授权时**属性访问**就抛，插件拿不到「看起来能用、调用才失败」的对象。"""
    with pytest.raises(NucleaError) as caught:
        getattr(make_ctx(tmp_path), accessor)
    assert caught.value.code is ErrorCode.PERMISSION_DENIED


def test_a_declared_accessor_says_it_is_not_implemented_yet(tmp_path: Path) -> None:
    """`D26` 才有带守卫的实现。给一个能跑但没有守卫的门面才是真的危险。"""
    ctx = make_ctx(tmp_path, grants=PluginGrants(frozenset({PermissionKind.NET})))
    with pytest.raises(NucleaError) as caught:
        _ = ctx.net
    assert caught.value.code is ErrorCode.CAPABILITY_MISSING
    assert "D26" in caught.value.user_message


# ---------------------------------------------------------------------- 凭据


def _secret_grants() -> PluginGrants:
    return PluginGrants(frozenset({PermissionKind.SECRET}), frozenset({"api_key"}))


def test_a_granted_secret_resolves_from_the_environment(tmp_path: Path) -> None:
    ctx = make_ctx(
        tmp_path,
        grants=_secret_grants(),
        secrets={"api_key": "${NM_TOKEN}"},
        env={"NM_TOKEN": SENTINEL},
    )
    secret = ctx.secret("api_key")
    assert isinstance(secret, SecretStr)
    assert secret.reveal() == SENTINEL
    # 掩码是默认渲染，明文只经 `reveal()` 取出。
    assert SENTINEL not in f"{secret!r} {secret}"


def test_an_ungranted_secret_and_a_missing_one_are_distinguishable(tmp_path: Path) -> None:
    """`D19` 的 `model_openai` 靠这个区分把「去改权限」和「去补配置」分开。"""
    with pytest.raises(NucleaError) as denied:
        make_ctx(tmp_path).secret("api_key")
    assert denied.value.code is ErrorCode.PERMISSION_DENIED

    with pytest.raises(NucleaError) as missing:
        make_ctx(tmp_path, grants=_secret_grants()).secret("api_key")
    assert missing.value.code is ErrorCode.CONFIG_SECRET_MISSING
    assert missing.value.detail["pointer"] == "/plugins/probe/secrets/api_key"


def test_an_unexported_variable_reports_only_its_name(tmp_path: Path) -> None:
    """`EDG-502`：错误里只有变量名与位置，没有任何值。"""
    ctx = make_ctx(tmp_path, grants=_secret_grants(), secrets={"api_key": "${NOPE}"}, env={})
    with pytest.raises(NucleaError) as caught:
        ctx.secret("api_key")
    assert caught.value.code is ErrorCode.CONFIG_SECRET_MISSING
    assert "NOPE" in repr(caught.value.detail)


def test_a_literal_secret_is_still_wrapped(tmp_path: Path) -> None:
    """按位置就是一个凭据——不含 `${VAR}` 也要包起来，免得它以明文进日志。"""
    ctx = make_ctx(tmp_path, grants=_secret_grants(), secrets={"api_key": SENTINEL})
    assert ctx.secret("api_key").reveal() == SENTINEL
    assert SENTINEL not in str(ctx.secret("api_key"))


# ---------------------------------------------------------------------- 事件桥


async def test_events_reach_an_async_handler(tmp_path: Path) -> None:
    ctx = make_ctx(tmp_path)
    seen: list[RuntimeEvent] = []

    async def handler(event: RuntimeEvent) -> None:
        seen.append(event)

    ctx.events.subscribe(EventName.INSTANCE_READY, handler)
    ctx.bridge._bus.publish(EventName.INSTANCE_READY)  # noqa: SLF001 - 桥就是接在它上面的
    await asyncio.sleep(0)
    await asyncio.gather(*ctx.bridge.tasks)
    assert [event.name for event in seen] == [EventName.INSTANCE_READY]


async def test_only_the_subscribed_event_is_delivered(tmp_path: Path) -> None:
    ctx = make_ctx(tmp_path)
    calls = 0

    async def handler(event: RuntimeEvent) -> None:
        nonlocal calls
        del event
        calls += 1

    ctx.events.subscribe(EventName.INSTANCE_READY, handler)
    # 同一个 handler 重复订阅同一事件视为一次（`EventSubscriber` 的约定）。
    ctx.events.subscribe(EventName.INSTANCE_READY, handler)
    ctx.bridge._bus.publish(EventName.INSTANCE_STOPPING)  # noqa: SLF001
    ctx.bridge._bus.publish(EventName.INSTANCE_READY)  # noqa: SLF001
    await asyncio.sleep(0)
    await asyncio.gather(*ctx.bridge.tasks)
    assert calls == 1


def test_publishing_without_a_loop_is_counted_not_crashed(tmp_path: Path) -> None:
    """`publish()` 会在没有事件循环的路径上被调用（`instance.starting`、`nm config show`）。"""
    ctx = make_ctx(tmp_path)

    async def handler(event: RuntimeEvent) -> None:  # pragma: no cover - 永远不会被跑到
        del event

    ctx.events.subscribe(EventName.INSTANCE_READY, handler)
    ctx.bridge._bus.publish(EventName.INSTANCE_READY)  # noqa: SLF001
    assert ctx.bridge.dropped == 1


# ------------------------------------------------------------------ 后台任务与门面


async def test_spawn_task_registers_the_task(tmp_path: Path) -> None:
    ctx = make_ctx(tmp_path)
    done = asyncio.Event()

    async def body() -> None:
        done.set()

    ctx.spawn_task(body(), name="probe")
    await asyncio.wait_for(done.wait(), timeout=1)


def test_spawn_task_without_a_loop_is_an_invariant_violation(tmp_path: Path) -> None:
    """`setup()` 在装配期同步执行，那时派生后台任务就是在赌一个还不存在的循环。"""
    ctx = make_ctx(tmp_path)

    async def body() -> None:  # pragma: no cover - 不会被跑到
        return None

    coro = body()
    with pytest.raises(NucleaError) as caught:
        ctx.spawn_task(coro, name="probe")
    assert caught.value.code is ErrorCode.KERNEL_INVARIANT_VIOLATED
    coro.close()


def test_the_two_facades_are_unavailable_before_the_instance_is_ready(tmp_path: Path) -> None:
    """`PluginContext` 要在 `setup()` 之前交给插件，而门面此时还不存在。"""
    ctx = make_ctx(tmp_path)
    for accessor in ("instance", "turns"):
        with pytest.raises(NucleaError) as caught:
            getattr(ctx, accessor)
        assert caught.value.code is ErrorCode.KERNEL_INVARIANT_VIOLATED
