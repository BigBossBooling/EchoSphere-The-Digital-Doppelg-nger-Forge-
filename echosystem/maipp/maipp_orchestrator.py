import logging
import boto3
import json
import time
from botocore.exceptions import ClientError
import signal
import sys
import asyncio
import asyncpg
from typing import Optional, List, Dict, Any # Added List, Dict, Any
import httpx
import uuid # For RawAnalysisFeatures record creation

from .config import settings, Settings
from .data_handler_service import (
    UserDataPackageInfo,
    fetch_user_data_package_metadata,
    retrieve_and_decrypt_s3_object,
    securely_dispose_of_decrypted_data,
    extract_text_from_decrypted_data
)
from .consent_client_service import verify_consent_for_action, ConsentVerificationResponse
from .ai_adapters.google_gemini_adapter import GoogleGeminiAdapter # Added
from .ai_adapters.base_adapter import AIAdapterError # Added

logger = logging.getLogger(__name__)

# Global clients
sqs_client = None
s3_client = None
kms_client = None
pg_pool_udim: Optional[asyncpg.Pool] = None
http_client: Optional[httpx.AsyncClient] = None
mongo_client_placeholder = None # Placeholder for actual MongoDB client (e.g., Motor client)
postgres_pool_maipp_placeholder = None # Placeholder for actual PostgreSQL pool (e.g., asyncpg pool)
graph_db_driver_placeholder = None # Placeholder for actual Neo4j driver

# AI Service Adapters (globally initialized)
gemini_topic_adapter: Optional[GoogleGeminiAdapter] = None
# Add other adapters here as they are implemented
# e.g., openai_summary_adapter: Optional[OpenAIAdapter] = None

running = True

def signal_handler(signum, frame):
    global running
    logger.info(f"Signal {signum} received, initiating graceful shutdown of MAIPP Orchestrator...")
    running = False

def configure_logging(log_level_str: str):
    numeric_level = getattr(logging, log_level_str.upper(), logging.INFO)
    if not isinstance(numeric_level, int):
        logging.warning(f"Invalid log level in settings: {log_level_str}. Defaulting to INFO.")
        numeric_level = logging.INFO
    logging.basicConfig(level=numeric_level, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', force=True)
    logger.info(f"Logging configured to level: {log_level_str.upper()}")

async def initialize_maipp_dependencies(current_settings: Settings):
    global sqs_client, s3_client, kms_client, pg_pool_udim, http_client
    global gemini_topic_adapter # Add new adapter to globals
    # ... (other globals for DBs, AI clients)

    configure_logging(current_settings.LOG_LEVEL)
    logger.info(f"MAIPP ({current_settings.APP_NAME}) Initializing dependencies in {current_settings.APP_ENV} mode...")

    try:
        aws_client_args = {}
        if current_settings.AWS_REGION:
            aws_client_args['region_name'] = current_settings.AWS_REGION

        sqs_client = boto3.client("sqs", **aws_client_args)
        s3_client = boto3.client("s3", **aws_client_args)
        kms_client = boto3.client("kms", **aws_client_args)
        logger.info(f"AWS clients (SQS, S3, KMS) initialized (region: {current_settings.AWS_REGION or 'default'}).")

        if current_settings.POSTGRES_DSN_UDIM_METADATA:
            try:
                pg_pool_udim = await asyncpg.create_pool(
                    dsn=current_settings.POSTGRES_DSN_UDIM_METADATA, min_size=1, max_size=10
                )
                logger.info(f"PostgreSQL connection pool for UDIM Metadata initialized.")
            except Exception as e:
                logger.error(f"Failed to initialize PostgreSQL pool for UDIM Metadata: {e}", exc_info=True)
                raise
        else:
            logger.critical("POSTGRES_DSN_UDIM_METADATA not set. MAIPP cannot fetch package details.")
            raise ValueError("POSTGRES_DSN_UDIM_METADATA is not configured.")

        http_client = httpx.AsyncClient()
        logger.info("HTTPX AsyncClient initialized for internal API calls (e.g., Consent Service).")

        # Initialize AI Service Adapters
        if current_settings.GOOGLE_GEMINI_API_KEY:
            # Example: Initialize for a specific task like topic extraction
            # Model name could also come from settings if we want to configure different Gemini models
            gemini_topic_adapter = GoogleGeminiAdapter(model_name="gemini-1.0-pro") # Or "gemini-1.5-pro-latest"
            # The adapter's __init__ now calls _initialize_client asynchronously.
            # In a robust app, you might await self.adapter._initialize_client() if it were async
            # or ensure it's properly scheduled if client init is async and non-blocking.
            # For now, GoogleGeminiAdapter's _initialize_client is synchronous due to genai.configure()
            logger.info(f"GoogleGeminiAdapter for topics initialized with model: {gemini_topic_adapter.model_name}")
        else:
            gemini_topic_adapter = None
            logger.warning("Google Gemini API key not set in MAIPP settings, topic extraction via Gemini will be skipped.")

        logger.info("MAIPP Dependencies initialization routines completed.")

    except Exception as e:
        logger.error(f"Failed to initialize MAIPP dependencies: {e}", exc_info=True)
        raise

async def process_data_package(message_payload: dict, current_settings: Settings) -> str:
    package_id = message_payload.get('packageID', 'Unknown')
    user_id = message_payload.get('userID', 'Unknown')
    consent_token_id = message_payload.get('consentTokenID', 'Unknown')
    data_type = message_payload.get('dataType')
    sqs_message_id = message_payload.get('sqsMessageId', 'N/A')

    log_prefix = f"[{package_id} SQS_Msg_ID:{sqs_message_id}]"
    logger.info(f"{log_prefix} Starting processing. UserID: {user_id}, DataType: {data_type}")

    required_keys = ["packageID", "userID", "consentTokenID", "rawDataReference", "dataType"]
    if not all(key in message_payload for key in required_keys):
        logger.error(f"{log_prefix} Invalid SQS message payload: Missing required keys.", extra={"payload": message_payload})
        return "DELETE_MALFORMED"

    package_info: Optional[UserDataPackageInfo] = None
    decrypted_data: Optional[bytes] = None
    extracted_text: Optional[str] = None
    all_raw_features_for_package: List[Dict[str, Any]] = [] # To collect all RawAnalysisFeatures

    try:
        if not pg_pool_udim or not http_client:
            logger.error(f"{log_prefix} Critical dependencies (UDIM DB Pool or HTTP Client) not initialized.")
            return "RETRY_LATER"

        package_info = await fetch_user_data_package_metadata(package_id, pg_pool_udim)
        if not package_info:
            logger.error(f"{log_prefix} Failed to fetch UserDataPackage metadata.")
            return "DELETE_NO_METADATA"

        logger.debug(f"{log_prefix} Retrieving and decrypting data from {package_info.raw_data_reference}.")
        decrypted_data = await retrieve_and_decrypt_s3_object(package_info, s3_client, kms_client)
        if decrypted_data is None:
            logger.error(f"{log_prefix} Failed to retrieve/decrypt data.")
            return "RETRY_LATER"

        original_filename = package_info.metadata.get('originalFilename', 'unknown_file') if package_info.metadata else 'unknown_file'

        # --- Text Extraction (conditionally based on consent and data type) ---
        text_based_content_available = False
        if package_info.data_type.startswith("text/") or \
           package_info.data_type in ["application/pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"] or \
           (original_filename and (original_filename.lower().endswith(".docx") or original_filename.lower().endswith(".pdf"))):

            consent_scope_text_extraction = f"action:extract_text,resource_package_id:{package_info.package_id}"
            logger.debug(f"{log_prefix} Verifying consent for text extraction. Scope: {consent_scope_text_extraction}")
            consent_extraction = await verify_consent_for_action(
                package_info.user_id, package_info.consent_token_id, consent_scope_text_extraction, http_client, package_id
            )
            if consent_extraction.is_valid:
                logger.info(f"{log_prefix} Consent GRANTED for text extraction.")
                extracted_text = await extract_text_from_decrypted_data(
                    decrypted_data, package_info.data_type, original_filename
                )
                if extracted_text: # Could be empty string if doc was empty but extraction succeeded
                    logger.info(f"{log_prefix} Text extracted. Length: {len(extracted_text)}.")
                    text_based_content_available = True
                else: # None or empty string
                    logger.warning(f"{log_prefix} Text extraction returned no content for {original_filename}.")
            else:
                logger.warning(f"{log_prefix} Consent DENIED for text extraction. Reason: {consent_extraction.reason}")

        # --- Example: Topic Extraction using Google Gemini (if text available) ---
        if extracted_text and text_based_content_available and gemini_topic_adapter:
            consent_scope_topic = f"action:analyze_text_topics,resource_package_id:{package_info.package_id},model:gemini"
            logger.debug(f"{log_prefix} Verifying consent for topic extraction (Gemini). Scope: {consent_scope_topic}")
            consent_topic = await verify_consent_for_action(
                package_info.user_id, package_info.consent_token_id, consent_scope_topic, http_client, package_id
            )
            if consent_topic.is_valid:
                logger.info(f"{log_prefix} Consent GRANTED for topic extraction (Gemini).")
                try:
                    topic_prompt_template = "Extract up to 5 key topics from the following text. List each topic on a new line. Text: {text}"
                    gemini_analysis_result = await gemini_topic_adapter.analyze_text(
                        extracted_text, topic_prompt_template, max_output_tokens=200
                    )

                    # Create RawAnalysisFeatures record for this analysis
                    feature_set_id = str(uuid.uuid4())
                    raw_feature_entry = {
                        "featureSetID": feature_set_id,
                        "userID": package_info.user_id,
                        "sourceUserDataPackageID": package_info.package_id,
                        "modality": "text", # or "text_derived_from_document"
                        "modelNameOrType": gemini_topic_adapter.get_model_identifier(),
                        "extractedFeatures": gemini_analysis_result, # This is the dict returned by the adapter
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "status": "success"
                    }
                    all_raw_features_for_package.append(raw_feature_entry)
                    logger.info(f"{log_prefix} Topic extraction (Gemini) successful. Features: {str(gemini_analysis_result)[:200]}...")
                except AIAdapterError as adapter_err:
                    logger.error(f"{log_prefix} Gemini Adapter error during topic extraction: {adapter_err}", exc_info=True)
                    # Record this failure in RawAnalysisFeatures with error status
                    all_raw_features_for_package.append({
                        "featureSetID": str(uuid.uuid4()), "userID": package_info.user_id,
                        "sourceUserDataPackageID": package_info.package_id, "modality": "text",
                        "modelNameOrType": gemini_topic_adapter.get_model_identifier() if gemini_topic_adapter else "Gemini_UnknownModel",
                        "status": "failure", "errorDetails": str(adapter_err),
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    })
            else:
                logger.warning(f"{log_prefix} Consent DENIED for topic extraction (Gemini). Reason: {consent_topic.reason}")

        # --- Placeholder for other analyses (Sentiment, NER, Audio Emotion etc.) ---
        # Each would follow a similar pattern:
        # 1. Check if appropriate data is available (e.g., extracted_text for text analyses, decrypted_data for audio)
        # 2. Check if specific AI adapter is initialized
        # 3. Verify consent for the specific action + model
        # 4. If consent granted, call adapter's analyze_text/analyze_audio method
        # 5. Create RawAnalysisFeatures record (success or failure) and append to all_raw_features_for_package

        # After all analyses for this package are attempted:
        if all_raw_features_for_package:
            logger.info(f"{log_prefix} Conceptual: Storing {len(all_raw_features_for_package)} RawAnalysisFeatures records.")
            # STORE_RAW_FEATURES_BATCH(all_raw_features_for_package) # Task 5.1

        # Then, Trait Identification, ExtractedTraitCandidate storage, PKG Population...

        logger.info(f"{log_prefix} Main processing logic finished. Simulating overall success.")
        return "SUCCESS"
    except Exception as e:
        logger.error(f"{log_prefix} Unhandled exception in process_data_package. Error: {e}", exc_info=True)
        raise
    finally:
        if decrypted_data:
            logger.debug(f"{log_prefix} Cleaning up decrypted data.")
            securely_dispose_of_decrypted_data(decrypted_data, package_id_for_logging=package_id)
        else:
            logger.debug(f"{log_prefix} No decrypted data to dispose.")

# ... (main_sqs_consumer_loop and main async functions remain largely the same, ensuring they use the global AI adapter instances)

async def main():
    global running, http_client, pg_pool_udim, gemini_topic_adapter # Add other adapters if they need cleanup
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    current_settings_obj = None
    try:
        current_settings_obj = get_settings()
        await initialize_maipp_dependencies(current_settings_obj)
        # Check all critical global clients initialized by initialize_maipp_dependencies
        if all([sqs_client, current_settings_obj.UDIM_NOTIFICATION_QUEUE_URL, pg_pool_udim, http_client, s3_client, kms_client]):
             await main_sqs_consumer_loop(current_settings_obj)
        else:
            logger.critical("MAIPP cannot start due to missing critical configurations or failed client initializations.")
            sys.exit(1)
    except ValueError as ve:
        logger.critical(f"MAIPP configuration error: {ve}", exc_info=True)
        sys.exit(1)
    except Exception as e:
        logger.critical(f"MAIPP application failed to start or crashed during initialization: {e}", exc_info=True)
        sys.exit(1)
    finally:
        logger.info("MAIPP Application attempting shutdown...")
        if pg_pool_udim:
            try: await pg_pool_udim.close(); logger.info("PostgreSQL UDIM metadata pool closed.")
            except Exception as e: logger.error(f"Error closing PostgreSQL pool: {e}", exc_info=True)
        if http_client:
            try: await http_client.aclose(); logger.info("HTTPX AsyncClient closed.")
            except Exception as e: logger.error(f"Error closing HTTPX client: {e}", exc_info=True)
        # Add cleanup for other async clients/drivers (MongoDB, Neo4j, other AI clients) if they are initialized globally
        # e.g. if graph_db_driver_placeholder and hasattr(graph_db_driver_placeholder, 'close'): await graph_db_driver_placeholder.close()
        logger.info("MAIPP Application shutdown procedures complete.")
        sys.exit(0 if running else 1)


if __name__ == "__main__":
    # Need to import datetime for RawAnalysisFeatures timestamp
    from datetime import datetime, timezone
    asyncio.run(main())
```
