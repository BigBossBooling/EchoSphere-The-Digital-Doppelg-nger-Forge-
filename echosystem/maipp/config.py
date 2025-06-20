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
    MONGO_DB_URL: Optional[str] = "mongodb://localhost:27017"
    MONGO_MAIPP_DATABASE_NAME: str = "echosphere_maipp_db"
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
    CONSENT_API_URL: Optional[str] = "http://localhost:8008/internal/consent/v1"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_file_encoding='utf-8', case_sensitive=False)

@lru_cache()
def get_settings() -> Settings:
    s = Settings()
    numeric_level = getattr(logging, s.LOG_LEVEL.upper(), None)
    if not isinstance(numeric_level, int):
        initial_log_level = logging.INFO
        logging.basicConfig(level=initial_log_level, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', force=True)
        logger.warning(f"Invalid LOG_LEVEL '{s.LOG_LEVEL}' in settings. Defaulting to INFO for initial settings load logs.")
    else:
        initial_log_level = numeric_level
    logging.basicConfig(level=initial_log_level, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', force=True)

    critical_configs = {
        "UDIM_NOTIFICATION_QUEUE_URL": s.UDIM_NOTIFICATION_QUEUE_URL,
        "POSTGRES_DSN_UDIM_METADATA": s.POSTGRES_DSN_UDIM_METADATA,
        "MONGO_DB_URL": s.MONGO_DB_URL,
        "MONGO_MAIPP_DATABASE_NAME": s.MONGO_MAIPP_DATABASE_NAME,
        "POSTGRES_DSN_MAIPP_CANDIDATES": s.POSTGRES_DSN_MAIPP_CANDIDATES, # Added to critical checks
        # "NEO4J_URI": s.NEO4J_URI, # Neo4j might be optional if no graph features used initially
    }
    for config_name, config_value in critical_configs.items():
        if not config_value:
            err_msg = f"{config_name} must be set in environment or .env file for MAIPP to function."
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
    if not s.NEO4J_URI: # Add specific warning for Neo4j if not critical error
        logger.warning("NEO4J_URI not set. PKG features will be unavailable.")
    return s

settings = get_settings()
```
