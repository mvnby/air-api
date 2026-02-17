import sentry_sdk

from core.config import settings


def init_sentry() -> None:
    if settings.SENTRY_DSN:
        sentry_sdk.init(
            dsn=settings.SENTRY_DSN,
            traces_sample_rate=1.0,
            profiles_sample_rate=1.0,
            environment=settings.ENVIRONMENT,
        )
