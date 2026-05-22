import os
from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()

class Settings(BaseSettings):
    # Bot Settings
    BOT_TOKEN: str
    ADMIN_IDS: str = ""
    ADMIN_ID: int = 0
    SECRET_KEY: str
    ENVIRONMENT: str = "local"
    
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
        if self.ADMIN_IDS:
            ids.extend([int(x.strip()) for x in self.ADMIN_IDS.split(",") if x.strip()])
        if self.ADMIN_ID and self.ADMIN_ID not in ids:
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
    
    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "logs/app.log"
    
    # Automation
    SCHEDULER_INTERVAL: int = 6 # hours

    # Monitoring
    SENTRY_DSN: str = ""

    # GitHub Actions (for Turbo Rebuilds)
    GITHUB_TOKEN: str = ""
    GITHUB_OWNER: str = "mvnby"
    GITHUB_REPO: str = "air-api"

    # Mail integration (Yandex Mail by default)
    MAIL_IMAP_HOST: str = "imap.yandex.ru"
    MAIL_IMAP_PORT: int = 993
    MAIL_IMAP_USE_SSL: bool = True
    MAIL_IMAP_USERNAME: str = ""
    MAIL_IMAP_PASSWORD: str = ""
    MAIL_IMAP_BANK_FOLDER: str = "INBOX"
    MAIL_IMAP_PROCESSED_FOLDER: str = ""
    MAIL_IMAP_AUTO_IMPORT_ENABLED: bool = True
    MAIL_IMAP_IMPORT_INTERVAL_MINUTES: int = 20
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
