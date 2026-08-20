"""流式 edit-in-place 状态机的验收（`MSG-005`、`EDG-304`，开发方案 `D33`）。

模块 docstring 里那八条判定，每条一个用例。**全程用注入的 `FakeClock`，不 `sleep`**：
节流是本模块唯一的时间语义，用真实时间测它意味着每个用例都要等 0.8 秒，慢机器上还会
假阳性。
"""

from __future__ import annotations

from _fakes import CONVERSATION, FakeClock, FakePlatform, FakeWorkspace, outbound
from nucleamind_plugin_discord import StreamRelay

from nucleamind.contracts import AttachmentRef, AttachmentSource, NucleaError, StreamState


def relay(platform: FakePlatform, clock: FakeClock, **kwargs: object) -> StreamRelay:
    return StreamRelay(platform=platform, now_ms=clock, **kwargs)  # type: ignore[arg-type]


class TestStreamRelay:
    async def test_started_does_not_put_anything_on_the_wire(self) -> None:
        """判定 ①：Discord 上不会因此出现一条空消息。"""
        platform, clock = FakePlatform(), FakeClock()
        stream = relay(platform, clock)
        await stream.handle(outbound("", state=StreamState.STARTED))
        assert platform.sent == []
        assert stream.active() == 1

    async def test_a_blank_first_delta_waits_for_real_text(self) -> None:
        """判定 ②：模型的第一个 delta 常常是空白，上线会发出一条看起来坏掉的消息。"""
        platform, clock = FakePlatform(), FakeClock()
        stream = relay(platform, clock)
        await stream.handle(outbound(" ", state=StreamState.DELTA))
        assert platform.sent == []
        await stream.handle(outbound("你好", state=StreamState.DELTA))
        assert len(platform.sent) == 1
        assert platform.sent[0][1] == " 你好"

    async def test_throttled_text_is_not_lost(self) -> None:
        """判定 ③：被节流跳过的文本留在缓冲里，终态收束时必须完整。"""
        platform, clock = FakePlatform(), FakeClock()
        stream = relay(platform, clock, edit_interval_ms=800)
        await stream.handle(outbound("一", state=StreamState.DELTA))
        for text in ("二", "三", "四", "五"):
            clock.advance(100)  # 全都在节流窗口内
            await stream.handle(outbound(text, state=StreamState.DELTA))
        assert platform.messages[0].edits == []  # 一次编辑都没发生
        # 用 `CANCELLED` 收束：`FINAL` 的正文在契约构造时就不许为空，因此「回退到累积
        # 文本」这条路只有中断/失败才走得到——而那恰好是最需要它的时候。
        await stream.handle(outbound("", state=StreamState.CANCELLED))
        assert "一二三四五" in platform.messages[0].content

    async def test_an_edit_happens_once_the_interval_passes(self) -> None:
        platform, clock = FakePlatform(), FakeClock()
        stream = relay(platform, clock, edit_interval_ms=800)
        await stream.handle(outbound("一", state=StreamState.DELTA))
        clock.advance(900)
        await stream.handle(outbound("二", state=StreamState.DELTA))
        assert platform.messages[0].edits == ["一二"]

    async def test_the_terminal_content_wins_over_the_accumulated_deltas(self) -> None:
        """判定 ④：终态消息带的是同一段完整正文，用它可以避免 delta 丢片造成的漂移。"""
        platform, clock = FakePlatform(), FakeClock()
        stream = relay(platform, clock)
        await stream.handle(outbound("半", state=StreamState.DELTA))
        await stream.handle(outbound("完整的答案", state=StreamState.FINAL))
        assert platform.messages[0].content == "完整的答案"

    async def test_an_overlong_finish_edits_the_head_and_sends_the_rest(self) -> None:
        """判定 ⑤：只编辑会让 2000 之外的内容静默消失。"""
        platform, clock = FakePlatform(), FakeClock()
        stream = relay(platform, clock)
        await stream.handle(outbound("开始", state=StreamState.DELTA))
        await stream.handle(outbound("x" * 2500, state=StreamState.FINAL))
        assert len(platform.messages[0].edits) == 1
        assert len(platform.messages[0].edits[0]) <= 2000
        # 首块之外的内容作为新消息补发出去，一个字都不能少。
        assert len(platform.sent) == 2
        assert len(platform.messages[0].edits[0]) + len(platform.sent[1][1]) == 2500

    async def test_a_new_turn_gets_a_new_buffer(self) -> None:
        """判定 ⑥：旧 wire 消息原样留着——它自己的终态已经带过 `EDG-304` 标记了。"""
        platform, clock = FakePlatform(), FakeClock()
        stream = relay(platform, clock)
        await stream.handle(outbound("第一轮", state=StreamState.DELTA, turn="turn-1"))
        await stream.handle(outbound("第二轮", state=StreamState.DELTA, turn="turn-2"))
        assert len(platform.sent) == 2
        assert platform.messages[0].content == "第一轮"
        assert platform.messages[1].content == "第二轮"

    async def test_different_conversations_use_different_buffers(self) -> None:
        """判定 ⑦：缓冲表按 conversation 分片，因此并发 `deliver` 不需要加锁。"""
        platform, clock = FakePlatform(), FakeClock()
        stream = relay(platform, clock)
        await stream.handle(outbound("A", state=StreamState.DELTA, conversation="a"))
        await stream.handle(outbound("B", state=StreamState.DELTA, conversation="b"))
        assert stream.active() == 2
        assert [item[0] for item in platform.sent] == ["a", "b"]

    async def test_a_finished_conversation_releases_its_buffer(self) -> None:
        platform, clock = FakePlatform(), FakeClock()
        stream = relay(platform, clock)
        await stream.handle(outbound("x", state=StreamState.DELTA))
        await stream.handle(outbound("x", state=StreamState.FINAL))
        assert stream.active() == 0

    async def test_streaming_off_only_sends_at_the_end(self) -> None:
        """`MSG-005` 的降级：不支持（或不想要）流式时聚合成最终消息。"""
        platform, clock = FakePlatform(), FakeClock()
        stream = relay(platform, clock, streaming=False)
        for text in ("一", "二", "三"):
            await stream.handle(outbound(text, state=StreamState.DELTA))
        assert platform.sent == []
        await stream.handle(outbound("一二三", state=StreamState.FINAL))
        assert len(platform.sent) == 1
        assert platform.sent[0][1] == "一二三"

    async def test_a_terminal_marker_reaches_the_wire(self) -> None:
        platform, clock = FakePlatform(), FakeClock()
        stream = relay(platform, clock)
        await stream.handle(outbound("半句", state=StreamState.DELTA))
        await stream.handle(outbound("", state=StreamState.CANCELLED))
        assert "已中断" in platform.messages[0].content
        assert "半句" in platform.messages[0].content

    async def test_a_terminal_without_a_live_message_just_sends(self) -> None:
        """没有流式（或流式一片都没上线）时，终态就是一条普通消息。"""
        platform, clock = FakePlatform(), FakeClock()
        stream = relay(platform, clock)
        await stream.handle(outbound("答案", state=StreamState.FINAL, conversation=CONVERSATION))
        assert platform.sent == [(CONVERSATION, "答案", None)]

    async def test_an_empty_cancellation_keeps_what_was_already_shown(self) -> None:
        """中断时正文可以是空的（契约允许），但已经显示的内容一个字都不能丢。"""
        platform, clock = FakePlatform(), FakeClock()
        stream = relay(platform, clock)
        await stream.handle(outbound("已经说了的", state=StreamState.DELTA))
        await stream.handle(outbound("", state=StreamState.CANCELLED))
        assert "已经说了的" in platform.messages[0].content
        assert "已中断" in platform.messages[0].content


class TestAttachmentUpload:
    """判定 ⑧：附件在正文之后真的传上去（`D47`）。"""

    @staticmethod
    def _png(locator: str = "artifacts/images/a.png") -> AttachmentRef:
        return AttachmentRef(
            source=AttachmentSource.WORKSPACE,
            locator=locator,
            media_type="image/png",
            filename=locator.rsplit("/", 1)[-1],
        )

    async def test_a_workspace_attachment_is_uploaded_after_the_text(self) -> None:
        platform, clock = FakePlatform(), FakeClock()
        workspace = FakeWorkspace({"artifacts/images/a.png": b"PNG"})

        async def read(item: AttachmentRef) -> bytes | None:
            return await workspace.read_bytes(item.locator)

        stream = relay(platform, clock, read_attachment=read)
        await stream.handle(outbound("给你", attachments=(self._png(),)))

        assert platform.sent == [(CONVERSATION, "给你", None)]
        assert platform.uploads == [(CONVERSATION, [("a.png", b"PNG")])]

    async def test_the_relative_path_never_reaches_the_channel_as_text(self) -> None:
        """一条 workspace 相对路径印在频道里对用户没有任何意义。"""
        platform, clock = FakePlatform(), FakeClock()

        async def read(item: AttachmentRef) -> bytes | None:
            del item
            return b"PNG"

        stream = relay(platform, clock, read_attachment=read)
        await stream.handle(outbound("给你", attachments=(self._png(),)))
        assert all("artifacts/images" not in content for _, content, _ in platform.sent)

    async def test_an_unreadable_attachment_says_so_and_does_not_raise(self) -> None:
        """`EDG-204`：一个读不到的附件不该把一次成功的投递变成失败。"""
        platform, clock = FakePlatform(), FakeClock()
        workspace = FakeWorkspace()

        async def read(item: AttachmentRef) -> bytes | None:
            try:
                return await workspace.read_bytes(item.locator)
            except NucleaError:
                return None

        stream = relay(platform, clock, read_attachment=read)
        await stream.handle(outbound("给你", attachments=(self._png(),)))

        assert platform.uploads == []
        assert "无法上传" in platform.sent[-1][1]

    async def test_without_a_reader_the_attachment_is_reported_not_dropped(self) -> None:
        """没注入 reader 时也要说一句——静默丢掉才是最坏的那一种。"""
        platform, clock = FakePlatform(), FakeClock()
        stream = relay(platform, clock)
        await stream.handle(outbound("给你", attachments=(self._png(),)))
        assert platform.uploads == []
        assert "无法上传" in platform.sent[-1][1]

    async def test_uploads_also_happen_when_the_answer_was_streamed(self) -> None:
        """流式路径与非流式路径都要走到上传——收束走的是同一个 `_finish`。"""
        platform, clock = FakePlatform(), FakeClock()

        async def read(item: AttachmentRef) -> bytes | None:
            del item
            return b"PNG"

        stream = relay(platform, clock, read_attachment=read)
        await stream.handle(outbound("画", state=StreamState.DELTA))
        await stream.handle(outbound("画好了", attachments=(self._png(),)))

        assert platform.messages[0].edits == ["画好了"]
        assert platform.uploads == [(CONVERSATION, [("a.png", b"PNG")])]
