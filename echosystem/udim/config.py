from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache
from typing import Optional

class Settings(BaseSettings):
    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"
    APP_NAME: str = "EchoSphere UDIM Service"
    API_V1_STR: str = "/api/v1" # Base path for V1 APIs

    S3_BUCKET_NAME: str = "your-echosphere-udim-default-data-bucket" # Example default, should be overridden by env
    KMS_KEY_ID: str = "" # Optional: Specific KMS Key ID/ARN. If empty or not set, S3 default KMS encryption for the bucket is used or AWS managed S3 key.

    # Renaming SQS_MAIPP_QUEUE_URL to SQS_MAIPP_NOTIFICATION_QUEUE_URL for clarity as per prompt
    SQS_MAIPP_NOTIFICATION_QUEUE_URL: str = "" # Must be set in .env for actual operation. Example: "http://localhost:9324/queue/maipp-data-ready-queue" or AWS SQS URL

    POSTGRES_USER: str = "udim_user"
    POSTGRES_PASSWORD: str = "udim_password"
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_PORT: str = "5432"
    POSTGRES_DB: str = "echosphere_udim"

    QLDB_LEDGER_NAME: str = "echosphere-consent-ledger"
    QLDB_AWS_REGION: str = "us-east-1" # Example default

    OAUTH_GOOGLE_CLIENT_ID: Optional[str] = None
    OAUTH_GOOGLE_CLIENT_SECRET: Optional[str] = None
    OAUTH_GOOGLE_REDIRECT_URI: str = "http://localhost:8000/api/v1/connections/oauth/google-drive/callback"

    # This setting helps pydantic find the .env file.
    # It also configures case_insensitivity for environment variables and allows extra fields (though we set extra='ignore').
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

@lru_cache()
def get_settings() -> Settings:
    return Settings()

settings = get_settings()
```
