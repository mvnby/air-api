from __future__ import annotations

import re


CANARY_RUN_ID_PATTERN = (
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-"
    r"[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
_CANARY_RUN_ID_RE = re.compile(CANARY_RUN_ID_PATTERN)


def normalize_canary_run_id(value: str) -> str:
    run_id = value if isinstance(value, str) else ""
    if not _CANARY_RUN_ID_RE.fullmatch(run_id):
        raise ValueError("Canary run_id must be a canonical lowercase UUIDv4")
    return run_id


def short_canary_run_id(value: str) -> str:
    return normalize_canary_run_id(value).split("-", maxsplit=1)[0]
