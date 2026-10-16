"""Bound anonymous challenge creation independently from password failures."""

from services.login_throttle_service import LoginThrottleService


class TelegramLoginThrottleService(LoginThrottleService):
    # Starts include successful logins; a shared office address must not use
    # the five-failed-password budget, or poison password-login counters.
    MAX_FAILURES = 30
    SOURCE_MAX_FAILURES = 30
    GLOBAL_MAX_FAILURES = 1000
    _FINGERPRINT_DOMAIN = b"manager-telegram-challenge\x00"
    _SOURCE_FINGERPRINT_DOMAIN = b"manager-telegram-challenge-source\x00"
    _GLOBAL_FINGERPRINT_DOMAIN = b"manager-telegram-challenge-global\x00"
