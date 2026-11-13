from functools import lru_cache
from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    APP_NAME: str = "Digital Wallet API"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True
    ENVIRONMENT: str = "development"

    DATABASE_URL: str = "postgresql+asyncpg://wallet_user:wallet_pass@localhost:5432/digital_wallet"
    DATABASE_URL_SYNC: str = "postgresql://wallet_user:wallet_pass@localhost:5432/digital_wallet"

    SECRET_KEY: str = "change-this-to-a-very-long-random-secret-key-in-production-min-32-chars"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    BACKEND_CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:8000"]

    REDIS_URL: Optional[str] = "redis://localhost:6379/0"
    CELERY_BROKER_URL: Optional[str] = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: Optional[str] = "redis://localhost:6379/2"

    MAX_TRANSACTION_AMOUNT: float = 100000.00
    DAILY_TRANSFER_LIMIT: float = 50000.00
    DAILY_WITHDRAWAL_LIMIT: float = 20000.00
    MAX_TRANSACTIONS_PER_DAY: int = 50
    SUSPICIOUS_AMOUNT_THRESHOLD: float = 10000.00

    FIRST_SUPERUSER_EMAIL: str = "admin@wallet.com"
    FIRST_SUPERUSER_PASSWORD: str = "Admin@12345"
    FIRST_SUPERUSER_FULL_NAME: str = "System Administrator"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()