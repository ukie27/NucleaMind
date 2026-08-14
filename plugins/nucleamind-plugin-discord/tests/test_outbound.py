"""出站分段与 `EDG-304` 标记的验收（`MSG-003`，开发方案 `D33`）。

| 验收项 | 测试 |
| --- | --- |
| 2000 字符分段的三档切法 | `TestSplit` |
| 中断/失败标记 | `TestTerminalMarkers` |
| 附件呈现与回复引用 | `TestPlan` |

纯函数，不需要事件循环也不需要假平台。
"""

from __future__ import annotations

import pytest
from _fakes import outbound
from nucleamind_plugin_discord import (
    MAX_MESSAGE_LENGTH,
    TERMINAL_MARKERS,
    SendPlan,
    plan_outbound,
    split_message,
)

from nucleamind.contracts import AttachmentRef, AttachmentSource, StreamState


class TestSplit:
    def test_an_empty_string_yields_nothing(self) -> None:
        """**不是 `[""]`**：一条空消息发过去是 400，而调用方要的是「没什么可发的」。"""
        assert split_message("") == []

    @pytest.mark.parametrize("size", [1999, 2000])
    def test_at_or_below_the_limit_stays_one_chunk(self, size: int) -> None:
        assert split_message("x" * size) == ["x" * size]

    def test_one_over_the_limit_splits(self) -> None:
        chunks = split_message("x" * (MAX_MESSAGE_LENGTH + 1))
        assert len(chunks) == 2
        assert all(len(chunk) <= MAX_MESSAGE_LENGTH for chunk in chunks)

    def test_a_newline_is_preferred_over_a_space(self) -> None:
        """三档切法的第一档。切在换行上，代码块与列表因此不会被拦腰截断。"""
        text = "a" * 1990 + "\n" + "b" * 20 + " " + "c" * 20
        chunks = split_message(text)
        assert chunks[0] == "a" * 1990
        assert chunks[1].startswith("b")

    def test_a_space_is_preferred_over_a_hard_cut(self) -> None:
        text = "a" * 1990 + " " + "b" * 30
        chunks = split_message(text)
        assert chunks[0] == "a" * 1990
        assert chunks[1] == "b" * 30

    def test_a_run_without_separators_is_hard_cut(self) -> None:
        text = "a" * 2500
        chunks = split_message(text)
        assert chunks == ["a" * 2000, "a" * 500]

    def test_every_chunk_is_within_the_limit(self) -> None:
        """最要紧的一条：任何一块超限都是 400。"""
        text = ("段落。" * 400 + "\n") * 5
        assert all(len(chunk) <= MAX_MESSAGE_LENGTH for chunk in split_message(text))

    def test_nothing_is_lost_apart_from_separator_whitespace(self) -> None:
        text = "一二三 " * 900
        assert "".join(split_message(text)).replace(" ", "") == text.replace(" ", "")

    def test_a_non_positive_limit_returns_one_chunk(self) -> None:
        """切不动的循环比一条超长消息更糟。"""
        assert split_message("abc", 0) == ["abc"]


class TestTerminalMarkers:
    def test_the_markers_match_the_terminal_states(self) -> None:
        assert set(TERMINAL_MARKERS) == {StreamState.CANCELLED, StreamState.FAILED}

    def test_a_cancelled_answer_carries_the_interrupt_marker(self) -> None:
        """`EDG-304`：不得渲染成完整回答。"""
        plan = plan_outbound(outbound("半句话", state=StreamState.CANCELLED))
        assert plan.chunks[-1].endswith("[已中断：以上是中断前已产生的内容]")
        assert "半句话" in plan.chunks[0]

    def test_a_failed_answer_carries_the_failure_marker(self) -> None:
        plan = plan_outbound(outbound("", state=StreamState.FAILED))
        assert plan.chunks == ("[本轮失败]",)

    def test_a_complete_answer_carries_no_marker(self) -> None:
        plan = plan_outbound(outbound("答案"))
        assert plan.chunks == ("答案",)

    def test_the_marker_shares_the_message_with_the_partial_answer(self) -> None:
        """分开发会让半截答案孤零零留在上面看着像完整回答——`EDG-304` 要防的正是这个。"""
        plan = plan_outbound(outbound("半句", state=StreamState.CANCELLED))
        assert len(plan.chunks) == 1
        assert "半句" in plan.chunks[0] and "已中断" in plan.chunks[0]

    def test_the_markers_are_the_same_words_the_terminal_uses(self) -> None:
        """与 `builtins/cli_entry/console.py::TERMINAL_MARKERS` 逐字相同。

        `R4` 够不着那个模块，因此这里是第二份字面量——两处不一致时「被中断」在不同
        Channel 上会读起来不一样，而那正是用户最需要一眼认出的一句话。
        """
        assert TERMINAL_MARKERS[StreamState.CANCELLED] == "[已中断：以上是中断前已产生的内容]"
        assert TERMINAL_MARKERS[StreamState.FAILED] == "[本轮失败]"


class TestPlan:
    def test_a_url_attachment_becomes_a_line(self) -> None:
        ref = AttachmentRef(
            source=AttachmentSource.URL, locator="https://cdn.test/a.png", media_type="image/png"
        )
        plan = plan_outbound(outbound("看这个", attachments=(ref,)))
        assert "https://cdn.test/a.png" in plan.chunks[0]

    def test_a_workspace_attachment_says_so_instead_of_pretending(self) -> None:
        """`FileAccess` 没有 `read_bytes`，本轮传不出去。假装发过比说不出去更糟。"""
        ref = AttachmentRef(
            source=AttachmentSource.WORKSPACE,
            locator="notes/a.md",
            media_type="text/markdown",
            filename="a.md",
        )
        plan = plan_outbound(outbound("给你", attachments=(ref,)))
        assert "无法上传" in plan.chunks[0]

    def test_only_the_first_chunk_carries_the_reply_reference(self) -> None:
        """每块都引用会在频道里刷出一串重复的引用条。"""
        plan = plan_outbound(outbound("答案", reply_to="7"))
        assert plan.reply_to == "7"

    def test_a_plan_with_no_chunks_reports_itself_empty(self) -> None:
        """`FINAL` 恒有正文（契约在构造时就拒绝空的），因此空计划只可能来自别处。"""
        assert SendPlan().empty is True
        assert plan_outbound(outbound("答案")).empty is False
