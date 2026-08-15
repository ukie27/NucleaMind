"""`storage.py` 的用例：落点、内容寻址的文件名、原子写、`ArtifactRef`。

真的写盘（`tmp_path`），因为「函数是对的」不等于「调用它的那条路径是对的」——
`builtins/tools_shell` 的环境哨兵用例是同一种做法。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from _image_fakes import PNG_BYTES, ImageContext
from nucleamind_plugin_image import IMAGE_DIR_NAME, image_directory, resolve_settings
from nucleamind_plugin_image.storage import ImageStore, digest_name

from nucleamind.contracts import ArtifactRef, ErrorCode, NucleaError


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


class TestImageStore:
    def test_it_writes_the_bytes_and_creates_the_directory(self, tmp_path: Path) -> None:
        store = ImageStore(tmp_path / "nested" / "images")
        saved = store.save(PNG_BYTES, "image/png")
        assert saved.path.read_bytes() == PNG_BYTES
        assert saved.size_bytes == len(PNG_BYTES)

    def test_no_temporary_file_survives(self, tmp_path: Path) -> None:
        """写走「同目录临时文件 → fsync → os.replace」，成功之后目录里只有成品。"""
        store = ImageStore(tmp_path)
        store.save(PNG_BYTES, "image/png")
        assert [p.name for p in tmp_path.iterdir()] == [digest_name(PNG_BYTES, "image/png")]

    def test_saving_twice_is_idempotent(self, tmp_path: Path) -> None:
        store = ImageStore(tmp_path)
        first = store.save(PNG_BYTES, "image/png")
        second = store.save(PNG_BYTES, "image/png")
        assert first.path == second.path
        assert len(list(tmp_path.iterdir())) == 1

    def test_the_artifact_carries_the_path_media_type_and_size(self, tmp_path: Path) -> None:
        saved = ImageStore(tmp_path).save(PNG_BYTES, "image/png")
        assert isinstance(saved.artifact, ArtifactRef)
        assert saved.artifact.locator == saved.path.as_posix()
        assert saved.artifact.media_type == "image/png"
        assert saved.artifact.size_bytes == len(PNG_BYTES)

    def test_a_write_failure_reports_errno_not_the_path(self, tmp_path: Path) -> None:
        """路径是宿主机信息，而这条错误会被折进模型可见的工具结果里（`D20` 的先例）。"""
        blocker = tmp_path / "blocked"
        blocker.write_bytes(b"not a directory")
        store = ImageStore(blocker / "images")
        with pytest.raises(NucleaError) as caught:
            store.save(PNG_BYTES, "image/png")
        assert caught.value.code is ErrorCode.PERSISTENCE_WRITE_FAILED
        assert set(caught.value.detail) == {"errno", "reason"}


class TestImageDirectory:
    def test_the_default_is_under_the_state_dir(self, tmp_path: Path) -> None:
        ctx = ImageContext(tmp_path)
        assert image_directory(ctx, resolve_settings({})) == tmp_path / IMAGE_DIR_NAME

    def test_a_relative_dir_resolves_against_the_state_dir(self, tmp_path: Path) -> None:
        """`nm` 从哪个目录启动不该改变图存到哪里。"""
        ctx = ImageContext(tmp_path)
        settings = resolve_settings({"dir": "renders"})
        assert image_directory(ctx, settings) == tmp_path / "renders"

    def test_an_absolute_dir_is_taken_as_written(self, tmp_path: Path) -> None:
        elsewhere = tmp_path / "elsewhere"
        ctx = ImageContext(tmp_path)
        settings = resolve_settings({"dir": str(elsewhere)})
        assert image_directory(ctx, settings) == elsewhere
