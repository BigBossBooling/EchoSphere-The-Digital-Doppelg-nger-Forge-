# echosystem/phase2_feedback_engine/app/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache
from typing import Optional
import logging # For logging in get_settings if needed

logger = logging.getLogger(__name__)

class Settings(BaseSettings):
    APP_NAME: str = "EchoSphere Phase2 Feedback Engine"
    API_V1_STR: str = "/api/v1/persona"
    LOG_LEVEL: str = "INFO"
    APP_ENV: str = "development" # e.g., development, staging, production

    # --- AWS General Settings ---
    AWS_REGION: Optional[str] = "us-east-1" # Example
    AWS_ACCESS_KEY_ID: Optional[str] = None # For explicit credentials, if not using IAM roles
    AWS_SECRET_ACCESS_KEY: Optional[str] = None # For explicit credentials
    AWS_ENDPOINT_URL: Optional[str] = None # For LocalStack or other local AWS-compatible services (applied to S3, DynamoDB, SQS if not specified per service)

    # --- SQS Settings ---
    FEEDBACK_EVENT_SQS_QUEUE_URL: Optional[str] = None
    SQS_MAX_MESSAGES: int = 10 # Max messages to fetch per SQS poll
    SQS_VISIBILITY_TIMEOUT: int = 60 # Seconds: time message is hidden after being received
    SQS_POLL_WAIT_TIME: int = 10 # Seconds: SQS long polling duration

    # --- PostgreSQL Settings for Feedback DB ---
    POSTGRES_DSN_FEEDBACK_DB: Optional[str] = "postgresql://user:password@localhost:5432/feedback_db" # Example DSN
    DB_POOL_MIN_SIZE: int = 2
    DB_POOL_MAX_SIZE: int = 10

    # --- Persona Behavioral Model Store Settings ---
    # Option 1: DynamoDB
    BEHAVIORAL_MODEL_DYNAMODB_TABLE: Optional[str] = "EchoSphere_PersonaBehavioralModels"
    # Option 2: MongoDB
    BEHAVIORAL_MODEL_MONGODB_URI: Optional[str] = None # e.g., "mongodb://user:pass@host:port/db_name"
    BEHAVIORAL_MODEL_MONGODB_DATABASE: Optional[str] = "echosphere_behavioral_models"
    BEHAVIORAL_MODEL_MONGODB_COLLECTION: Optional[str] = "persona_behavioral_models"

    # --- S3 Settings for Large Model Artifacts ---
    MODEL_ARTIFACTS_S3_BUCKET: Optional[str] = "echosphere-persona-models-bucket" # Example bucket name

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_file_encoding='utf-8')

@lru_cache()
def get_settings() -> Settings:
    s = Settings()
    # Example validation logic within get_settings, can also be done with Pydantic validators in the class
    if s.APP_ENV == "production":
        if not s.FEEDBACK_EVENT_SQS_QUEUE_URL:
            logger.critical("CRITICAL: FEEDBACK_EVENT_SQS_QUEUE_URL is not set for production!")
        if not s.POSTGRES_DSN_FEEDBACK_DB:
            logger.critical("CRITICAL: POSTGRES_DSN_FEEDBACK_DB is not set for production!")
        if not s.MODEL_ARTIFACTS_S3_BUCKET:
            logger.warning("Warning: MODEL_ARTIFACTS_S3_BUCKET is not set for production.") # May or may not be critical
        if not s.BEHAVIORAL_MODEL_DYNAMODB_TABLE and not s.BEHAVIORAL_MODEL_MONGODB_URI:
            logger.warning("Warning: Neither DynamoDB table nor MongoDB URI is configured for behavioral models in production.")

    # Ensure only one NoSQL DB option is primarily configured if both URIs/Tables are set by mistake
    if s.BEHAVIORAL_MODEL_DYNAMODB_TABLE and s.BEHAVIORAL_MODEL_MONGODB_URI:
        logger.warning("Both DynamoDB table and MongoDB URI are configured for behavioral models. Please clarify which one to use or ensure application logic handles this.")

    return s

settings = get_settings()
