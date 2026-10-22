#!/usr/bin/env python3
"""Transaction-owned memory relief for a provably idle primary canary worker.

Runs on the host using only stdlib and psql in the existing DB container. Never
imports the application, changes delivery controls, or drains active providers.
The caller holds and verifies the real inherited deployment lock.
"""

from __future__ import annotations

import contextlib
import json
import os
from pathlib import Path
import re
import selectors
import signal
import stat
import subprocess
import sys
import tempfile
import urllib.request


IMAGE = re.compile(r".+(?:@sha256:[0-9a-f]{64}|:[0-9a-f]{40})$")
COMMAND_TIMEOUT_SECONDS = 40
IDLE_SQL = """
BEGIN;
SET LOCAL lock_timeout = '2s';
SET LOCAL statement_timeout = '5s';
SET LOCAL idle_in_transaction_session_timeout = '120s';
WITH control AS MATERIALIZED (
  SELECT * FROM communication_runtime_state WHERE channel = 'telegram' FOR UPDATE
)
SELECT json_build_object(
  'primary', NOT pg_is_in_recovery(), 'mode', mode, 'status', status,
  'revision', control_revision,
  'fresh', heartbeat_at BETWEEN now() - interval '30 seconds' AND now(),
  'running', (SELECT count(*) FROM communication_delivery WHERE status = 'running')
) FROM control;
"""


class GuardError(RuntimeError):
    pass


class GuardInterrupted(GuardError):
    pass


class IdleWorkerGuard:
    def __init__(self):
        self.project = Path(os.environ.get("API_PROJECT_DIR", "/opt/air-api"))
        self.canonical = os.environ.get(
            "PATRONI_CANONICAL_COMPOSE_FILE", str(self.project / "docker-compose.patroni.yml")
        )
        self.journal = self.project / ".ha-idle-worker-capacity.json"
        self.marker = self.project / ".ha-communications-worker-release-fenced"
        self.service = "communications-worker"
        self.compose = ["docker", "compose", "-f", self.canonical, "--profile", "bluegreen"]
        self.release_helper = os.environ["COMMUNICATIONS_WORKER_RELEASE_HELPER"]
        self.lock_helper = os.environ["API_DEPLOY_LOCK_HELPER"]
        self.env = os.environ.copy()

    def run(self, args, *, check=True, env=None, operation=None, **kwargs):
        process = subprocess.Popen(
            args, cwd=self.project, env=env or self.env, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            start_new_session=True, pass_fds=(9,), **kwargs,
        )
        try:
            output, errors = process.communicate(timeout=COMMAND_TIMEOUT_SECONDS)
        except BaseException:
            # A shell/Compose grandchild must not outlive the authorizing guard.
            # Kill the entire command group before any transaction recovery.
            with contextlib.suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)
            process.communicate(timeout=5)
            raise
        result = subprocess.CompletedProcess(args, process.returncode, output, errors)
        if check and result.returncode:
            # Docker inspect/Compose output can contain secrets. Never relay it.
            raise GuardError(
                f"idle worker command failed: {operation or Path(args[0]).name} "
                f"(exit={result.returncode})"
            )
        return result

    def verify_lock(self):
        if self.env.get("API_DEPLOY_LOCK_FD") != "9":
            raise GuardError("idle worker guard requires inherited deploy lock fd 9")
        self.run([sys.executable, self.lock_helper, "verify", str(self.project / ".deploy.lock"), "9"])

    def safe_file(self, path, *, mode=0o600):
        metadata = path.lstat()
        if (not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.geteuid()
                or metadata.st_nlink != 1 or stat.S_IMODE(metadata.st_mode) != mode):
            raise GuardError("idle worker state file metadata is unsafe")

    def load(self):
        if not os.path.lexists(self.journal):
            return None
        self.safe_file(self.journal)
        with self.journal.open() as stream:
            record = json.load(stream)
        if (not isinstance(record, dict)
                or set(record) != {"version", "image", "revision", "phase", "operation"}
                or record["version"] != 1 or not isinstance(record["image"], str)
                or not IMAGE.fullmatch(record["image"])
                or type(record["revision"]) is not int or record["revision"] < 0
                or record["phase"] not in {"paused", "promoted", "uncertain"}
                or record["operation"] not in {"migrate", "deploy"}):
            raise GuardError("idle worker recovery record is invalid")
        return record

    def write(self, record):
        metadata = self.project.lstat()
        if (not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != os.geteuid()
                or metadata.st_mode & 0o022):
            raise GuardError("idle worker journal parent is unsafe")
        descriptor, temporary = tempfile.mkstemp(prefix=".idle-worker.", dir=self.project)
        try:
            with os.fdopen(descriptor, "w") as stream:
                json.dump(record, stream, sort_keys=True)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.journal)
            self.sync_directory()
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def sync_directory(self):
        descriptor = os.open(self.project, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def clear(self):
        self.safe_file(self.journal)
        self.journal.unlink()
        self.sync_directory()

    def require_primary(self):
        url = self.env.get("API_PATRONI_URL", "http://127.0.0.1:8008/patroni")
        with urllib.request.urlopen(url, timeout=5) as response:
            payload = json.load(response)
        if payload.get("state") != "running" or payload.get("role") not in {"leader", "master", "primary"}:
            raise GuardError("idle worker recovery requires a freshly proven primary")

    def api_image(self):
        slot = self.project / ".active-api-slot"
        service = "app"
        if slot.exists():
            active = slot.read_text().strip()
            if active not in {"blue", "green"}:
                raise GuardError("active API slot is invalid")
            service += "-" + active
        ids = self.run([*self.compose, "ps", "--status", "running", "-q", service]).stdout.split()
        if len(ids) != 1:
            raise GuardError("active API runtime is ambiguous")
        image = self.run(
            ["docker", "inspect", "--format", "{{.Config.Image}}", ids[0]],
            operation="inspect active API image",
        ).stdout.strip()
        if not IMAGE.fullmatch(image):
            raise GuardError("active API image is not immutable")
        return image

    def running_ids(self):
        return self.run(
            [*self.compose, "ps", "--status", "running", "-q", self.service],
            operation="query running communications worker",
        ).stdout.split()

    def require_worker(self, image):
        ids = self.running_ids()
        if len(ids) != 1:
            raise GuardError("idle worker runtime is ambiguous")
        payload = json.loads(self.run(
            ["docker", "inspect", ids[0]], operation="inspect communications worker",
        ).stdout)
        config = payload[0]["Config"]
        environment = dict(item.split("=", 1) for item in config["Env"] if "=" in item)
        if (config["Image"] != image or not payload[0]["State"]["Running"]
                or environment.get("APP_ROLE") != "primary"
                or environment.get("COMMUNICATIONS_WORKER_ENABLED") != "true"
                or environment.get("COMMUNICATIONS_WORKER_ALLOW_ALL_MODE") != "false"):
            raise GuardError("idle worker image, role, or canary gates differ")

    def release(self, action, image):
        env = {**self.env, "BACKEND_IMAGE": image, "IDLE_CANONICAL_FILE": self.canonical}
        script = '''set -Eeuo pipefail
PROJECT_DIR="$API_PROJECT_DIR"
COMMUNICATIONS_WORKER_SERVICE=communications-worker
source "$COMMUNICATIONS_WORKER_RELEASE_HELPER"
COMPOSE=(docker compose -f "$IDLE_CANONICAL_FILE" --profile bluegreen)
'''
        if action == "fence":
            script += "communications_worker_set_release_fence\n"
        elif action == "start":
            script += "communications_worker_start_controlled primary canary\n"
        else:
            script += "communications_worker_require_contract canary\n"
        try:
            self.run(["bash", "-c", script], env=env, operation=f"{action} communications worker")
        except (subprocess.TimeoutExpired, GuardInterrupted):
            if action == "start":
                # Docker may already have accepted a recreate. Never race that
                # operation with an automatic restart of the original image.
                self.mark_uncertain(image)
            raise

    def mark_uncertain(self, image):
        record = self.load()
        if record:
            record["phase"] = "uncertain"
            self.write(record)
        self.release("fence", image)

    @contextlib.contextmanager
    def control_lock(self):
        # The lock prevents an operator gate switch between idle proof and stop/start.
        # Heartbeats/terminal status also update this row: never wait for those
        # writes while holding it. Prove the container stopped, then release SQL.
        command = [*self.compose, "exec", "-T", "db", "sh", "-lc",
                   'exec psql -XqAt -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" '
                   '-d "${POSTGRES_DB:-air_conditioners}"']
        with tempfile.TemporaryFile(mode="w+") as errors:
            process = subprocess.Popen(command, cwd=self.project, env=self.env, text=True,
                                       start_new_session=True,
                                       stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errors)
            try:
                signal.alarm(60)  # Always shorter than the server-side idle lock expiry.
                process.stdin.write(IDLE_SQL)
                process.stdin.flush()
                with selectors.DefaultSelector() as selector:
                    selector.register(process.stdout, selectors.EVENT_READ)
                    if not selector.select(timeout=8):
                        raise GuardError("idle worker control lock timed out")
                line = process.stdout.readline()
                if not line:
                    raise GuardError("idle worker control proof failed")
                proof = json.loads(line)
                if proof.get("primary") is not True or proof.get("mode") != "all" or proof.get("running") != 0:
                    raise GuardError("active or inconclusive deliveries; worker suspension refused")
                yield proof
                process.stdin.write("ROLLBACK;\n\\q\n")
                process.stdin.flush()
                if process.wait(timeout=5):
                    raise GuardError("idle worker control lock connection failed")
            finally:
                signal.alarm(0)
                if process.poll() is None:
                    process.stdin.close()  # EOF aborts the transaction, including on TERM.
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        with contextlib.suppress(ProcessLookupError):
                            os.killpg(process.pid, signal.SIGKILL)
                        process.wait(timeout=5)
                process.stdout.close()
                if not process.stdin.closed:
                    process.stdin.close()

    def prepare(self, operation):
        if self.load():
            raise GuardError("recover the previous idle worker journal before capture")
        if self.run(["bash", "-c", 'source "$API_DEPLOY_CAPACITY_HELPER"; require_deploy_capacity'], check=False).returncode == 0:
            return
        expected_role = self.env.get("API_EXPECTED_PATRONI_ROLE", "")
        if expected_role != "primary" and not (operation == "migrate" and not expected_role):
            return  # The unchanged downstream guard still rejects insufficient capacity.
        self.require_primary()
        if os.path.lexists(self.marker):
            self.safe_file(self.marker)
            return  # A pre-existing fence is never lifted for memory relief.
        image = self.api_image()
        self.release("contract", image)
        self.require_worker(image)
        with self.control_lock() as proof:
            if proof.get("status") != "paused" or proof.get("fresh") is not True:
                raise GuardError("idle worker heartbeat does not prove an idle paused runtime")
            self.write({"version": 1, "image": image, "revision": proof["revision"],
                        "phase": "paused", "operation": operation})
            self.release("fence", image)
            try:
                stopped = self.run([*self.compose, "stop", self.service], check=False)
            except (subprocess.TimeoutExpired, GuardInterrupted):
                if self.running_ids():
                    self.mark_uncertain(image)
                raise
            if stopped.returncode < 0:
                raise GuardError(
                    f"stop communications worker interrupted (exit={stopped.returncode}); "
                    "recovery record retained"
                )
            # The role agent enforces this same fence with stop + rm and may
            # remove the container while Compose stop is waiting. Accept a
            # failed stop only when successful all-state inventory proves that
            # this canonical project's worker no longer exists. Even exited
            # containers remain a failure here; recovery owns all other cases.
            if stopped.returncode and self.run(
                [*self.compose, "ps", "--all", "-q", self.service],
                operation="query all communications worker containers",
            ).stdout.split():
                raise GuardError(
                    f"stop communications worker left a container (exit={stopped.returncode}); "
                    "recovery record retained"
                )
            if self.running_ids():
                raise GuardError(
                    f"stop communications worker did not prove stopped (exit={stopped.returncode}); "
                    "recovery record retained"
                )
            self.safe_file(self.marker)
        print("idle communications worker suspended inside release transaction")

    def recover(self):
        record = self.load()
        if record is None:
            return
        if record["phase"] != "paused":
            raise GuardError("promoted or uncertain release; retain fence and journal for inspection")
        self.require_primary()
        image = self.api_image()
        if image != record["image"]:
            raise GuardError("API image changed since worker suspension; retain fence for inspection")
        self.release("contract", image)
        with self.control_lock() as proof:
            if proof.get("revision") != record["revision"]:
                raise GuardError("communications control revision changed; worker restoration refused")
            self.require_primary()
            if self.api_image() != image:
                raise GuardError("active API changed before worker restoration")
            if os.path.lexists(self.marker) or not self.running_ids():
                self.release("start", image)
            self.require_worker(image)
        self.clear()
        print("original idle communications worker restored")

    def promoted(self):
        record = self.load()
        if record:
            record["phase"] = "promoted"
            self.write(record)

    def complete(self):
        record = self.load()
        if not record:
            return
        self.require_primary()
        image = self.api_image()
        if image != self.env.get("BACKEND_IMAGE") or os.path.lexists(self.marker):
            raise GuardError("new worker release is not verified; retain recovery journal")
        self.release("contract", image)
        with self.control_lock() as proof:
            if proof.get("revision") != record["revision"]:
                raise GuardError("communications control changed during candidate release")
            self.require_worker(image)
        self.clear()

    def start_candidate(self):
        record = self.load()
        if not record or record["operation"] != "deploy" or record["phase"] != "paused":
            raise GuardError("candidate worker start requires the original suspension journal")
        candidate = self.env.get("API_COMPOSE_FILE", "")
        if not candidate or Path(candidate).name != candidate:
            raise GuardError("candidate worker start requires the transaction Compose basename")
        self.canonical = str(self.project / candidate)
        self.compose = ["docker", "compose", "-f", self.canonical, "--profile", "bluegreen"]
        self.require_primary()
        image = self.api_image()
        if image != self.env.get("BACKEND_IMAGE"):
            raise GuardError("candidate API image parity is not proven")
        with self.control_lock() as proof:
            if proof.get("revision") != record["revision"]:
                raise GuardError("communications control changed before candidate worker start")
            self.require_primary()
            self.release("start", image)
            self.require_worker(image)


def main():
    def interrupted(_signum, _frame):
        raise GuardInterrupted("idle worker operation interrupted; transaction recovery required")

    for signum in (signal.SIGTERM, signal.SIGINT, signal.SIGALRM):
        signal.signal(signum, interrupted)
    guard = IdleWorkerGuard()
    guard.verify_lock()
    action = sys.argv[1]
    try:
        if action == "prepare":
            guard.prepare(sys.argv[2])
        elif action in {"recover", "promoted", "complete", "start_candidate"}:
            getattr(guard, action)()
        else:
            raise GuardError("unknown idle worker guard operation")
    except BaseException:
        # Any failed operation that owns a journal remains fenced, even when a
        # concurrent process removed the marker. Never fence an unowned active
        # worker merely because its preflight was refused before capture.
        with contextlib.suppress(Exception):
            record = guard.load()
            if record:
                guard.release("fence", record["image"])
        raise


if __name__ == "__main__":
    try:
        main()
    except (GuardError, OSError, ValueError, subprocess.SubprocessError) as error:
        print(f"idle worker capacity guard failed: {error}", file=sys.stderr)
        sys.exit(1)
