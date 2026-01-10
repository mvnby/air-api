import os
from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()

class Settings(BaseSettings):
    # Bot Settings
    BOT_TOKEN: str
    ADMIN_ID: int
    SECRET_KEY: str = "super-secret-key"
    
    # Database Settings
    DATABASE_URL: str = "sqlite+aiosqlite:///./air_conditioners.db"
    
    # Static Files
    STATIC_DIR: str = "static"
    UPLOAD_DIR: str = "static/uploads"
    
    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "app.log"
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
