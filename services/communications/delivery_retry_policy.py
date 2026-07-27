import hashlib


RETRY_BASE_SECONDS = 30
RETRY_MAX_SECONDS = 3600
RETRY_JITTER_PERCENT = 20


def delivery_retry_delay_seconds(
    *,
    delivery_id: str,
    attempts: int,
) -> int:
    safe_attempts = max(1, int(attempts))
    exponential_delay = min(
        RETRY_MAX_SECONDS,
        RETRY_BASE_SECONDS * (2 ** min(safe_attempts - 1, 16)),
    )
    if exponential_delay >= RETRY_MAX_SECONDS:
        return RETRY_MAX_SECONDS
    jitter_window = max(
        1,
        (exponential_delay * RETRY_JITTER_PERCENT) // 100,
    )
    digest = hashlib.sha256(
        f"{delivery_id}:{safe_attempts}".encode("utf-8")
    ).digest()
    return min(
        RETRY_MAX_SECONDS,
        exponential_delay
        + int.from_bytes(digest[:4], "big") % (jitter_window + 1),
    )
