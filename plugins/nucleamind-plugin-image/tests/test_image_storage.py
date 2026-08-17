"""`storage.py` 的用例：两种落点、内容寻址的文件名、原子写、产物与附件引用。

真的写盘（`tmp_path`），因为「函数是对的」不等于「调用它的那条路径是对的」——
`builtins/tools_shell` 的环境哨兵用例是同一种做法。

`D47` 之后落点有两种：默认的 workspace（走 `ctx.fs`，交得出附件）与运维配置的绝对路径
（走 `pathlib`，交不出附件）。**两者都要测「交不交得出附件」**——那正是这一轮的正事。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from _image_fakes import PNG_BYTES, FakeWorkspace, ImageContext
from nucleamind_plugin_image import IMAGE_DIR_NAME, build_store, resolve_settings
from nucleamind_plugin_image.storage import (
    LocalImageStore,
    WorkspaceImageStore,
    digest_name,
)

from nucleamind.contracts import ArtifactRef, AttachmentSource, ErrorCode, NucleaError


class TestDigestName:
    def test_the_same_bytes_always_get_the_same_name(self) -> None:
        """内容寻址：重跑不会堆出一堆一模一样的图。"""
        assert digest_name(PNG_BYTES, "image/png") == digest_name(PNG_BYTES, "image/png")

    def test_different_bytes_get_different_names(self) -> None:
        assert digest_name(b"a", "image/png") != digest_name(b"b", "image/png")

    def test_the_extension_follows_the_media_type(self) -> None:
        assert digest_name(PNG_BYTES, "image/jpeg").endswith(".jpg")

    def test_the_prompt_never_appears_in_a_filename(self) -> None:
        """prompt 可能很长、可能带路径分隔符，也可能包含用户不想留在磁盘上的内容。
        名字只由字节决定，因此这条是结构性成立的——这里断言的是它的可观察形态。"""
        name = digest_name(PNG_BYTES, "image/png")
        assert name.startswith("image-")
        assert "/" not in name and "\\" not in name and " " not in name


class TestWorkspaceImageStore:
    async def test_it_writes_through_the_facade(self, tmp_path: Path) -> None:
        workspace = FakeWorkspace(tmp_path)
        saved = await WorkspaceImageStore(workspace, IMAGE_DIR_NAME).save(PNG_BYTES, "image/png")
        assert (tmp_path / saved.locator).read_bytes() == PNG_BYTES
        assert saved.size_bytes == len(PNG_BYTES)

    async def test_the_locator_is_a_workspace_relative_posix_path(self, tmp_path: Path) -> None:
        """`AttachmentRef` 按契约拒绝绝对路径与上跳段——这条就是那个前提。"""
        saved = await WorkspaceImageStore(FakeWorkspace(tmp_path), "artifacts/images").save(
            PNG_BYTES, "image/png"
        )
        assert saved.locator.startswith("artifacts/images/")
        assert not Path(saved.locator).is_absolute()

    async def test_the_attachment_and_the_artifact_point_at_the_same_thing(
        self, tmp_path: Path
    ) -> None:
        """两个引用是两个消费者，不是两份真相：Channel 读的和后续工具读的必须是同一个。"""
        saved = await WorkspaceImageStore(FakeWorkspace(tmp_path), IMAGE_DIR_NAME).save(
            PNG_BYTES, "image/png"
        )
        assert isinstance(saved.artifact, ArtifactRef)
        assert saved.attachment is not None
        assert saved.attachment.locator == saved.artifact.locator == saved.locator
        assert saved.attachment.source is AttachmentSource.WORKSPACE
        assert saved.attachment.media_type == "image/png"
        assert saved.attachment.size_bytes == len(PNG_BYTES)
        assert saved.attachment.filename == digest_name(PNG_BYTES, "image/png")

    async def test_saving_twice_lands_on_one_file(self, tmp_path: Path) -> None:
        store = WorkspaceImageStore(FakeWorkspace(tmp_path), IMAGE_DIR_NAME)
        first = await store.save(PNG_BYTES, "image/png")
        second = await store.save(PNG_BYTES, "image/png")
        assert first.locator == second.locator

    async def test_facade_failures_are_passed_through(self, tmp_path: Path) -> None:
        """门面的错误 `detail` 比这里能补的更准确，再包一层只会把位置埋掉。"""

        class Refusing(FakeWorkspace):
            async def write_bytes(self, path: str, data: bytes) -> None:
                del path, data
                raise NucleaError(ErrorCode.PERMISSION_DENIED, "没有 fs:write。")

        with pytest.raises(NucleaError) as caught:
            await WorkspaceImageStore(Refusing(tmp_path), IMAGE_DIR_NAME).save(
                PNG_BYTES, "image/png"
            )
        assert caught.value.code is ErrorCode.PERMISSION_DENIED


class TestLocalImageStore:
    async def test_it_writes_the_bytes_and_creates_the_directory(self, tmp_path: Path) -> None:
        saved = await LocalImageStore(tmp_path / "nested" / "images").save(PNG_BYTES, "image/png")
        assert Path(saved.locator).read_bytes() == PNG_BYTES
        assert saved.size_bytes == len(PNG_BYTES)

    async def test_no_temporary_file_survives(self, tmp_path: Path) -> None:
        """写走「同目录临时文件 → fsync → os.replace」，成功之后目录里只有成品。"""
        await LocalImageStore(tmp_path).save(PNG_BYTES, "image/png")
        assert [p.name for p in tmp_path.iterdir()] == [digest_name(PNG_BYTES, "image/png")]

    async def test_saving_twice_is_idempotent(self, tmp_path: Path) -> None:
        store = LocalImageStore(tmp_path)
        first = await store.save(PNG_BYTES, "image/png")
        second = await store.save(PNG_BYTES, "image/png")
        assert first.locator == second.locator
        assert len(list(tmp_path.iterdir())) == 1

    async def test_it_cannot_offer_an_attachment(self, tmp_path: Path) -> None:
        """绝对路径落点交不出附件——把宿主机绝对路径交给 Channel 去读正是契约要挡的事。"""
        saved = await LocalImageStore(tmp_path).save(PNG_BYTES, "image/png")
        assert saved.attachment is None
        assert saved.artifact.locator == Path(saved.locator).as_posix()

    async def test_a_write_failure_reports_errno_not_the_path(self, tmp_path: Path) -> None:
        """路径是宿主机信息，而这条错误会被折进模型可见的工具结果里（`D20` 的先例）。"""
        blocker = tmp_path / "blocked"
        blocker.write_bytes(b"not a directory")
        with pytest.raises(NucleaError) as caught:
            await LocalImageStore(blocker / "images").save(PNG_BYTES, "image/png")
        assert caught.value.code is ErrorCode.PERSISTENCE_WRITE_FAILED
        assert set(caught.value.detail) == {"errno", "reason"}


class TestBuildStore:
    def test_the_default_is_the_workspace_artifacts_directory(self, tmp_path: Path) -> None:
        store = build_store(ImageContext(tmp_path), resolve_settings({}), files=FakeWorkspace(tmp_path))
        assert isinstance(store, WorkspaceImageStore)
        assert store.location == f"<workspace>/{IMAGE_DIR_NAME}"

    def test_a_relative_dir_resolves_against_the_workspace(self, tmp_path: Path) -> None:
        """`D47` 之前它按 `ctx.state_dir` 解析。改的理由：生成的图是用户的交付物。"""
        store = build_store(
            ImageContext(tmp_path), resolve_settings({"dir": "renders"}), files=FakeWorkspace(tmp_path)
        )
        assert isinstance(store, WorkspaceImageStore)
        assert store.location == "<workspace>/renders"

    def test_an_absolute_dir_is_taken_as_written(self, tmp_path: Path) -> None:
        elsewhere = tmp_path / "elsewhere"
        settings = resolve_settings({"dir": str(elsewhere)})
        store = build_store(ImageContext(tmp_path), settings, files=FakeWorkspace(tmp_path))
        assert isinstance(store, LocalImageStore)
        assert store.root == elsewhere
