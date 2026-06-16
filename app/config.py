from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    SECRET_KEY: str = "your-secret-key-change-in-production-2024-file-retention"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24
    DATABASE_URL: str = "sqlite:///./file_retention.db"
    SCHEDULER_INTERVAL_MINUTES: int = 60

    ARCHIVE_RESTORE_WINDOW_DAYS: int = 30

    SCHEDULER_MAX_RETRY_ATTEMPTS: int = 5
    SCHEDULER_RETRY_MIN_WAIT_SECONDS: int = 5
    SCHEDULER_RETRY_MAX_WAIT_SECONDS: int = 120

    RATE_LIMIT_WHITELIST_IPS: List[str] = []
    RATE_LIMIT_WHITELIST_USERS: List[str] = ["admin"]

    class Config:
        env_file = ".env"


settings = Settings()
