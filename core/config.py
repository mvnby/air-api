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
    
    @property
    def admin_list(self) -> list[int]:
        ids = []
        if self.ADMIN_IDS:
            ids.extend([int(x.strip()) for x in self.ADMIN_IDS.split(",") if x.strip()])
        if self.ADMIN_ID and self.ADMIN_ID not in ids:
            ids.append(int(self.ADMIN_ID))
        return ids
    
    # Database Settings
    DATABASE_URL: str = "sqlite+aiosqlite:///./air_conditioners.db"
    
    # Static Files
    STATIC_DIR: str = "static"
    UPLOAD_DIR: str = "static/uploads"
    
    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "logs/app.log"
    
    # Automation
    SCHEDULER_INTERVAL: int = 6 # hours
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
