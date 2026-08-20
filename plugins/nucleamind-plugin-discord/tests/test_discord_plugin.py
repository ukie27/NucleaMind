"""官方插件 `discord` 的验收：manifest、配置、Channel 生命周期（开发方案 `D33`）。

| 验收项 | 测试 |
| --- | --- |
| 通过 `ChannelContract` 全部用例 | `TestDiscordChannelContract` |
| manifest 自洽、entry point 对得上 | `TestManifest` |
| 配置校验在 `setup()` 时发生一次 | `TestSettings` |
| `start` / `stop` / `receive` / `deliver` 的契约约定 | `TestChannelLifecycle` |
| 没装 `discord.py` 时给一句能照做的话 | `TestMissingSdk` |

线格式与判定的逐条断言在 `test_normalize.py` / `test_outbound.py` / `test_stream.py` /
`test_indicators.py`；这里只放需要真的构造一个 Channel（或真的解析一次配置）才成立的。
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Sequence
from importlib.metadata import entry_points
from typing import Any

import pytest
from _fakes import CONVERSATION, TOKEN, FakePlatform, FakeWorkspace, outbound, settings
from nucleamind_plugin_discord import (
    CAPABILITY_NAME,
    CONFIG_KEYS,
    CONFIG_SCHEMA,
    DEFAULT_INTENTS,
    MANIFEST,
    SECRET_TOKEN,
    DiscordChannel,
    resolve_settings,
    setup,
)
from nucleamind_plugin_discord.gateway import MISSING_SDK_FIX, DiscordGateway

from nucleamind.contracts import (
    AttachmentRef,
    AttachmentSource,
    CapabilityKind,
    ErrorCode,
    NucleaError,
    StreamState,
)
from nucleamind.sdk.testing import ChannelContract, FakePluginContext


class _FakeGateway:
    """`DiscordGateway` 的替身：不连任何东西，但四个方法都在。"""

    def __init__(self) -> None:
        self.connected = 0
        self.closed = 0
        self.platform = FakePlatform()
        self.bot_user_id = "1"

    async def connect(self) -> None:
        self.connected += 1

    async def close(self) -> None:
        self.closed += 1

    # boundary: 生产实现返回 discord.Message；这里返回 `FakeSent`，形状一致即可
    async def send(self, conversation_id: str, content: str, *, reply_to: str | None) -> Any:
        return await self.platform.send(conversation_id, content, reply_to=reply_to)

    async def send_files(
        self, conversation_id: str, files: Sequence[tuple[str, bytes]], *, reply_to: str | None
    ) -> None:
        await self.platform.send_files(conversation_id, files, reply_to=reply_to)

    async def add_reaction(self, conversation_id: str, message_id: str, emoji: str) -> None:
        return None

    async def clear_reaction(self, conversation_id: str, message_id: str, emoji: str) -> None:
        return None

    async def type_once(self, conversation_id: str) -> None:
        return None


# boundary: 下面两个是关键字转发器，类型检查落在被构造的 `DiscordSettings` 与 ctx 上
def make_channel(
    *,
    files: FakeWorkspace | None = None,
    **kwargs: Any,  # boundary: 关键字转发，见上一行
) -> tuple[DiscordChannel, _FakeGateway]:
    gateway = _FakeGateway()
    channel = DiscordChannel(
        settings(**kwargs),
        token=TOKEN,
        gateway=gateway,  # type: ignore[arg-type]
        files=files,
    )
    return channel, gateway


def make_context(**config: Any) -> FakePluginContext:  # boundary: 同上
    return FakePluginContext(
        plugin_id=MANIFEST.id,
        config=config,
        secrets={SECRET_TOKEN: "discord-token-0123456789"},
    )


# ------------------------------------------------------------------------------ 契约基类


class TestDiscordChannelContract(ChannelContract):
    """`Channel` 的通用契约。四条断言各构造一次 Channel。"""

    def make_channel(self) -> DiscordChannel:
        channel, _ = make_channel()
        return channel


# ------------------------------------------------------------------------------ manifest


class TestManifest:
    def test_entry_point_name_equals_the_manifest_id(self) -> None:
        """`D25` 的判定：对不上时 `plugins.enabled` 指不到任何东西。"""
        assert MANIFEST.id in {item.name for item in entry_points(group="nucleamind.plugins")}

    def test_one_channel_capability_and_no_overrides(self) -> None:
        assert len(MANIFEST.capabilities) == 1
        decl = MANIFEST.capabilities[0]
        assert decl.kind is CapabilityKind.CHANNEL
        assert decl.name == CAPABILITY_NAME
        assert decl.overrides is None

    def test_priority_is_not_declared(self) -> None:
        """写了默认值 100 会被原样采纳，而内建基准是 0（`D16` 记的坑）。"""
        assert "priority" not in MANIFEST.capabilities[0].model_fields_set

    def test_a_platform_outage_must_not_take_the_instance_down(self) -> None:
        """`critical=False`：token 过期不该让 CLI 与其它 Channel 一起下线（`PLG-004`）。"""
        assert MANIFEST.critical is False

    def test_config_schema_matches_the_settings_table(self) -> None:
        """两处都「自洽」而对不上时，一个写对了的配置会在阶段 A 被 schema 拒掉。"""
        assert set(CONFIG_SCHEMA["properties"]) == set(CONFIG_KEYS)
        assert CONFIG_SCHEMA["additionalProperties"] is False

    def test_intents_allows_zero(self) -> None:
        """任何下限都要能容纳真实用得上的值（`D31` 踩过 `port: 0`）。"""
        assert CONFIG_SCHEMA["properties"]["intents"]["minimum"] == 0


# ------------------------------------------------------------------------------ 配置


class TestSettings:
    def test_defaults_match_the_legacy_values(self) -> None:
        """默认值一字不改地沿用 legacy，只换单位与命名。"""
        resolved = resolve_settings(make_context())
        assert resolved.channel_id == CAPABILITY_NAME
        assert resolved.intents == DEFAULT_INTENTS == 37377
        assert resolved.group_policy == "mention"
        assert resolved.stream_edit_interval_ms == 800  # legacy 的 0.8s
        assert resolved.working_emoji_delay_ms == 2000  # legacy 的 2.0s
        assert resolved.typing_interval_ms == 8000  # legacy 的 8s
        assert resolved.max_attachment_bytes == 20 * 1024 * 1024
        assert resolved.streaming is True

    def test_an_empty_allow_from_means_everyone(self) -> None:
        assert resolve_settings(make_context()).allow_from == frozenset()

    def test_ids_may_be_written_as_numbers(self) -> None:
        """Discord 的 id 在 JSON 里既可能被写成 `"123"` 也可能被写成 `123`。"""
        resolved = resolve_settings(make_context(allow_from=[123, "456"]))
        assert resolved.allow_from == frozenset({"123", "456"})

    def test_no_one_is_an_operator_by_default(self) -> None:
        """默认空是安全的一侧：`operator_only` 命令默认不可用。"""
        assert resolve_settings(make_context()).operators == frozenset()
        named = resolve_settings(make_context(operators=["42"]))
        assert named.operators == frozenset({"42"})

    def test_an_unknown_group_policy_is_rejected(self) -> None:
        with pytest.raises(NucleaError) as excinfo:
            resolve_settings(make_context(group_policy="whatever"))
        assert excinfo.value.code is ErrorCode.CONFIG_INVALID

    def test_a_proxy_username_without_a_proxy_is_rejected(self) -> None:
        """那个用户名永远不会被用到，而用户以为配好了。"""
        with pytest.raises(NucleaError) as excinfo:
            resolve_settings(make_context(proxy_username="u"))
        assert excinfo.value.code is ErrorCode.CONFIG_INVALID

    def test_booleans_must_be_booleans(self) -> None:
        with pytest.raises(NucleaError):
            resolve_settings(make_context(streaming=1))

    def test_an_id_list_must_be_a_list(self) -> None:
        with pytest.raises(NucleaError):
            resolve_settings(make_context(allow_from="42"))

    def test_the_gate_carries_the_bot_identity(self) -> None:
        gate = resolve_settings(make_context(operators=["42"])).gate(bot_user_id="1")
        assert gate.bot_user_id == "1"
        assert gate.operators == frozenset({"42"})


# ------------------------------------------------------------------------------ setup


class _Recorder:
    def __init__(self, ctx: FakePluginContext) -> None:
        self.ctx = ctx
        self.registered: dict[str, object] = {}

    def register_channel(self, name: str, channel: object) -> None:
        self.registered[name] = channel


class TestSetup:
    def test_setup_registers_exactly_one_channel(self) -> None:
        recorder = _Recorder(make_context())
        setup(recorder)  # type: ignore[arg-type]
        assert list(recorder.registered) == [CAPABILITY_NAME]
        assert isinstance(recorder.registered[CAPABILITY_NAME], DiscordChannel)

    def test_a_missing_token_is_a_config_error_pointing_at_the_key(self) -> None:
        """一个没有 token 的 Discord Channel 连不上任何东西——「起来了但什么都不做」更糟。"""
        ctx = FakePluginContext(
            plugin_id=MANIFEST.id, config={}
        )
        with pytest.raises(NucleaError) as excinfo:
            setup(_Recorder(ctx))  # type: ignore[arg-type]
        assert excinfo.value.code is ErrorCode.CONFIG_INVALID
        assert SECRET_TOKEN in str(excinfo.value.detail["pointer"])

    def test_a_bad_config_fails_before_registration(self) -> None:
        recorder = _Recorder(make_context(group_policy="nope"))
        with pytest.raises(NucleaError):
            setup(recorder)  # type: ignore[arg-type]
        assert recorder.registered == {}


# ------------------------------------------------------------------------------ 生命周期


class TestChannelLifecycle:
    async def test_start_connects_once(self) -> None:
        channel, gateway = make_channel()
        await channel.start()
        await channel.start()
        assert gateway.connected == 1
        await channel.stop()

    async def test_stop_is_idempotent_and_never_raises(self) -> None:
        """`EDG-104`：一个抛异常的 `stop()` 会让别的收尾也做不完。"""
        channel, _ = make_channel()
        await channel.start()
        await channel.stop()
        await channel.stop()

    async def test_receive_ends_after_stop(self) -> None:
        channel, _ = make_channel()
        await channel.start()
        await channel.stop()
        assert [message async for message in channel.receive()] == []

    async def test_channel_id_comes_from_the_config(self) -> None:
        """它是装配根 `by_channel` 的路由键——多 bot 部署时要能区分。"""
        channel, _ = make_channel(channel_id="discord-ops")
        assert channel.channel_id == "discord-ops"

    async def test_deliver_raises_external_channel_when_the_platform_fails(self) -> None:
        """`D43`：投递失败照约定抛。

        出站路由点捕获它、发一条 `channel.delivery_failed`，turn 照样走到终态
        （`EDG-204`），因此抛是安全的。在此之前这里把故障整个吞掉——「答案发不出去」
        于是在事件流里一个字都没有，而那正是最需要被看见的一种失败。
        """
        channel, gateway = make_channel()
        gateway.platform.fail = True
        await channel.start()
        with pytest.raises(NucleaError) as caught:
            await channel.deliver(outbound("答案"))
        assert caught.value.code is ErrorCode.EXTERNAL_CHANNEL
        assert caught.value.retryable is True
        # **只放类型名不放异常消息**：平台 SDK 的异常文本可能带 webhook URL 或令牌。
        assert "cause" in caught.value.detail
        await channel.stop()

    async def test_a_reasoning_delta_is_dropped_unless_asked_for(self) -> None:
        channel, gateway = make_channel()
        await channel.start()
        await channel.deliver(
            outbound("想一想", state=StreamState.DELTA, metadata={"reasoning": True})
        )
        assert gateway.platform.sent == []
        await channel.stop()

    async def test_a_final_message_reaches_the_platform(self) -> None:
        channel, gateway = make_channel()
        await channel.start()
        await channel.deliver(outbound("答案"))
        assert gateway.platform.sent == [(CONVERSATION, "答案", None)]
        await channel.stop()

    async def test_a_workspace_attachment_is_read_through_ctx_fs_and_uploaded(self) -> None:
        """`D47`：Channel 自己读字节（契约层只存引用），读的那条路是 `ctx.fs`。"""
        workspace = FakeWorkspace({"artifacts/images/a.png": b"PNG"})
        channel, gateway = make_channel(files=workspace)
        await channel.start()
        await channel.deliver(
            outbound(
                "给你",
                attachments=(
                    AttachmentRef(
                        source=AttachmentSource.WORKSPACE,
                        locator="artifacts/images/a.png",
                        media_type="image/png",
                        filename="a.png",
                    ),
                ),
            )
        )
        assert workspace.reads == ["artifacts/images/a.png"]
        assert gateway.platform.uploads == [(CONVERSATION, [("a.png", b"PNG")])]
        await channel.stop()

    async def test_an_attachment_read_failure_does_not_fail_the_delivery(self) -> None:
        """读不到就印一行。`deliver()` 照约定抛的只有**正文**发不出去那一种。"""
        channel, gateway = make_channel(files=FakeWorkspace())
        await channel.start()
        await channel.deliver(
            outbound(
                "给你",
                attachments=(
                    AttachmentRef(
                        source=AttachmentSource.WORKSPACE,
                        locator="artifacts/images/gone.png",
                        media_type="image/png",
                        filename="gone.png",
                    ),
                ),
            )
        )
        assert gateway.platform.uploads == []
        assert "无法上传" in gateway.platform.sent[-1][1]
        await channel.stop()

    async def test_an_inbound_message_reaches_the_queue(self) -> None:
        """平台回调 → 归一化 → 入站队列。这是 `receive()` 唯一的来源。"""
        from _fakes import FakeMessage

        channel, _ = make_channel()
        await channel.start()
        await channel._on_platform_message(FakeMessage())  # noqa: SLF001 - 模拟平台回调
        stream = channel.receive()
        message = await asyncio.wait_for(anext(stream), timeout=2)
        assert message.content == "在吗"
        assert message.conversation_id == CONVERSATION
        await channel.stop()

    async def test_a_malformed_platform_event_does_not_take_the_bot_down(self) -> None:
        """`MSG-004`：一条看不懂的平台事件不该让 bot 下线。"""
        channel, _ = make_channel()
        await channel.start()
        await channel._on_platform_message(object())  # noqa: SLF001 - 故意畸形
        await channel.stop()


# ------------------------------------------------------------------------------ 缺依赖


class TestMissingSdk:
    async def test_a_missing_discord_py_says_what_to_run(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """装了插件却没装 SDK 时给一句能照做的话，而不是一段 ImportError 栈。

        **开发环境里 `discord.py` 是装着的**（legacy channel 的依赖，
        `scripts/install_channel_dependencies.py` 会装它），因此这里要造出「没装」：
        把 `sys.modules["discord"]` 设成 `None` 会让 `import discord` 抛 `ImportError`，
        这是 CPython 有文档的行为，比 patch `__import__` 精确。
        """
        monkeypatch.setitem(sys.modules, "discord", None)
        gateway = DiscordGateway(token=TOKEN, intents=0, on_message=_never_called)
        with pytest.raises(NucleaError) as excinfo:
            gateway._import_sdk()  # noqa: SLF001 - 断言的就是这层错误
        assert excinfo.value.code is ErrorCode.EXTERNAL_CHANNEL
        assert excinfo.value.detail["fix"] == MISSING_SDK_FIX
        assert "pip install" in MISSING_SDK_FIX

    async def test_close_without_connect_is_safe(self) -> None:
        gateway = DiscordGateway(token=TOKEN, intents=0, on_message=_never_called)
        await gateway.close()
        assert gateway.bot_user_id == ""


async def _never_called(message: object) -> None:
    raise AssertionError("这条路径不该被走到")
