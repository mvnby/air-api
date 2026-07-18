import os
import stat
from pathlib import Path

import pytest

from scripts.ha.sync_bot_voice_env import render_env, sync_env


def test_render_env_replaces_duplicates_and_preserves_unrelated_values():
    rendered = render_env(
        "OTHER=value\nBOT_VOICE_TRANSCRIPTION_API_KEY=old\n"
        "BOT_VOICE_TRANSCRIPTION_API_KEY=duplicate\n",
        "gsk_test_secret",
    )

    assert "OTHER=value" in rendered
    assert rendered.count("BOT_VOICE_TRANSCRIPTION_API_KEY=") == 1
    assert "BOT_VOICE_TRANSCRIPTION_API_KEY=gsk_test_secret" in rendered
    assert "BOT_VOICE_TRANSCRIPTION_ENABLED=true" in rendered
    assert (
        "BOT_VOICE_TRANSCRIPTION_API_URL="
        "https://api.groq.com/openai/v1/audio/transcriptions" in rendered
    )
    assert "BOT_VOICE_TRANSCRIPTION_MODEL=whisper-large-v3-turbo" in rendered


def test_sync_env_is_atomic_and_preserves_mode(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text("OTHER=value\n", encoding="utf-8")
    env_file.chmod(0o640)

    sync_env(env_file, "gsk_test_secret")

    assert "OTHER=value" in env_file.read_text(encoding="utf-8")
    assert "BOT_VOICE_TRANSCRIPTION_API_KEY=gsk_test_secret" in env_file.read_text(
        encoding="utf-8"
    )
    assert stat.S_IMODE(env_file.stat().st_mode) == 0o640
    assert not list(tmp_path.glob("..env.*"))


def test_sync_env_rejects_symlink_and_malformed_secret(tmp_path: Path):
    target = tmp_path / "target.env"
    target.write_text("OTHER=value\n", encoding="utf-8")
    symlink = tmp_path / ".env"
    symlink.symlink_to(target)

    with pytest.raises(ValueError, match="non-symlink"):
        sync_env(symlink, "gsk_test_secret")
    with pytest.raises(ValueError, match="malformed"):
        render_env("", "bad\nsecret")


def test_sync_env_preserves_owner_when_running_as_current_user(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text("OTHER=value\n", encoding="utf-8")
    before = env_file.stat()

    sync_env(env_file, "gsk_test_secret")

    after = env_file.stat()
    assert (after.st_uid, after.st_gid) == (os.getuid(), os.getgid())
