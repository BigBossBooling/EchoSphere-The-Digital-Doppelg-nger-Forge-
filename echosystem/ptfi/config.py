# echosystem/ptfi/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache
from typing import Optional
import logging # For logger in get_settings

logger = logging.getLogger(__name__)

class Settings(BaseSettings):
    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"
    APP_NAME: str = "EchoSphere PTFI Service"
    API_V1_STR: str = "/api/v1/ptfi" # Example base path for PTFI APIs

    # Database DSN for ExtractedTraitCandidate & UserRefinedTrait logs (PostgreSQL)
    POSTGRES_DSN_PTFI: Optional[str] = "postgresql+asyncpg://ptfi_user:ptfi_pass@localhost:5432/echo_phase1_db"

    # PKG Connection (Neo4j example)
    NEO4J_URI: Optional[str] = "neo4j://localhost:7687" # Use bolt, neo4j+s, or neo4j+ssc
    NEO4J_USER: Optional[str] = "neo4j"
    NEO4J_PASSWORD: Optional[str] = "password"

    # (If PTFI needs to call any AI assist LLMs directly - for future tasks)
    # OPENAI_API_KEY: Optional[str] = None
    # GOOGLE_GEMINI_API_KEY: Optional[str] = None

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_file_encoding='utf-8', case_sensitive=False)

@lru_cache()
def get_settings() -> Settings:
    s = Settings()
    # Configure logging as early as possible using the loaded settings
    numeric_level = getattr(logging, s.LOG_LEVEL.upper(), None)
    if not isinstance(numeric_level, int):
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', force=True)
        logger.warning(f"Invalid LOG_LEVEL '{s.LOG_LEVEL}' in settings. Defaulting to INFO for initial settings load logs.")
    else:
        logging.basicConfig(level=numeric_level, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', force=True)

    # Add critical config validation
    if not s.POSTGRES_DSN_PTFI:
        logger.critical("POSTGRES_DSN_PTFI must be set for PTFI service to function.")
        # raise ValueError("POSTGRES_DSN_PTFI must be set.") # Or handle gracefully depending on app logic
    if not s.NEO4J_URI:
        logger.warning("NEO4J_URI not set. PKG interaction features will be unavailable.")

    return s

settings = get_settings()
