import re
from urllib.parse import urlsplit

from dotenv import load_dotenv
from pydantic import ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from core.runtime_controls import (
    RuntimeControlDecision,
    resolve_single_active_control,
)

load_dotenv()


_STOREFRONT_SIGNING_KEY_ID_PATTERN = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$"
)


def _redact_settings_validation_error(error: ValidationError) -> ValidationError:
    line_errors = error.errors(include_url=False)
    for line_error in line_errors:
        line_error["input"] = "[redacted]"
    return ValidationError.from_exception_data(
        error.title,
        line_errors,
        hide_input=True,
    )


class Settings(BaseSettings):
    # Bot Settings
    BOT_TOKEN: str = ""
    BOT_ACCESS_BACKEND: str = "database"
    BOT_API_TOKEN: str = ""
    BOT_API_BASE_URL: str = "http://app:8000/api/internal/bot/v1"
    BOT_API_TIMEOUT_SECONDS: float = 5.0
    MANAGER_BASE_URL: str = "https://api.mvn.by/manager"
    BOT_TASK_TIMEZONE: str = "Europe/Minsk"
    BOT_VOICE_TRANSCRIPTION_ENABLED: bool = False
    BOT_VOICE_TRANSCRIPTION_API_URL: str = (
        "https://api.groq.com/openai/v1/audio/transcriptions"
    )
    BOT_VOICE_TRANSCRIPTION_API_KEY: str = ""
    BOT_VOICE_TRANSCRIPTION_MODEL: str = "whisper-large-v3-turbo"
    BOT_VOICE_TRANSCRIPTION_TIMEOUT_SECONDS: float = 30.0
    ADMIN_IDS: str = ""
    ADMIN_ID: int = 0
    SECRET_KEY: str
    ENVIRONMENT: str = "local"
    APP_ROLE: str = "primary"
    
    # CORS Settings
    @property
    def CORS_ORIGINS(self) -> list[str]:
        if self.ENVIRONMENT == "production":
            return [
                "https://mvn.by",
                "https://dev.mvn.by",
            ]
        return [
            "https://mvn.by",
            "https://dev.mvn.by",
            "http://localhost:4321",
            "http://localhost:3000",
        ]
    
    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"
    
    # HTTP Basic Auth
    ADMIN_USERNAME: str
    ADMIN_PASSWORD: str
    
    @property
    def admin_list(self) -> list[int]:
        ids = []
        seen = set()
        if self.ADMIN_IDS:
            for raw_id in self.ADMIN_IDS.split(","):
                value = raw_id.strip()
                if not value:
                    continue
                admin_id = int(value)
                if admin_id in seen:
                    continue
                seen.add(admin_id)
                ids.append(admin_id)
        if self.ADMIN_ID and int(self.ADMIN_ID) not in seen:
            ids.append(int(self.ADMIN_ID))
        return ids

    def is_admin_user(self, user_id: int | None) -> bool:
        return user_id is not None and int(user_id) in self.admin_list
    
    # Database Settings
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "air_conditioners"
    
    # DATABASE_URL can be set directly or will be constructed from POSTGRES_* vars
    DATABASE_URL: str = ""
    
    def __init__(self, **kwargs):
        redacted_error: ValidationError | None = None
        try:
            super().__init__(**kwargs)
        except ValidationError as error:
            redacted_error = _redact_settings_validation_error(error)
        if redacted_error is not None:
            raise redacted_error from None
        # If DATABASE_URL not provided, construct it from POSTGRES_* settings
        if not self.DATABASE_URL:
            self.DATABASE_URL = f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
    
    # Static Files
    STATIC_DIR: str = "static"
    UPLOAD_DIR: str = "static/uploads"
    PUBLIC_SITE_URL: str = "https://mvn.by"
    # Optional runtime keyring for a trusted storefront SSR/proxy. When unset,
    # public requests keep using the canonical MVN storefront; a request that
    # tries to select another storefront still fails closed.
    STOREFRONT_CONTEXT_SIGNING_KEY_ID: str = ""
    STOREFRONT_CONTEXT_SIGNING_SECRET: str = ""
    STOREFRONT_CONTEXT_PREVIOUS_SIGNING_KEY_ID: str = ""
    STOREFRONT_CONTEXT_PREVIOUS_SIGNING_SECRET: str = ""
    STOREFRONT_CONTEXT_MAX_AGE_SECONDS: int = 300
    STOREFRONT_CONTEXT_MAX_BODY_BYTES: int = 20 * 1024 * 1024
    STOREFRONT_CONTEXT_REQUIRE_SIGNED_REQUESTS: bool = False
    # Comma-separated upstream API host allowlist. Blank keeps the safe
    # environment-specific defaults used by production and local smoke tests.
    STOREFRONT_CONTEXT_API_HOSTS: str = ""

    @property
    def storefront_context_api_hosts(self) -> tuple[str, ...]:
        configured = tuple(
            item.strip()
            for item in self.STOREFRONT_CONTEXT_API_HOSTS.split(",")
            if item.strip()
        )
        if configured:
            return configured
        if self.ENVIRONMENT == "production":
            return ("api.mvn.by", "localhost", "127.0.0.1")
        return (
            "api.mvn.by",
            "localhost",
            "127.0.0.1",
            "testserver",
            "test",
            "app",
        )

    @field_validator(
        "STOREFRONT_CONTEXT_SIGNING_KEY_ID",
        "STOREFRONT_CONTEXT_PREVIOUS_SIGNING_KEY_ID",
    )
    @classmethod
    def _validate_storefront_context_key_id(cls, value: str) -> str:
        normalized = str(value or "").strip()
        if normalized and not _STOREFRONT_SIGNING_KEY_ID_PATTERN.fullmatch(
            normalized
        ):
            raise ValueError(
                "Storefront context signing key ID must use 1-64 ASCII letters, digits, dot, underscore or dash"
            )
        return normalized

    @field_validator(
        "STOREFRONT_CONTEXT_SIGNING_SECRET",
        "STOREFRONT_CONTEXT_PREVIOUS_SIGNING_SECRET",
    )
    @classmethod
    def _validate_storefront_context_secret(cls, value: str) -> str:
        normalized = str(value or "")
        if normalized and len(normalized.encode("utf-8")) < 32:
            raise ValueError(
                "STOREFRONT_CONTEXT_SIGNING_SECRET must contain at least 32 bytes"
            )
        return normalized

    @field_validator("STOREFRONT_CONTEXT_MAX_AGE_SECONDS")
    @classmethod
    def _validate_storefront_context_max_age(cls, value: int) -> int:
        normalized = int(value)
        if normalized < 30 or normalized > 900:
            raise ValueError(
                "STOREFRONT_CONTEXT_MAX_AGE_SECONDS must be between 30 and 900"
            )
        return normalized

    @field_validator("STOREFRONT_CONTEXT_MAX_BODY_BYTES")
    @classmethod
    def _validate_storefront_context_max_body_bytes(cls, value: int) -> int:
        normalized = int(value)
        if normalized < 1024 or normalized > 64 * 1024 * 1024:
            raise ValueError(
                "STOREFRONT_CONTEXT_MAX_BODY_BYTES must be between 1 KiB and 64 MiB"
            )
        return normalized

    @model_validator(mode="after")
    def _validate_storefront_context_keyring(self):
        primary_id = bool(self.STOREFRONT_CONTEXT_SIGNING_KEY_ID)
        primary_secret = bool(self.STOREFRONT_CONTEXT_SIGNING_SECRET)
        previous_id = bool(self.STOREFRONT_CONTEXT_PREVIOUS_SIGNING_KEY_ID)
        previous_secret = bool(self.STOREFRONT_CONTEXT_PREVIOUS_SIGNING_SECRET)

        if primary_id != primary_secret:
            raise ValueError(
                "STOREFRONT_CONTEXT_SIGNING_KEY_ID and STOREFRONT_CONTEXT_SIGNING_SECRET must be configured together"
            )
        if previous_id != previous_secret:
            raise ValueError(
                "STOREFRONT_CONTEXT_PREVIOUS_SIGNING_KEY_ID and "
                "STOREFRONT_CONTEXT_PREVIOUS_SIGNING_SECRET must be configured together"
            )
        if previous_id and not primary_id:
            raise ValueError(
                "Previous storefront signing key requires a configured primary key"
            )
        if (
            previous_id
            and self.STOREFRONT_CONTEXT_PREVIOUS_SIGNING_KEY_ID
            == self.STOREFRONT_CONTEXT_SIGNING_KEY_ID
        ):
            raise ValueError(
                "Primary and previous storefront signing key IDs must differ"
            )
        if self.STOREFRONT_CONTEXT_REQUIRE_SIGNED_REQUESTS and not primary_id:
            raise ValueError(
                "Signed storefront requests cannot be required without a primary signing key"
            )
        return self

    # Product media storage. Default stays local so CI/deploy do not require
    # R2/S3 secrets unless PRODUCT_MEDIA_STORAGE_PROVIDER is changed.
    PRODUCT_MEDIA_STORAGE_PROVIDER: str = "local"
    PRODUCT_MEDIA_LOCAL_VARIANT_DIR: str = "media/products/variants"
    PRODUCT_MEDIA_LOCAL_VARIANT_PUBLIC_PREFIX: str = "/media/products/variants"
    PRODUCT_MEDIA_S3_BUCKET: str = ""
    PRODUCT_MEDIA_S3_ENDPOINT_URL: str = ""
    PRODUCT_MEDIA_S3_REGION: str = "auto"
    PRODUCT_MEDIA_S3_ACCESS_KEY_ID: str = ""
    PRODUCT_MEDIA_S3_SECRET_ACCESS_KEY: str = ""
    PRODUCT_MEDIA_S3_PUBLIC_BASE_URL: str = ""
    PRODUCT_MEDIA_S3_KEY_PREFIX: str = "products/variants"
    PRODUCT_MEDIA_S3_CACHE_CONTROL: str = "public, max-age=31536000, immutable"

    # Generic media storage for articles, media library, order attachments and
    # other non-product files. S3/R2 settings fall back to PRODUCT_MEDIA_S3_*
    # inside the storage adapter when these values are left empty.
    MEDIA_STORAGE_PROVIDER: str = "local"
    MEDIA_LOCAL_DIR: str = "media"
    MEDIA_LOCAL_PUBLIC_PREFIX: str = "/media"
    MEDIA_S3_BUCKET: str = ""
    MEDIA_S3_ENDPOINT_URL: str = ""
    MEDIA_S3_REGION: str = "auto"
    MEDIA_S3_ACCESS_KEY_ID: str = ""
    MEDIA_S3_SECRET_ACCESS_KEY: str = ""
    MEDIA_S3_PUBLIC_BASE_URL: str = ""
    MEDIA_S3_KEY_PREFIX: str = ""
    MEDIA_S3_CACHE_CONTROL: str = "public, max-age=31536000, immutable"

    # Customer, installation and warranty evidence is private. In production
    # use a dedicated non-public bucket; never expose a public base URL.
    SERVICE_ATTACHMENT_STORAGE_PROVIDER: str = "local"
    SERVICE_ATTACHMENT_LOCAL_DIR: str = "private_media/service-attachments"
    SERVICE_ATTACHMENT_S3_BUCKET: str = ""
    SERVICE_ATTACHMENT_S3_ENDPOINT_URL: str = ""
    SERVICE_ATTACHMENT_S3_REGION: str = "auto"
    SERVICE_ATTACHMENT_S3_ACCESS_KEY_ID: str = ""
    SERVICE_ATTACHMENT_S3_SECRET_ACCESS_KEY: str = ""
    SERVICE_ATTACHMENT_S3_KEY_PREFIX: str = "service-attachments"
    SERVICE_ATTACHMENT_ACCESS_TTL_SECONDS: int = 300
    SERVICE_ATTACHMENT_MAX_SIZE_BYTES: int = 25 * 1024 * 1024

    @model_validator(mode="after")
    def _validate_private_attachment_storage(self):
        if not self.is_production:
            return self
        provider = str(self.SERVICE_ATTACHMENT_STORAGE_PROVIDER or "").strip().lower()
        if provider != "r2":
            raise ValueError(
                "Production service attachments require SERVICE_ATTACHMENT_STORAGE_PROVIDER=r2 "
                "and a dedicated private bucket"
            )
        required = {
            "SERVICE_ATTACHMENT_S3_BUCKET": self.SERVICE_ATTACHMENT_S3_BUCKET,
            "SERVICE_ATTACHMENT_S3_ENDPOINT_URL": self.SERVICE_ATTACHMENT_S3_ENDPOINT_URL,
            "SERVICE_ATTACHMENT_S3_ACCESS_KEY_ID": self.SERVICE_ATTACHMENT_S3_ACCESS_KEY_ID,
            "SERVICE_ATTACHMENT_S3_SECRET_ACCESS_KEY": self.SERVICE_ATTACHMENT_S3_SECRET_ACCESS_KEY,
        }
        missing = [name for name, value in required.items() if not str(value or "").strip()]
        if missing:
            raise ValueError("Production private attachment storage is missing: " + ", ".join(missing))

        endpoint = self.SERVICE_ATTACHMENT_S3_ENDPOINT_URL.strip()
        try:
            parsed_endpoint = urlsplit(endpoint)
            parsed_endpoint.port
        except ValueError:
            parsed_endpoint = None
        if (
            parsed_endpoint is None
            or parsed_endpoint.scheme.lower() != "https"
            or not parsed_endpoint.hostname
            or parsed_endpoint.username is not None
            or parsed_endpoint.password is not None
            or parsed_endpoint.query
            or parsed_endpoint.fragment
            or any(char.isspace() for char in endpoint)
        ):
            raise ValueError(
                "Production private attachment storage endpoint must be a credential-free HTTPS URL"
            )

        private_bucket = self.SERVICE_ATTACHMENT_S3_BUCKET.strip().casefold()
        shared_bucket_settings = [
            name
            for name, value in (
                ("MEDIA_S3_BUCKET", self.MEDIA_S3_BUCKET),
                ("PRODUCT_MEDIA_S3_BUCKET", self.PRODUCT_MEDIA_S3_BUCKET),
            )
            if str(value or "").strip().casefold() == private_bucket
        ]
        if shared_bucket_settings:
            raise ValueError(
                "Production private attachment bucket must differ from: "
                + ", ".join(shared_bucket_settings)
            )
        return self

    PRODUCT_MEDIA_ORIGINAL_SOURCE_PROVIDER: str = "local"
    PRODUCT_MEDIA_LOCAL_ORIGINAL_DIR: str = "media/products/shared"
    PRODUCT_MEDIA_LOCAL_ORIGINAL_PUBLIC_PREFIX: str = "/media/products/shared"
    PRODUCT_MEDIA_ORIGINAL_S3_KEY_PREFIX: str = "products/shared"
    MEDIA_WORKER_TOKEN: str = ""
    
    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "logs/app.log"
    
    # Automation
    SCHEDULER_INTERVAL: int = 6 # hours
    SCHEDULER_ENABLED: bool | None = None
    BOT_ENABLED: bool | None = None
    BOT_DROP_PENDING_UPDATES: bool = False
    API_READY_ENABLED: bool | None = None
    DB_BOOTSTRAP_ENABLED: bool | None = None
    READINESS_REQUIRE_WRITABLE_DB: bool = True
    RUNTIME_DB_LOCKS_ENABLED: bool = True
    RUNTIME_LOCK_RETRY_SECONDS: int = 15

    @field_validator("BOT_ACCESS_BACKEND", mode="before")
    @classmethod
    def _validate_bot_access_backend(cls, value: object) -> str:
        normalized = str(value or "").strip().lower()
        if normalized not in {"database", "api"}:
            raise ValueError("BOT_ACCESS_BACKEND must be database or api")
        return normalized

    @model_validator(mode="after")
    def _validate_bot_api_runtime(self):
        if self.BOT_ACCESS_BACKEND != "api":
            return self
        if not self.BOT_API_TOKEN.strip():
            raise ValueError("BOT_API_TOKEN is required when BOT_ACCESS_BACKEND=api")

        parsed = urlsplit(self.BOT_API_BASE_URL.strip())
        if self.ENVIRONMENT == "production":
            if parsed.scheme != "https":
                raise ValueError("production Bot API access requires an HTTPS base URL")
            if parsed.hostname in {"app", "app-blue", "app-green"}:
                raise ValueError("production Bot API access requires a stable host across blue-green slots")
        return self

    # Durable communications runtime. The process is deliberately inert unless
    # this immutable deployment gate is explicitly enabled. A second, database-
    # backed off/canary/all control is evaluated by the runtime after it proves
    # primary ownership.
    COMMUNICATIONS_WORKER_ENABLED: bool = False
    # Full website-event delivery requires a second immutable rollout key.
    # Canary mode remains available while this is false.
    COMMUNICATIONS_WORKER_ALLOW_ALL_MODE: bool = False
    COMMUNICATIONS_WORKER_POLL_SECONDS: float = 1.0
    COMMUNICATIONS_WORKER_HEARTBEAT_SECONDS: float = 10.0
    COMMUNICATIONS_WORKER_LOCK_RETRY_SECONDS: float = 2.0
    COMMUNICATIONS_WORKER_LOCK_CHECK_SECONDS: float = 3.0
    COMMUNICATIONS_WORKER_DB_PROBE_TIMEOUT_SECONDS: float = 5.0
    COMMUNICATIONS_WORKER_FENCING_SECONDS: float = 60.0
    COMMUNICATIONS_WORKER_SHUTDOWN_SECONDS: float = 15.0
    COMMUNICATIONS_WORKER_PROVIDER_TIMEOUT_SECONDS: float = 10.0
    COMMUNICATIONS_WORKER_PROVIDER_CLOSE_SECONDS: float = 5.0
    COMMUNICATIONS_WORKER_LEASE_SECONDS: int = 90

    @field_validator(
        "SCHEDULER_ENABLED",
        "BOT_ENABLED",
        "API_READY_ENABLED",
        "DB_BOOTSTRAP_ENABLED",
        mode="before",
    )
    @classmethod
    def _blank_runtime_switch_is_unset(cls, value: object) -> object | None:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @property
    def scheduler_control_decision(self) -> RuntimeControlDecision:
        return resolve_single_active_control(
            app_role=self.APP_ROLE,
            explicit_enabled=self.SCHEDULER_ENABLED,
            env_var_name="SCHEDULER_ENABLED",
            process_label="scheduler loops",
        )

    @property
    def bot_control_decision(self) -> RuntimeControlDecision:
        return resolve_single_active_control(
            app_role=self.APP_ROLE,
            explicit_enabled=self.BOT_ENABLED,
            env_var_name="BOT_ENABLED",
            process_label="Telegram bot polling",
        )

    @property
    def api_ready_control_decision(self) -> RuntimeControlDecision:
        return resolve_single_active_control(
            app_role=self.APP_ROLE,
            explicit_enabled=self.API_READY_ENABLED,
            env_var_name="API_READY_ENABLED",
            process_label="public API traffic",
        )

    @property
    def db_bootstrap_control_decision(self) -> RuntimeControlDecision:
        return resolve_single_active_control(
            app_role=self.APP_ROLE,
            explicit_enabled=self.DB_BOOTSTRAP_ENABLED,
            env_var_name="DB_BOOTSTRAP_ENABLED",
            process_label="database bootstrap",
        )

    # Monitoring
    SENTRY_DSN: str = ""
    SENTRY_TRACES_SAMPLE_RATE: float = 0.1
    SENTRY_PROFILES_SAMPLE_RATE: float = 0.0

    @field_validator("SENTRY_TRACES_SAMPLE_RATE", "SENTRY_PROFILES_SAMPLE_RATE")
    @classmethod
    def _validate_sentry_sample_rate(cls, value: float) -> float:
        normalized = float(value)
        if normalized < 0 or normalized > 1:
            raise ValueError("Sentry sample rates must be between 0 and 1")
        return normalized

    # AI integrations
    DEEPSEEK_TOKEN: str = ""
    DEEPSEEK_MODEL: str = "deepseek-v4-flash"
    DEEPSEEK_API_URL: str = "https://api.deepseek.com/chat/completions"
    GOOGLE_VISION_CREDENTIALS_FILE: str = ""
    GOOGLE_VISION_PROJECT_ID: str = ""

    # GitHub Actions (for Turbo Rebuilds)
    GITHUB_TOKEN: str = ""
    GITHUB_OWNER: str = "mvnby"
    GITHUB_REPO: str = "air-api"
    WEB_REBUILD_GITHUB_OWNER: str = "mvnby"
    WEB_REBUILD_GITHUB_REPO: str = "mvn-web"
    WEB_REBUILD_GITHUB_REF: str = "main"
    WEB_REBUILD_CALLBACK_TOKEN: str = ""

    # Destructive restore is intentionally disabled by default. Enabling this
    # switch is only one part of the restore runbook: traffic must also be
    # drained and a single active control-plane process must be guaranteed.
    BACKUP_RESTORE_ENABLED: bool = False

    # Mail integration (Yandex Mail by default)
    MAIL_IMAP_HOST: str = "imap.yandex.ru"
    MAIL_IMAP_PORT: int = 993
    MAIL_IMAP_TIMEOUT_SECONDS: int = 12
    MAIL_IMAP_USE_SSL: bool = True
    MAIL_IMAP_USERNAME: str = ""
    MAIL_IMAP_PASSWORD: str = ""
    MAIL_IMAP_BANK_FOLDER: str = "INBOX"
    MAIL_IMAP_PROCESSED_FOLDER: str = ""
    MAIL_IMAP_AUTO_IMPORT_ENABLED: bool = True
    MAIL_IMAP_IMPORT_INTERVAL_MINUTES: int = 20
    MAIL_IMAP_LEAD_FOLDER: str = "INBOX"
    MAIL_IMAP_LEAD_PROCESSED_FOLDER: str = ""
    MAIL_IMAP_LEAD_AUTO_IMPORT_ENABLED: bool = False
    MAIL_IMAP_LEAD_IMPORT_INTERVAL_MINUTES: int = 20
    MAIL_IMAP_LEAD_INITIAL_LOOKBACK_DAYS: int = 5
    MAIL_IMAP_LEAD_KEYWORDS: str = ""
    MAIL_SMTP_HOST: str = "smtp.yandex.ru"
    MAIL_SMTP_PORT: int = 465
    MAIL_SMTP_USE_SSL: bool = True
    MAIL_SMTP_USERNAME: str = ""
    MAIL_SMTP_PASSWORD: str = ""
    MAIL_FROM_EMAIL: str = ""
    MAIL_FROM_NAME: str = "Мастер Воздуха"
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )


settings = Settings()
