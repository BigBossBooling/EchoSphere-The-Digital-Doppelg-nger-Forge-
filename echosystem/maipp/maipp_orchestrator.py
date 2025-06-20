import logging
import boto3
import json
import time
from botocore.exceptions import ClientError
import signal
import sys
import asyncio
import asyncpg
from typing import Optional, List, Dict, Any
import httpx
import uuid
from datetime import datetime, timezone

from .config import settings, Settings
from .data_handler_service import (
    UserDataPackageInfo,
    fetch_user_data_package_metadata,
    retrieve_and_decrypt_s3_object,
    securely_dispose_of_decrypted_data,
    extract_text_from_decrypted_data
)
from .consent_client_service import verify_consent_for_action, ConsentVerificationResponse
from .ai_adapters.google_gemini_adapter import GoogleGeminiAdapter
from .ai_adapters.base_adapter import AIAdapterError
from .models import RawAnalysisFeatureSet, ExtractedTraitCandidateModel # Added ExtractedTraitCandidateModel
from .feature_store_service import save_batch_raw_analysis_features
from .trait_derivation_service import derive_traits_from_features # Added
from .candidate_store_service import save_batch_extracted_trait_candidates # Added

logger = logging.getLogger(__name__)

# Global clients
sqs_client = None
s3_client = None
kms_client = None
pg_pool_udim: Optional[asyncpg.Pool] = None
http_client: Optional[httpx.AsyncClient] = None

mongo_client: Optional[AsyncIOMotorClient] = None
maipp_db: Optional[AsyncIOMotorDatabase] = None

pg_pool_maipp_candidates: Optional[asyncpg.Pool] = None # For MAIPP's ExtractedTraitCandidate store
graph_db_driver_placeholder = None

gemini_topic_adapter: Optional[GoogleGeminiAdapter] = None

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
    global sqs_client, s3_client, kms_client, pg_pool_udim, http_client, mongo_client, maipp_db
    global gemini_topic_adapter, pg_pool_maipp_candidates # Added pg_pool_maipp_candidates

    configure_logging(current_settings.LOG_LEVEL)
    logger.info(f"MAIPP ({current_settings.APP_NAME}) Initializing dependencies in {current_settings.APP_ENV} mode...")

    try:
        aws_client_args = {}
        if current_settings.AWS_REGION: aws_client_args['region_name'] = current_settings.AWS_REGION
        sqs_client = boto3.client("sqs", **aws_client_args)
        s3_client = boto3.client("s3", **aws_client_args)
        kms_client = boto3.client("kms", **aws_client_args)
        logger.info(f"AWS clients (SQS, S3, KMS) initialized.")

        if current_settings.POSTGRES_DSN_UDIM_METADATA:
            pg_pool_udim = await asyncpg.create_pool(dsn=current_settings.POSTGRES_DSN_UDIM_METADATA, min_size=1, max_size=10)
            logger.info(f"PostgreSQL pool for UDIM Metadata initialized.")
        else:
            raise ValueError("POSTGRES_DSN_UDIM_METADATA is not configured.")

        if current_settings.POSTGRES_DSN_MAIPP_CANDIDATES: # New pool for MAIPP candidates
            pg_pool_maipp_candidates = await asyncpg.create_pool(dsn=current_settings.POSTGRES_DSN_MAIPP_CANDIDATES, min_size=1, max_size=5)
            logger.info(f"PostgreSQL pool for MAIPP Trait Candidates initialized.")
        else:
            # Depending on whether this is critical for all MAIPP flows, either raise ValueError or log warning
            logger.warning("POSTGRES_DSN_MAIPP_CANDIDATES not set. Trait candidate storage will be unavailable.")
            # raise ValueError("POSTGRES_DSN_MAIPP_CANDIDATES is not configured.")


        http_client = httpx.AsyncClient()
        logger.info("HTTPX AsyncClient initialized.")

        if current_settings.MONGO_DB_URL and current_settings.MONGO_MAIPP_DATABASE_NAME:
            from motor.motor_asyncio import AsyncIOMotorClient
            mongo_client = AsyncIOMotorClient(current_settings.MONGO_DB_URL)
            maipp_db = mongo_client[current_settings.MONGO_MAIPP_DATABASE_NAME]
            try:
                await maipp_db.command('ping')
                logger.info(f"MongoDB client initialized for DB: {current_settings.MONGO_MAIPP_DATABASE_NAME}")
            except Exception as e:
                logger.error(f"MongoDB ping failed: {e}", exc_info=True)
                raise ConnectionError(f"MongoDB connection/ping failed: {e}")
        else:
            logger.warning("MongoDB URL or Database Name not configured. RawAnalysisFeatures storage will be unavailable.")

        if current_settings.GOOGLE_GEMINI_API_KEY:
            gemini_model_name = "gemini-1.0-pro" # Default or pull from settings
            gemini_topic_adapter = GoogleGeminiAdapter(model_name=gemini_model_name)
            if not gemini_topic_adapter.client:
                 logger.warning(f"GoogleGeminiAdapter client for {gemini_topic_adapter.model_name} failed to initialize.")
                 gemini_topic_adapter = None
            else:
                 logger.info(f"GoogleGeminiAdapter initialized with model: {gemini_topic_adapter.model_name}")
        else:
            gemini_topic_adapter = None
            logger.warning("Google Gemini API key not set, Gemini adapter will be skipped.")

        logger.info("MAIPP Dependencies initialization routines completed.")

    except Exception as e:
        logger.error(f"Failed to initialize MAIPP dependencies: {e}", exc_info=True)
        raise

async def process_data_package(message_payload: dict, current_settings: Settings) -> str:
    package_id = message_payload.get('packageID', 'Unknown')
    user_id_str = message_payload.get('userID', 'Unknown')
    consent_token_id_str = message_payload.get('consentTokenID', 'Unknown')
    sqs_message_id = message_payload.get('sqsMessageId', 'N/A')

    log_prefix = f"[{package_id} SQS_Msg_ID:{sqs_message_id}]"
    logger.info(f"{log_prefix} Starting processing. UserID: {user_id_str}, DataType: {message_payload.get('dataType')}")

    required_keys = ["packageID", "userID", "consentTokenID", "rawDataReference", "dataType"]
    if not all(key in message_payload for key in required_keys):
        logger.error(f"{log_prefix} Invalid SQS message payload: Missing required keys.", extra={"payload": message_payload})
        return "DELETE_MALFORMED"

    package_info: Optional[UserDataPackageInfo] = None
    decrypted_data: Optional[bytes] = None
    extracted_text: Optional[str] = None
    all_raw_features_for_package: List[RawAnalysisFeatureSet] = [] # Initialize list to store feature sets

    try:
        # Check critical dependencies needed for the core flow
        if not all([pg_pool_udim, http_client, s3_client, kms_client, (maipp_db if settings.MONGO_DB_URL else True), (pg_pool_maipp_candidates if settings.POSTGRES_DSN_MAIPP_CANDIDATES else True)]):
            logger.error(f"{log_prefix} Critical data store or HTTP clients not initialized.")
            return "RETRY_LATER"

        package_info = await fetch_user_data_package_metadata(package_id, pg_pool_udim)
        if not package_info: return "DELETE_NO_METADATA"

        decrypted_data = await retrieve_and_decrypt_s3_object(package_info, s3_client, kms_client)
        if decrypted_data is None: return "RETRY_LATER"

        original_filename = package_info.metadata.get('originalFilename', 'unknown_file') if package_info.metadata else 'unknown_file'

        text_based_content_available = False
        # ... (Text extraction logic as before, populating extracted_text and text_based_content_available) ...
        if package_info.data_type.startswith("text/") or \
           package_info.data_type in ["application/pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"] or \
           (original_filename and (original_filename.lower().endswith(".docx") or original_filename.lower().endswith(".pdf"))):
            consent_scope_text_extraction = f"action:extract_text,resource_package_id:{package_info.package_id}"
            consent_extraction = await verify_consent_for_action(package_info.user_id, package_info.consent_token_id, consent_scope_text_extraction, http_client, package_id)
            if consent_extraction.is_valid:
                extracted_text = await extract_text_from_decrypted_data(decrypted_data, package_info.data_type, original_filename)
                if extracted_text: text_based_content_available = True; logger.info(f"{log_prefix} Text extracted. Length: {len(extracted_text)}.")
                else: logger.warning(f"{log_prefix} Text extraction returned no content for {original_filename}.")
            else: logger.warning(f"{log_prefix} Consent DENIED for text extraction. Reason: {consent_extraction.reason}")

        # Conceptual Gemini Topic Extraction (as before, populating all_raw_features_for_package)
        if extracted_text and text_based_content_available and gemini_topic_adapter:
            # ... (Gemini adapter call and feature creation logic as in Turn 84, appending to all_raw_features_for_package) ...
            consent_scope_topic = f"action:analyze_text_topics,resource_package_id:{package_info.package_id},model:gemini"
            consent_topic = await verify_consent_for_action(package_info.user_id, package_info.consent_token_id, consent_scope_topic, http_client, package_id)
            feature_status = "failure_consent_denied"; gemini_analysis_result_payload = {"error": f"Consent denied: {consent_topic.reason}"}
            if consent_topic.is_valid:
                logger.info(f"{log_prefix} Consent GRANTED for topic extraction (Gemini).")
                try:
                    topic_prompt_template = "Extract up to 5 key topics from the following text. List each topic on a new line. Text: {text}"
                    gemini_analysis_result_payload = await gemini_topic_adapter.analyze_text(extracted_text, topic_prompt_template, max_output_tokens=200)
                    feature_status = "success"; logger.info(f"{log_prefix} Topic extraction (Gemini) successful.")
                except AIAdapterError as adapter_err:
                    logger.error(f"{log_prefix} Gemini Adapter error: {adapter_err}", exc_info=True)
                    feature_status = "failure_adapter_error"; gemini_analysis_result_payload = {"error": str(adapter_err)}
            else: logger.warning(f"{log_prefix} Consent DENIED for topic extraction (Gemini). Reason: {consent_topic.reason}")
            all_raw_features_for_package.append(RawAnalysisFeatureSet(
                userID=uuid.UUID(package_info.user_id), sourceUserDataPackageID=uuid.UUID(package_info.package_id),
                modality="text", modelNameOrType=gemini_topic_adapter.get_model_identifier(),
                extractedFeatures=gemini_analysis_result_payload, timestamp=datetime.now(timezone.utc),
                status=feature_status, errorDetails=gemini_analysis_result_payload.get("error") if feature_status != "success" else None,
                consentTokenID_used=uuid.UUID(package_info.consent_token_id) if package_info.consent_token_id else None,
                required_scope_for_consent=consent_scope_topic
            ))


        # Store all collected RawAnalysisFeatures
        if all_raw_features_for_package:
            if maipp_db:
                inserted_ids = await save_batch_raw_analysis_features(maipp_db, all_raw_features_for_package)
                if inserted_ids: logger.info(f"{log_prefix} Stored {len(inserted_ids)} RawAnalysisFeatureSet records.")
                else: logger.error(f"{log_prefix} Failed to store RawAnalysisFeatureSet records.")
            else: logger.error(f"{log_prefix} MongoDB not configured. Cannot store RawAnalysisFeatures.")

        # Trait Derivation
        trait_candidates_list: List[ExtractedTraitCandidateModel] = []
        if all_raw_features_for_package: # Only derive if there are features
            logger.info(f"{log_prefix} Proceeding to trait derivation from {len(all_raw_features_for_package)} feature sets.")
            trait_candidates_list = await derive_traits_from_features(
                user_id=uuid.UUID(package_info.user_id), # Ensure UUID type
                source_package_id=uuid.UUID(package_info.package_id), # Ensure UUID type
                raw_features_list=all_raw_features_for_package
                # Pass gemini_topic_adapter (or a more generic one) if LLM synthesis is used in derive_traits
            )
            if trait_candidates_list:
                logger.info(f"{log_prefix} Generated {len(trait_candidates_list)} trait candidates.")
                # Store these candidates
                if pg_pool_maipp_candidates:
                    attempted_inserts = await save_batch_extracted_trait_candidates(pg_pool_maipp_candidates, trait_candidates_list)
                    logger.info(f"{log_prefix} Attempted to save {attempted_inserts} trait candidates to PostgreSQL.")
                    # Add more robust check for actual inserted count if save_batch function is enhanced
                else:
                    logger.error(f"{log_prefix} PostgreSQL for MAIPP Candidates not configured. Cannot store trait candidates.")
            else:
                logger.info(f"{log_prefix} No trait candidates generated.")
        else:
            logger.warning(f"{log_prefix} No raw features were generated, skipping trait derivation.")

        # TODO: PKG Population based on trait_candidates_list and/or all_raw_features_for_package

        logger.info(f"{log_prefix} Main processing logic finished. Simulating overall success.")
        return "SUCCESS"
    except Exception as e:
        logger.error(f"{log_prefix} Unhandled exception in process_data_package. Error: {e}", exc_info=True)
        raise
    finally:
        if decrypted_data:
            securely_dispose_of_decrypted_data(decrypted_data, package_id_for_logging=package_id)

async def main_sqs_consumer_loop(current_settings: Settings):
    # ... (SQS loop structure as before) ...
    global running
    critical_db_clients = [pg_pool_udim, http_client, s3_client, kms_client]
    if settings.MONGO_DB_URL: critical_db_clients.append(maipp_db)
    if settings.POSTGRES_DSN_MAIPP_CANDIDATES: critical_db_clients.append(pg_pool_maipp_candidates)

    if not all([sqs_client] + critical_db_clients):
        logger.critical("One or more critical clients not initialized. MAIPP consumer cannot start."); return
    if not current_settings.UDIM_NOTIFICATION_QUEUE_URL:
        logger.critical("UDIM_NOTIFICATION_QUEUE_URL not configured."); return
    logger.info(f"MAIPP SQS Consumer starting. Listening to queue: {current_settings.UDIM_NOTIFICATION_QUEUE_URL}")
    while running:
        try:
            response = sqs_client.receive_message(
                QueueUrl=current_settings.UDIM_NOTIFICATION_QUEUE_URL,
                AttributeNames=['ApproximateReceiveCount'], MaxNumberOfMessages=1,
                VisibilityTimeout=current_settings.SQS_VISIBILITY_TIMEOUT,
                WaitTimeSeconds=current_settings.SQS_POLL_WAIT_TIME_SECONDS
            )
            if "Messages" in response and running:
                message = response["Messages"][0]; receipt_handle = message["ReceiptHandle"]; message_id = message["MessageId"]
                logger.info(f"MAIPP: Message received. SQS_Msg_ID: {message_id}, ApproxReceiveCount: {message.get('Attributes', {}).get('ApproximateReceiveCount', '1')}")
                processing_status_code = "RETRY_LATER"
                try:
                    payload = json.loads(message["Body"]); payload['sqsMessageId'] = message_id
                    processing_status_code = await process_data_package(payload, current_settings)
                except json.JSONDecodeError:
                    logger.error(f"MAIPP: Failed to decode SQS message body. SQS_Msg_ID: {message_id}.", exc_info=True)
                    processing_status_code = "DELETE_MALFORMED"
                except Exception as e:
                    logger.error(f"MAIPP: Unhandled exception in SQS loop for SQS_Msg_ID: {message_id}. Error: {e}", exc_info=True)
                    processing_status_code = "RETRY_LATER"
                if processing_status_code in ["SUCCESS", "DELETE_MALFORMED", "DELETE_NO_METADATA"]:
                    logger.info(f"MAIPP: Deleting message {message_id} due to status: {processing_status_code}.")
                    try: sqs_client.delete_message(QueueUrl=current_settings.UDIM_NOTIFICATION_QUEUE_URL, ReceiptHandle=receipt_handle)
                    except ClientError as del_e: logger.error(f"Failed to delete SQS message {message_id}: {del_e}", exc_info=True)
                elif processing_status_code == "RETRY_LATER": logger.info(f"MAIPP: Processing for SQS_Msg_ID {message_id} resulted in RETRY_LATER.")
            elif not running: logger.info("MAIPP SQS Consumer: Shutdown signal during poll, exiting."); break
            else: logger.debug("MAIPP: No messages received in this poll cycle.")
        except ClientError as e:
            if not running: break
            logger.error(f"MAIPP: SQS ClientError in main loop: {e}", exc_info=True); time.sleep(10)
        except Exception as e:
            if not running: break
            logger.critical(f"MAIPP: Unexpected critical error in SQS consumer loop: {e}", exc_info=True); time.sleep(30)
        if not running: logger.info("MAIPP SQS Consumer: Loop terminated post-poll due to shutdown signal."); break
    logger.info("MAIPP SQS Consumer loop has finished.")

async def main():
    global running, http_client, pg_pool_udim, mongo_client, pg_pool_maipp_candidates # Added pg_pool_maipp_candidates
    signal.signal(signal.SIGINT, signal_handler); signal.signal(signal.SIGTERM, signal_handler)
    current_settings_obj = None
    try:
        current_settings_obj = get_settings()
        await initialize_maipp_dependencies(current_settings_obj)

        # Refined check for critical initializations
        critical_initializations = [
            sqs_client, current_settings_obj.UDIM_NOTIFICATION_QUEUE_URL, pg_pool_udim, http_client, s3_client, kms_client
        ]
        if current_settings_obj.MONGO_DB_URL: critical_initializations.append(mongo_client)
        if current_settings_obj.POSTGRES_DSN_MAIPP_CANDIDATES: critical_initializations.append(pg_pool_maipp_candidates)

        if all(critical_initializations):
             await main_sqs_consumer_loop(current_settings_obj)
        else: logger.critical("MAIPP cannot start due to missing critical configurations or failed initializations."); sys.exit(1)

    except ValueError as ve: logger.critical(f"MAIPP configuration error: {ve}", exc_info=True); sys.exit(1)
    except Exception as e: logger.critical(f"MAIPP application failed to start or crashed: {e}", exc_info=True); sys.exit(1)
    finally:
        logger.info("MAIPP Application attempting shutdown...")
        if pg_pool_udim:
            try: await pg_pool_udim.close(); logger.info("PostgreSQL UDIM metadata pool closed.")
            except Exception as e: logger.error(f"Error closing PostgreSQL UDIM pool: {e}", exc_info=True)
        if pg_pool_maipp_candidates: # Cleanup for MAIPP candidates pool
            try: await pg_pool_maipp_candidates.close(); logger.info("PostgreSQL MAIPP candidates pool closed.")
            except Exception as e: logger.error(f"Error closing PostgreSQL MAIPP candidates pool: {e}", exc_info=True)
        if http_client:
            try: await http_client.aclose(); logger.info("HTTPX AsyncClient closed.")
            except Exception as e: logger.error(f"Error closing HTTPX client: {e}", exc_info=True)
        if mongo_client:
            try: mongo_client.close(); logger.info("MongoDB client closed.")
            except Exception as e: logger.error(f"Error closing MongoDB client: {e}", exc_info=True)
        logger.info("MAIPP Application shutdown procedures complete.")
        sys.exit(0 if running else 1)

if __name__ == "__main__":
    from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
    asyncio.run(main())

```
