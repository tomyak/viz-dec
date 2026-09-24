import fcntl
import os
import stat
import sys
import tempfile
from pathlib import Path

import pytest

from visual_decider.adapters import shared


@pytest.fixture
def temp_root(monkeypatch):
    # Deliberately short, including when pytest's own temp paths exceed sun_path.
    with tempfile.TemporaryDirectory(prefix="vdt-", dir="/tmp") as root:
        monkeypatch.setenv("TMPDIR", root)
        yield Path(root)


def test_runtime_respects_tmpdir_and_is_private(tmp_path, temp_root):
    runtime = shared.runtime_directory(tmp_path)
    assert runtime.parent == temp_root
    assert stat.S_IMODE(runtime.stat().st_mode) == 0o700
    assert shared.runtime_directory(tmp_path) == runtime
    assert shared.runtime_directory(tmp_path / "other") != runtime
    assert not (runtime / "engine.lock").exists()


def test_runtime_rejects_symlinks_and_public_directories(tmp_path, temp_root):
    runtime = shared.runtime_directory(tmp_path)
    runtime.chmod(0o755)
    with pytest.raises(PermissionError, match="owner-only"):
        shared.runtime_directory(tmp_path)
    runtime.rmdir()
    runtime.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(PermissionError, match="owner-only"):
        shared.runtime_directory(tmp_path)


def test_invalid_tmpdir_never_falls_back(tmp_path, monkeypatch):
    monkeypatch.setenv("TMPDIR", "relative")
    with pytest.raises(ValueError, match="absolute"):
        shared.runtime_directory(tmp_path)
    monkeypatch.setenv("TMPDIR", "/" + "long" * 30)
    with pytest.raises(ValueError, match="too long"):
        shared.runtime_directory(tmp_path)
    monkeypatch.setenv("TMPDIR", f"/tmp/missing-{os.getpid()}/nested")
    with pytest.raises(FileNotFoundError):
        shared.runtime_directory(tmp_path)


def test_unix_discovery_root_does_not_follow_tmpdir_override(tmp_path, temp_root, monkeypatch):
    monkeypatch.setattr(shared.sys, "platform", "linux")
    assert shared.user_temp_directory() == Path("/tmp")
    preferred = shared.runtime_directory(tmp_path, create=False)
    assert preferred.parent == temp_root
    candidates = shared.runtime_candidates(tmp_path, preferred)
    assert shared.runtime_directory(tmp_path, root="/tmp", create=False) in candidates
    assert list(temp_root.iterdir()) == []


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS user temp directory")
def test_mcp_host_without_tmpdir_finds_macos_user_directory(tmp_path, monkeypatch):
    import subprocess

    expected = Path(
        subprocess.check_output(["/usr/bin/getconf", "DARWIN_USER_TEMP_DIR"], text=True).strip()
    )
    monkeypatch.delenv("TMPDIR", raising=False)
    runtime = shared.runtime_directory(tmp_path)
    try:
        assert runtime.parent == expected
    finally:
        runtime.rmdir()


def test_read_only_installation_lock_is_shared_across_tmpdirs(tmp_path, temp_root, monkeypatch):
    first = shared.runtime_directory(tmp_path)
    descriptors = shared.acquire_engine_locks(tmp_path)
    try:
        second_root = temp_root / "two"
        second_root.mkdir()
        monkeypatch.setenv("TMPDIR", str(second_root))
        assert shared.runtime_directory(tmp_path) != first
        with pytest.raises(BlockingIOError):
            shared.acquire_engine_locks(tmp_path)
        assert list(tmp_path.iterdir()) == []  # No new lock or metadata files.
    finally:
        for fd in descriptors:
            os.close(fd)
    for fd in shared.acquire_engine_locks(tmp_path):
        os.close(fd)


def test_upgrade_cannot_overlap_a_legacy_daemon(tmp_path):
    legacy = Path("/tmp") / f"visual-decider-{os.getuid()}-{shared.installation_digest(tmp_path)}"
    legacy.mkdir(mode=0o700)
    try:
        with (legacy / "engine.lock").open("w") as old:
            fcntl.flock(old, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with pytest.raises(BlockingIOError):
                shared.acquire_engine_locks(tmp_path)
        # Failure releases the directory lock too; retry after the old process exits.
        descriptors = shared.acquire_engine_locks(tmp_path)
        try:
            assert len(descriptors) == 2
            with (legacy / "engine.lock").open("r") as old:
                with pytest.raises(BlockingIOError):
                    fcntl.flock(old, fcntl.LOCK_EX | fcntl.LOCK_NB)
        finally:
            for fd in descriptors:
                os.close(fd)
    finally:
        (legacy / "engine.lock").unlink()
        legacy.rmdir()
