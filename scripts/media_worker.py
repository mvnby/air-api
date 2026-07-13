#!/usr/bin/env python3
"""Poll media processing jobs and run heavy image work on this machine.

Environment:
  MEDIA_WORKER_API_URL=http://localhost:8000
  MEDIA_WORKER_TOKEN=...
  MEDIA_WORKER_ID=my-gpu-box
  MEDIA_WORKER_CAPABILITIES=background_removal,background_removal:rembg,upscale
  MEDIA_WORKER_BACKGROUND_COMMAND='python my_ben.py --input {input} --output {output}'
"""

from __future__ import annotations

import argparse
import asyncio
import os
import shlex
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from urllib.parse import urljoin

import requests


DEFAULT_CAPABILITIES = "background_removal,background_removal:rembg"


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _int_env(name: str, default: int) -> int:
    raw = _env(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _capabilities(raw_value: str) -> list[str]:
    return [item.strip() for item in raw_value.split(",") if item.strip()]


def _source_download_url(api_url: str, source_url: str) -> str:
    if source_url.startswith(("http://", "https://")):
        return source_url
    return urljoin(api_url.rstrip("/") + "/", source_url.lstrip("/"))


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _claim_job(api_url: str, token: str, worker_id: str, capabilities: list[str], lease_seconds: int):
    response = requests.post(
        f"{api_url.rstrip('/')}/api/manager/media/worker/jobs/claim",
        headers=_headers(token),
        json={
            "worker_id": worker_id,
            "capabilities": capabilities,
            "lease_seconds": lease_seconds,
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json().get("job")


def _download_source(api_url: str, job: dict, token: str, path: Path) -> None:
    source_url = job.get("source_url")
    if not source_url:
        raise RuntimeError("Claimed job does not include source_url")
    download_url = _source_download_url(api_url, source_url)
    headers = _headers(token) if download_url.startswith(api_url.rstrip("/")) else {}
    with requests.get(download_url, headers=headers, stream=True, timeout=120) as response:
        response.raise_for_status()
        with path.open("wb") as output:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    output.write(chunk)


def _renew_job(
    api_url: str,
    token: str,
    job_id: str,
    worker_id: str,
    lease_token: str,
    lease_seconds: int,
) -> None:
    response = requests.post(
        f"{api_url.rstrip('/')}/api/manager/media/worker/jobs/{job_id}/renew",
        headers=_headers(token),
        json={
            "worker_id": worker_id,
            "lease_token": lease_token,
            "lease_seconds": lease_seconds,
        },
        timeout=30,
    )
    response.raise_for_status()


def _lease_heartbeat(
    *,
    stop_event: threading.Event,
    api_url: str,
    token: str,
    job_id: str,
    worker_id: str,
    lease_token: str,
    lease_seconds: int,
) -> None:
    interval = max(10.0, min(60.0, lease_seconds / 3))
    while not stop_event.wait(interval):
        try:
            _renew_job(
                api_url,
                token,
                job_id,
                worker_id,
                lease_token,
                lease_seconds,
            )
        except Exception as exc:
            print(
                f"Media job {job_id} lease heartbeat failed: {type(exc).__name__}",
                file=sys.stderr,
                flush=True,
            )


def _start_lease_heartbeat(
    *,
    api_url: str,
    token: str,
    job_id: str,
    worker_id: str,
    lease_token: str,
    lease_seconds: int,
) -> tuple[threading.Event, threading.Thread]:
    stop_event = threading.Event()
    thread = threading.Thread(
        target=_lease_heartbeat,
        kwargs={
            "stop_event": stop_event,
            "api_url": api_url,
            "token": token,
            "job_id": job_id,
            "worker_id": worker_id,
            "lease_token": lease_token,
            "lease_seconds": lease_seconds,
        },
        name=f"media-lease-{job_id[:12]}",
        daemon=True,
    )
    thread.start()
    return stop_event, thread


def _complete_job(
    api_url: str,
    token: str,
    job_id: str,
    worker_id: str,
    lease_token: str,
    output_path: Path,
):
    with output_path.open("rb") as file_obj:
        response = requests.post(
            f"{api_url.rstrip('/')}/api/manager/media/worker/jobs/{job_id}/complete",
            headers=_headers(token),
            data={"worker_id": worker_id, "lease_token": lease_token},
            files={"file": (output_path.name, file_obj, "image/png")},
            timeout=180,
        )
    response.raise_for_status()
    return response.json()


def _fail_job(
    api_url: str,
    token: str,
    job_id: str,
    worker_id: str,
    lease_token: str,
    error: str,
) -> None:
    response = requests.post(
        f"{api_url.rstrip('/')}/api/manager/media/worker/jobs/{job_id}/fail",
        headers=_headers(token),
        json={"worker_id": worker_id, "lease_token": lease_token, "error": error[:2000]},
        timeout=30,
    )
    response.raise_for_status()


def _run_external_command(template: str, *, job: dict, input_path: Path, output_path: Path) -> None:
    if "{input}" not in template or "{output}" not in template:
        raise RuntimeError("Media worker command must contain {input} and {output}")
    try:
        command = [
            part.format(
                input=str(input_path),
                output=str(output_path),
                operation=str(job.get("operation") or ""),
                provider=str(job.get("provider") or ""),
                rembg_model=str(job.get("rembg_model") or ""),
                job_id=str(job.get("job_id") or ""),
            )
            for part in shlex.split(template, posix=os.name != "nt")
        ]
    except (KeyError, ValueError) as exc:
        raise RuntimeError("Media worker command template is invalid") from exc
    if not command or not command[0].strip():
        raise RuntimeError("Media worker command is empty")

    completed = _run_command_with_timeout(
        command,
        timeout=max(1, _int_env("MEDIA_WORKER_COMMAND_TIMEOUT_SECONDS", 1800)),
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        raise RuntimeError(f"External processor failed ({completed.returncode}): {detail}")
    if not output_path.exists() or output_path.stat().st_size == 0:
        raise RuntimeError("External processor did not create output file")


def _run_command_with_timeout(
    command: list[str],
    *,
    timeout: int,
) -> subprocess.CompletedProcess[str]:
    popen_kwargs = {
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "text": True,
    }
    if os.name == "nt":
        popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        popen_kwargs["start_new_session"] = True

    process = subprocess.Popen(command, **popen_kwargs)
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        if os.name == "nt":
            process.kill()
        else:
            os.killpg(process.pid, signal.SIGKILL)
        stdout, stderr = process.communicate()
        raise RuntimeError(f"External processor timed out after {timeout}s") from exc

    return subprocess.CompletedProcess(
        command,
        process.returncode,
        stdout=stdout,
        stderr=stderr,
    )


async def _run_builtin_background_removal(job: dict, input_path: Path, output_path: Path) -> None:
    from services.product_image_processing_contract import ProductImageVariantType
    from services.product_image_processing_provider import (
        ProductImageProcessingContext,
        get_product_image_processor,
    )

    provider = job.get("provider") or "rembg"
    processor = get_product_image_processor(provider, rembg_model=job.get("rembg_model"))
    processed = await processor.process(
        source_content=input_path.read_bytes(),
        context=ProductImageProcessingContext(
            product_image_id=0,
            source_url=job.get("source_url") or "",
            variant_type=ProductImageVariantType.PROCESSED.value,
        ),
    )
    output_path.write_bytes(processed.content)


def _process_job(job: dict, input_path: Path, output_path: Path) -> None:
    operation = job.get("operation") or "background_removal"
    command_env = {
        "background_removal": "MEDIA_WORKER_BACKGROUND_COMMAND",
        "upscale": "MEDIA_WORKER_UPSCALE_COMMAND",
    }.get(operation)
    command = _env(command_env or "") if command_env else ""
    if command:
        _run_external_command(command, job=job, input_path=input_path, output_path=output_path)
        return
    if operation == "background_removal":
        asyncio.run(_run_builtin_background_removal(job, input_path, output_path))
        return
    raise RuntimeError(f"No default processor configured for operation: {operation}")


def _run_once(api_url: str, token: str, worker_id: str, capabilities: list[str], lease_seconds: int) -> bool:
    job = _claim_job(api_url, token, worker_id, capabilities, lease_seconds)
    if not job:
        return False

    job_id = job["job_id"]
    lease_token = str(job.get("lease_token") or "")
    if not lease_token:
        raise RuntimeError(
            "Claimed job does not include lease_token; deploy the API and worker script together"
        )
    print(f"Claimed media job {job_id}: {job.get('operation')} {job.get('provider') or ''}", flush=True)
    stop_event, heartbeat_thread = _start_lease_heartbeat(
        api_url=api_url,
        token=token,
        job_id=job_id,
        worker_id=worker_id,
        lease_token=lease_token,
        lease_seconds=lease_seconds,
    )
    try:
        with tempfile.TemporaryDirectory(prefix="media-worker-") as tmp_dir:
            input_path = Path(tmp_dir) / "input"
            output_path = Path(tmp_dir) / "output.png"
            _download_source(api_url, job, token, input_path)
            _process_job(job, input_path, output_path)
            result = _complete_job(api_url, token, job_id, worker_id, lease_token, output_path)
            stop_event.set()
            heartbeat_thread.join(timeout=5)
            print(
                f"Completed media job {job_id}: asset #{result.get('result_asset_id')}",
                flush=True,
            )
    except Exception as exc:
        stop_event.set()
        heartbeat_thread.join(timeout=5)
        try:
            _fail_job(api_url, token, job_id, worker_id, lease_token, str(exc))
        except Exception as fail_exc:
            print(
                f"Could not mark media job {job_id} failed: {type(fail_exc).__name__}",
                file=sys.stderr,
                flush=True,
            )
        print(f"Failed media job {job_id}: {exc}", file=sys.stderr, flush=True)
    return True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", default=_env("MEDIA_WORKER_API_URL", "http://localhost:8000"))
    parser.add_argument("--token", default=_env("MEDIA_WORKER_TOKEN"))
    parser.add_argument("--worker-id", default=_env("MEDIA_WORKER_ID", socket.gethostname()))
    parser.add_argument("--capabilities", default=_env("MEDIA_WORKER_CAPABILITIES", DEFAULT_CAPABILITIES))
    parser.add_argument("--lease-seconds", type=int, default=_int_env("MEDIA_WORKER_LEASE_SECONDS", 900))
    parser.add_argument("--poll-interval", type=float, default=float(_env("MEDIA_WORKER_POLL_INTERVAL", "5")))
    parser.add_argument("--once", action="store_true", default=_env("MEDIA_WORKER_ONCE") == "1")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.token:
        print("MEDIA_WORKER_TOKEN is required", file=sys.stderr)
        return 2
    capabilities = _capabilities(args.capabilities)
    print(
        f"Media worker {args.worker_id} polling {args.api_url} with {', '.join(capabilities) or 'all'}",
        flush=True,
    )
    while True:
        try:
            claimed = _run_once(args.api_url, args.token, args.worker_id, capabilities, args.lease_seconds)
        except requests.HTTPError as exc:
            print(f"Worker API error: {exc}", file=sys.stderr, flush=True)
            claimed = False
        if args.once:
            return 0
        if not claimed:
            time.sleep(max(1.0, args.poll_interval))


if __name__ == "__main__":
    raise SystemExit(main())
