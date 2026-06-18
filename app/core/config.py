from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = Path(__file__).resolve().parent.parent.parent / ".env"


class Settings(BaseSettings):
    APP_ENV: str = "dev"

    DEV_DATABASE_URL: str | None = None
    DEV_REDIS_URL: str | None = None

    TEST_DATABASE_URL: str | None = None
    TEST_REDIS_URL: str | None = None

    PROD_DATABASE_URL: str | None = None
    PROD_REDIS_URL: str | None = None

    SECRET_KEY: str = Field(default="dev-only-change-me")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    JWT_ALGORITHM: str = "HS256"

    INTELLIGENCE_BASE_URL: str | None = None
    INTELLIGENCE_TIMEOUT_SECONDS: float = 5.0

    S3_ENDPOINT_URL: str | None = None
    S3_ACCESS_KEY_ID: str | None = None
    S3_SECRET_ACCESS_KEY: str | None = None
    S3_BUCKET_NAME: str = "jetpass"
    S3_REGION: str = "us-east-1"

    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def DATABASE_URL(self) -> str | None:
        if self.APP_ENV == "prod":
            return self.PROD_DATABASE_URL
        if self.APP_ENV == "test":
            return self.TEST_DATABASE_URL
        return self.DEV_DATABASE_URL

    @property
    def REDIS_URL(self) -> str | None:
        if self.APP_ENV == "prod":
            return self.PROD_REDIS_URL
        if self.APP_ENV == "test":
            return self.TEST_REDIS_URL
        return self.DEV_REDIS_URL

    @property
    def s3_configured(self) -> bool:
        return bool(self.S3_ENDPOINT_URL and self.S3_ACCESS_KEY_ID and self.S3_SECRET_ACCESS_KEY)


settings = Settings()
