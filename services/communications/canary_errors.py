from __future__ import annotations


class CommunicationsCanarySafetyError(RuntimeError):
    """Fail-closed canary guard with a safe, machine-readable error code."""

    def __init__(self, error_code: str) -> None:
        self.error_code = str(error_code).strip()[:100] or "canary_safety_check_failed"
        super().__init__(self.error_code)
