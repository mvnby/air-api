import json
import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BOOTSTRAP = REPO_ROOT / "scripts/bootstrap_web_atomic_nginx.sh"
PROMOTE = REPO_ROOT / "scripts/promote_web_release.sh"
DEPLOY = REPO_ROOT / "scripts/deploy_web_atomic.sh"
RELEASE_ID = "a" * 40


def _executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def _fake_bin(tmp_path: Path) -> tuple[Path, Path]:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    command_log = tmp_path / "commands.log"
    _executable(fake_bin / "flock", "#!/usr/bin/env bash\nexit 0\n")
    _executable(
        fake_bin / "nginx",
        """#!/usr/bin/env bash
printf 'nginx %s\n' "$*" >> "$COMMAND_LOG"
[[ "${NGINX_FAIL:-false}" != "true" ]]
""",
    )
    _executable(
        fake_bin / "systemctl",
        "#!/usr/bin/env bash\nprintf 'systemctl %s\n' \"$*\" >> \"$COMMAND_LOG\"\n",
    )
    _executable(
        fake_bin / "curl",
        """#!/usr/bin/env bash
printf 'curl %s\n' "$*" >> "$COMMAND_LOG"
[[ "${CURL_FAIL:-false}" != "true" ]]
""",
    )
    return fake_bin, command_log


def test_nginx_bootstrap_switches_to_live_symlink_without_changing_content(tmp_path):
    fake_bin, command_log = _fake_bin(tmp_path)
    web_root = tmp_path / "web"
    current = web_root / "current"
    current.mkdir(parents=True)
    (current / "index.html").write_text("legacy", encoding="utf-8")
    nginx_site = tmp_path / "mvn.by"
    nginx_site.write_text(
        f"server {{ root {current}; }}\nserver {{ root {current}; }}\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}:{env['PATH']}",
            "COMMAND_LOG": str(command_log),
            "WEB_ROOT": str(web_root),
            "WEB_NGINX_SITE_FILE": str(nginx_site),
            "CONFIRM_WEB_NGINX_BOOTSTRAP": "true",
        }
    )

    result = subprocess.run(["bash", str(BOOTSTRAP)], env=env, text=True, capture_output=True, check=False)

    assert result.returncode == 0, result.stderr
    live = web_root / "live"
    assert live.is_symlink()
    assert live.resolve() == current
    assert f"root {live};" in nginx_site.read_text(encoding="utf-8")
    assert (live / "index.html").read_text(encoding="utf-8") == "legacy"
    assert "systemctl reload nginx" in command_log.read_text(encoding="utf-8")


def _release_environment(tmp_path: Path, *, curl_fail: bool = False) -> tuple[dict[str, str], Path]:
    fake_bin, _ = _fake_bin(tmp_path)
    web_root = tmp_path / "web"
    current = web_root / "current"
    incoming = web_root / "releases" / f".{RELEASE_ID}.incoming"
    (incoming / "catalog").mkdir(parents=True)
    current.mkdir(parents=True)
    (current / "index.html").write_text("legacy", encoding="utf-8")
    (incoming / "index.html").write_text("candidate", encoding="utf-8")
    (incoming / "catalog/index.html").write_text("catalog", encoding="utf-8")
    (incoming / "release.json").write_text(json.dumps({"sha": RELEASE_ID}), encoding="utf-8")
    (web_root / "live").symlink_to(current)
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}:{env['PATH']}",
            "COMMAND_LOG": str(tmp_path / "commands.log"),
            "WEB_ROOT": str(web_root),
            "WEB_RELEASE_ID": RELEASE_ID,
            "WEB_DEPLOY_SUMMARY_FILE": str(tmp_path / "summary.txt"),
            "CURL_FAIL": "true" if curl_fail else "false",
        }
    )
    return env, web_root


def test_promote_release_atomically_updates_live_link(tmp_path):
    env, web_root = _release_environment(tmp_path)

    result = subprocess.run(["bash", str(PROMOTE)], env=env, text=True, capture_output=True, check=False)

    assert result.returncode == 0, result.stderr
    release = web_root / "releases" / RELEASE_ID
    assert (web_root / "live").resolve() == release
    assert (release / "index.html").read_text(encoding="utf-8") == "candidate"
    assert (web_root / "current/index.html").read_text(encoding="utf-8") == "legacy"
    assert "status=activated" in Path(env["WEB_DEPLOY_SUMMARY_FILE"]).read_text(encoding="utf-8")


def test_promote_release_restores_previous_link_when_origin_smoke_fails(tmp_path):
    env, web_root = _release_environment(tmp_path, curl_fail=True)
    previous = (web_root / "live").resolve()

    result = subprocess.run(["bash", str(PROMOTE)], env=env, text=True, capture_output=True, check=False)

    assert result.returncode != 0
    assert (web_root / "live").resolve() == previous
    assert "restored" in result.stdout


def test_local_deploy_uploads_only_to_incoming_release(tmp_path):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    command_log = tmp_path / "commands.log"
    _executable(
        fake_bin / "ssh",
        "#!/usr/bin/env bash\nprintf 'ssh %s\n' \"$*\" >> \"$COMMAND_LOG\"\ncat >/dev/null || true\n",
    )
    _executable(
        fake_bin / "rsync",
        "#!/usr/bin/env bash\nprintf 'rsync %s\n' \"$*\" >> \"$COMMAND_LOG\"\n",
    )
    _executable(fake_bin / "sleep", "#!/usr/bin/env bash\nexit 0\n")
    dist = tmp_path / "dist"
    (dist / "catalog").mkdir(parents=True)
    (dist / "index.html").write_text("index", encoding="utf-8")
    (dist / "catalog/index.html").write_text("catalog", encoding="utf-8")
    (dist / "release.json").write_text(json.dumps({"sha": RELEASE_ID}), encoding="utf-8")
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}:{env['PATH']}",
            "COMMAND_LOG": str(command_log),
            "WEB_HOST": "web.test",
            "WEB_RELEASE_ID": RELEASE_ID,
            "WEB_DIST_DIR": str(dist),
            "WEB_PROMOTE_HELPER_SOURCE": str(PROMOTE),
        }
    )

    result = subprocess.run(["bash", str(DEPLOY)], env=env, text=True, capture_output=True, check=False)

    assert result.returncode == 0, result.stderr
    rsync_call = next(line for line in command_log.read_text(encoding="utf-8").splitlines() if line.startswith("rsync "))
    assert f"releases/.{RELEASE_ID}.incoming/" in rsync_call
    assert "/current/" not in rsync_call
    assert "/live/" not in rsync_call
