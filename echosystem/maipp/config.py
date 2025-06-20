from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache
from typing import Optional
import logging # For logger in get_settings

logger = logging.getLogger(__name__) # For use within get_settings validation

class Settings(BaseSettings):
    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"
    APP_NAME: str = "EchoSphere MAIPP Service"
    API_V1_STR: str = "/api/v1/maipp" # If MAIPP exposes any APIs itself

    # --- Secrets for AI APIs (Loaded from .env or environment variables) ---
    OPENAI_API_KEY: Optional[str] = None
    GOOGLE_GEMINI_API_KEY: Optional[str] = None
    ANTHROPIC_API_KEY: Optional[str] = None
    HUGGINGFACE_HUB_TOKEN: Optional[str] = None

    # --- Database Connection Strings ---
    POSTGRES_DSN_UDIM_METADATA: Optional[str] = "postgresql+asyncpg://udim_meta_user:udim_meta_pass@localhost:5432/udim_metadata_db"
    MONGO_DB_URL: Optional[str] = "mongodb://localhost:27017/maipp_raw_features"
    POSTGRES_DSN_MAIPP_CANDIDATES: Optional[str] = "postgresql+asyncpg://maipp_user:maipp_pass@localhost:5432/maipp_candidates_db"
    NEO4J_URI: Optional[str] = "neo4j://localhost:7687"
    NEO4J_USER: Optional[str] = "neo4j"
    NEO4J_PASSWORD: Optional[str] = "password"

    # --- AWS Service Configuration ---
    AWS_REGION: Optional[str] = None

    # --- SQS Queue for incoming messages from UDIM ---
    UDIM_NOTIFICATION_QUEUE_URL: Optional[str] = None
    SQS_VISIBILITY_TIMEOUT: int = 180
    SQS_POLL_WAIT_TIME_SECONDS: int = 20
    MAIPP_PROCESSING_DLQ_URL: Optional[str] = None

    # --- Internal Service URLs ---
    CONSENT_API_URL: Optional[str] = "http://localhost:8008/internal/consent/v1" # Default example changed port to avoid conflict with udim if run locally

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_file_encoding='utf-8', case_sensitive=False)

@lru_cache()
def get_settings() -> Settings:
    s = Settings()
    # Configure logging first using the LOG_LEVEL from settings, before other logs.
    # This is a bit circular if logger is used for critical errors during settings load itself,
    # but pydantic_settings loads .env before this function is usually called by 'settings = get_settings()'.
    # Basic logging will be used until this point.
    numeric_level = getattr(logging, s.LOG_LEVEL.upper(), None)
    if not isinstance(numeric_level, int):
        initial_log_level = logging.INFO
        logging.basicConfig(level=initial_log_level, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', force=True)
        logger.warning(f"Invalid LOG_LEVEL '{s.LOG_LEVEL}' in settings. Defaulting to INFO for initial settings load logs.")
    else:
        initial_log_level = numeric_level
    logging.basicConfig(level=initial_log_level, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', force=True)


    if not s.UDIM_NOTIFICATION_QUEUE_URL:
        err_msg = "UDIM_NOTIFICATION_QUEUE_URL must be set in environment or .env file for MAIPP to function."
        logger.critical(err_msg)
        raise ValueError(err_msg)

    if not s.POSTGRES_DSN_UDIM_METADATA:
        err_msg = "POSTGRES_DSN_UDIM_METADATA must be set for MAIPP to access UserDataPackage info."
        logger.critical(err_msg)
        raise ValueError(err_msg)

    if not s.GOOGLE_GEMINI_API_KEY and not s.OPENAI_API_KEY and not s.ANTHROPIC_API_KEY:
        logger.warning(
            "Primary LLM API keys (GOOGLE_GEMINI_API_KEY, OPENAI_API_KEY, or ANTHROPIC_API_KEY) are not set. "
            "MAIPP functionality will be limited."
        )

    if not s.CONSENT_API_URL:
        logger.warning(
            "CONSENT_API_URL is not set. MAIPP will default to DENYING actions that require consent verification."
        )
    return s

settings = get_settings()

# Re-configure logging for all modules after settings are fully loaded and validated.
# This ensures that the logger instance used by other modules gets the correct level.
# The 'force=True' in basicConfig within get_settings might handle this, but explicit reconfig can be safer.
# However, direct calls to logger.info() etc. before this point might use default level if not careful.
# The current setup with logger at module level and basicConfig in get_settings should be okay.
```
