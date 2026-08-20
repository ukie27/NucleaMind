"""入站归一化的验收（`MSG-004`、`MSG-002`，开发方案 `D33`）。

| 验收项 | 测试 |
| --- | --- |
| 判定顺序与五道门 | `TestGating` |
| 平台消息 → `InboundMessage` | `TestNormalization` |
| 附件 → `AttachmentRef` + 正文标记 | `TestAttachments` |
| `discord.Message` → `RawInbound`（`gateway.to_raw`） | `TestRawConversion` |

**这一整个文件不需要装 `discord.py`**：`normalize()` 只认识 `RawInbound`，而
`to_raw()` 用 `getattr` 解构，一个长得像的普通对象就够（`_fakes.py`）。legacy 的测试
第 11 行是 `pytest.importorskip("discord")`——那意味着 CI 没装依赖时 52 个用例静默全跳。
"""

from __future__ import annotations

from datetime import UTC, datetime

from _fakes import (
    BOT_ID,
    CONVERSATION,
    USER_ID,
    FakeAttachment,
    FakeAuthor,
    FakeChannel,
    FakeGuild,
    FakeMessage,
    FakeReference,
    attachment,
    gate,
    raw,
)
from nucleamind_plugin_discord import RawAuthor, normalize, to_raw
from nucleamind_plugin_discord.normalize import EMPTY_CONTENT

from nucleamind.contracts import AttachmentSource


class TestGating:
    def test_messages_from_other_bots_are_kept_only_our_own_are_dropped(self) -> None:
        """上游 issue #3217：多 bot 编排要靠这条成立。

        **最容易被「顺手改成 `if author.bot: return`」毁掉的一条。** 一个 bot @ 另一个 bot
        求助是合法用法；bot 之间的循环仍被「每个 bot 都忽略自己」挡住。
        """
        mine = raw(author=RawAuthor(id=BOT_ID, is_bot=True))
        other = raw(author=RawAuthor(id="99", is_bot=True))
        assert normalize(mine, gate()) is None
        assert normalize(other, gate()) is not None

    def test_system_messages_are_dropped(self) -> None:
        """加人、pin、thread 生命周期这些不带用户 prompt。"""
        for kind in ("pins_add", "thread_created", "channel_name_change"):
            assert normalize(raw(message_type=kind), gate()) is None
        assert normalize(raw(message_type="reply"), gate()) is not None

    def test_an_empty_allow_from_allows_everyone(self) -> None:
        """与 legacy 一致。改它等于静默改变谁能用这个 bot。"""
        assert normalize(raw(), gate(allow_from=frozenset())) is not None

    def test_a_non_empty_allow_from_is_a_whitelist(self) -> None:
        assert normalize(raw(), gate(allow_from=frozenset({USER_ID}))) is not None
        assert normalize(raw(), gate(allow_from=frozenset({"other"}))) is None

    def test_allow_channels_matches_a_thread_by_its_parent(self) -> None:
        """运维配的是「这个频道」，而 thread 是那个频道里长出来的东西。"""
        thread = raw(channel_id="777", parent_channel_id=CONVERSATION)
        assert normalize(thread, gate(allow_channels=frozenset({CONVERSATION}))) is not None
        assert normalize(thread, gate(allow_channels=frozenset({"777"}))) is not None
        assert normalize(thread, gate(allow_channels=frozenset({"other"}))) is None

    def test_direct_messages_skip_the_group_gate(self) -> None:
        """DM 里没有别人，@ 门控没有意义。"""
        assert normalize(raw(guild_id=None), gate(group_policy="mention")) is not None

    def test_open_policy_answers_everything_in_a_guild(self) -> None:
        assert normalize(raw(guild_id="900"), gate(group_policy="open")) is not None

    def test_mention_policy_needs_the_bot_to_be_addressed(self) -> None:
        assert normalize(raw(guild_id="900"), gate()) is None

    def test_the_four_mention_paths(self) -> None:
        """逐条对应 legacy `_should_respond_in_group`。**第四条最容易漏。**"""
        # ① mention 列表命中
        assert normalize(raw(guild_id="900", mention_ids=(BOT_ID,)), gate()) is not None
        # ② 正文里的 `<@id>`
        assert normalize(raw(guild_id="900", content=f"<@{BOT_ID}> 在吗"), gate()) is not None
        # ③ 正文里的旧版 `<@!id>`
        assert normalize(raw(guild_id="900", content=f"<@!{BOT_ID}> 在吗"), gate()) is not None
        # ④ 回复的是 bot 自己发的消息——在 Discord 上这是接着说话的常规方式
        assert normalize(
            raw(guild_id="900", reply_to="7", reply_to_author_id=BOT_ID), gate()
        ) is not None

    def test_without_a_bot_identity_the_group_gate_stays_closed(self) -> None:
        """`on_ready` 之前宁可不答也不要在群里乱说话。"""
        assert normalize(raw(guild_id="900", mention_ids=("1",)), gate(bot_user_id="")) is None

    def test_rejections_are_recorded_for_diagnostics(self) -> None:
        """被丢掉的原因查得到，但**不发事件**——一个热闹的服务器每秒能产生几十条。"""
        probe = gate(allow_from=frozenset({"other"}))
        assert normalize(raw(), probe) is None
        assert probe.rejections == ["sender_not_allowed"]


class TestNormalization:
    def test_a_thread_is_its_own_conversation(self) -> None:
        """不需要 legacy 那个自造的 session key——`SessionKey` 已经表达完了。"""
        message = normalize(raw(channel_id="777", parent_channel_id=CONVERSATION), gate())
        assert message is not None
        assert message.conversation_id == "777"
        assert message.metadata["discord"]["parent_channel_id"] == CONVERSATION
        assert message.metadata["discord"]["is_thread"] is True

    def test_platform_fields_live_under_their_own_namespace(self) -> None:
        """`MSG-002`：平台私有字段只进 `metadata["discord"]`，Kernel 不解读它。"""
        message = normalize(raw(guild_id="900"), gate(group_policy="open"))
        assert message is not None
        assert set(message.metadata) == {"discord"}
        assert message.metadata["discord"]["guild_id"] == "900"

    def test_is_operator_only_for_the_named_operators(self) -> None:
        """`operator_only` 命令的可达性全靠这一行（契约：由 Channel 在边界决定）。"""
        assert normalize(raw(), gate()).sender.is_operator is False  # type: ignore[union-attr]
        named = gate(operators=frozenset({USER_ID}))
        assert normalize(raw(), named).sender.is_operator is True  # type: ignore[union-attr]

    def test_reply_to_is_carried_through(self) -> None:
        message = normalize(raw(reply_to="7"), gate())
        assert message is not None
        assert message.reply_to == "7"

    def test_an_empty_message_gets_a_floor_value(self) -> None:
        """契约要求内容与附件不能同时为空，而只有 sticker 的消息在这里确实两者皆空。"""
        message = normalize(raw(content="   "), gate())
        assert message is not None
        assert message.content == EMPTY_CONTENT


class TestAttachments:
    def test_attachments_become_url_refs_and_body_notes(self) -> None:
        """**不下载不落盘**：契约只存引用，因此归一化阶段不需要 Workspace IO。"""
        message = normalize(raw(attachments=(attachment(filename="报告.pdf"),)), gate())
        assert message is not None
        ref = message.attachments[0]
        assert ref.source is AttachmentSource.URL
        assert ref.filename == "报告.pdf"
        assert "[attachment: 报告.pdf]" in message.content

    def test_an_oversized_attachment_leaves_a_note_but_no_ref(self) -> None:
        """给了引用，下游就会去下载一个我们已经知道超限的东西。"""
        message = normalize(
            raw(attachments=(attachment(filename="big.bin", size=999),)),
            gate(max_attachment_bytes=100),
        )
        assert message is not None
        assert message.attachments == ()
        assert "too large" in message.content

    def test_a_missing_content_type_gets_a_floor(self) -> None:
        message = normalize(raw(attachments=(attachment(content_type=""),)), gate())
        assert message is not None
        assert message.attachments[0].media_type == "application/octet-stream"


class TestRawConversion:
    """`gateway.to_raw()`：SDK 对象能走到的最后一步。"""

    def test_a_plain_message_round_trips(self) -> None:
        converted = to_raw(FakeMessage())
        assert converted.message_id == "1001"
        assert converted.channel_id == CONVERSATION
        assert converted.author.id == USER_ID
        assert converted.content == "在吗"
        assert converted.is_direct_message is True

    def test_a_guild_message_carries_its_guild(self) -> None:
        converted = to_raw(FakeMessage(guild=FakeGuild("900")))
        assert converted.guild_id == "900"
        assert converted.is_direct_message is False

    def test_a_thread_carries_its_parent(self) -> None:
        converted = to_raw(FakeMessage(channel=FakeChannel("777", parent_id=CONVERSATION)))
        assert converted.channel_id == "777"
        assert converted.parent_channel_id == CONVERSATION

    def test_a_reply_carries_the_target_and_its_author(self) -> None:
        """第四条 @ 命中路径要的就是 `reply_to_author_id`。"""
        reference = FakeReference("7", author=FakeAuthor(BOT_ID))
        converted = to_raw(FakeMessage(reference=reference))
        assert converted.reply_to == "7"
        assert converted.reply_to_author_id == BOT_ID

    def test_mentions_and_attachments_are_flattened(self) -> None:
        converted = to_raw(
            FakeMessage(
                mentions=(FakeAuthor(BOT_ID),),
                attachments=(FakeAttachment("a.png", size=5, content_type="image/png"),),
            )
        )
        assert converted.mention_ids == (BOT_ID,)
        assert converted.attachments[0].filename == "a.png"
        assert converted.attachments[0].content_type == "image/png"

    def test_a_system_message_keeps_its_kind(self) -> None:
        assert to_raw(FakeMessage(kind="pins_add")).message_type == "pins_add"

    def test_a_message_without_a_timestamp_still_gets_one(self) -> None:
        """契约要求 `timestamp` 带时区；缺失时用当前时间而不是让整条消息失败。"""
        message = FakeMessage()
        message.created_at = None  # type: ignore[assignment]
        converted = to_raw(message)
        assert converted.timestamp.tzinfo is not None
        assert converted.timestamp <= datetime.now(UTC)
