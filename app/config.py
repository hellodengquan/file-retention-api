from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    SECRET_KEY: str = "your-secret-key-change-in-production-2024-file-retention"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24
    DATABASE_URL: str = "sqlite:///./file_retention.db"
    SCHEDULER_INTERVAL_MINUTES: int = 60

    class Config:
        env_file = ".env"


settings = Settings()
