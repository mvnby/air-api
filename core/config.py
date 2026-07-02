import os
from dotenv import load_dotenv
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from core.runtime_controls import (
    RuntimeControlDecision,
    resolve_single_active_control,
)

load_dotenv()


class Settings(BaseSettings):
    # Bot Settings
    BOT_TOKEN: str = ""
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
        super().__init__(**kwargs)
        # If DATABASE_URL not provided, construct it from POSTGRES_* settings
        if not self.DATABASE_URL:
            self.DATABASE_URL = f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
    
    # Static Files
    STATIC_DIR: str = "static"
    UPLOAD_DIR: str = "static/uploads"
    PUBLIC_SITE_URL: str = "https://mvn.by"

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
        extra="ignore"
    )

settings = Settings()
