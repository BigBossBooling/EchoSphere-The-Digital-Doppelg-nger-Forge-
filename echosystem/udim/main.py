from fastapi import FastAPI, File, UploadFile, HTTPException, Form, Depends
import logging
import uvicorn
import uuid # Import uuid module
from pydantic import BaseModel, Field # Import BaseModel and Field for response model
from typing import Optional, List
from datetime import datetime, timezone # Added timezone for UTC

# Assuming config.py is in the same directory 'udim' or the package is structured
# such that 'echosystem.udim.config' is resolvable.
from .config import settings
from .s3_service import upload_file_to_s3 # Import the s3_service function
from .sqs_service import send_event_to_maipp_queue # Import the SQS service function

# Configure logging using settings
numeric_log_level = getattr(logging, settings.LOG_LEVEL.upper(), None)
if not isinstance(numeric_log_level, int):
    # Fallback to INFO if LOG_LEVEL is invalid, and log a warning.
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logging.getLogger(__name__).warning(f"Invalid LOG_LEVEL '{settings.LOG_LEVEL}' in settings. Defaulting to INFO.")
else:
    logging.basicConfig(level=numeric_log_level, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

logger = logging.getLogger(__name__)

app = FastAPI(
    title=settings.APP_NAME,
    version="0.1.0", # Initial version for Phase 1
    description="User Data Ingestion Module (UDIM) for EchoSphere. Handles secure data uploads, initial validation, consent checks, and notifications for further processing.",
)

# --- Pydantic Models for API ---
class FileUploadResponse(BaseModel):
    ingestion_id: uuid.UUID
    s3_object_key: str
    filename: str
    content_type: Optional[str] = None
    size_bytes: Optional[int] = None
    status: str
    message: str

# Placeholder for User ID until auth is integrated
TEMP_USER_ID = "temp-user-id-phase1"

ALLOWED_FILE_TYPES: List[str] = ["text/plain", "application/pdf", "audio/mpeg", "audio/wav", "audio/mp3", "image/jpeg", "image/png"]
MAX_FILE_SIZE_BYTES: int = 100 * 1024 * 1024 # Max 100 MB

@app.get("/", tags=["Root"])
async def root():
    logger.info(f"{settings.APP_NAME} root endpoint was called.")
    return {"message": f"Welcome to {settings.APP_NAME}"}

@app.get("/health", tags=["Health Check"])
async def health_check():
    logger.info(f"Health check endpoint called for {settings.APP_NAME}")
    return {
        "status": "ok",
        "service": settings.APP_NAME,
        "environment": settings.APP_ENV,
        "log_level": settings.LOG_LEVEL,
        "version": app.version
    }

@app.post(settings.API_V1_STR + "/ingest/upload_file",
          response_model=FileUploadResponse,
          status_code=202, # HTTP 202 Accepted
          tags=["Ingestion"])
async def direct_upload_file(
    sourceDescription: str = Form(..., min_length=3, max_length=512, description="Description of the data source or file content."),
    # consentTokenID: str = Form(...), # To be added when consent logic is integrated (Task U4)
    file: UploadFile = File(..., description="The raw data file being uploaded.")
):
    logger.info(f"Received file upload request for: '{file.filename}', content-type: {file.content_type}, source: '{sourceDescription}'")

    if file.content_type not in ALLOWED_FILE_TYPES:
        logger.warning(f"Upload rejected for '{file.filename}': Unsupported file type '{file.content_type}'.")
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type: '{file.content_type}'. Allowed types are: {', '.join(ALLOWED_FILE_TYPES)}"
        )

    size_bytes: Optional[int] = None
    if hasattr(file, 'size') and file.size is not None:
        size_bytes = file.size
    else:
        logger.warning(f"File size for '{file.filename}' not directly available from UploadFile.size attribute. Size validation might be incomplete.")

    if size_bytes is not None and size_bytes > MAX_FILE_SIZE_BYTES:
        logger.warning(f"Upload rejected for '{file.filename}': File size {size_bytes} bytes exceeds limit of {MAX_FILE_SIZE_BYTES} bytes.")
        raise HTTPException(
            status_code=413,
            detail=f"File size exceeds maximum limit of {MAX_FILE_SIZE_BYTES // (1024*1024)}MB."
        )

    if size_bytes == 0:
        logger.warning(f"Upload rejected for '{file.filename}': File is empty.")
        raise HTTPException(status_code=400, detail="File cannot be empty.")

    ingestion_id = uuid.uuid4()
    s3_key = None # Initialize s3_key to ensure it's defined in all paths

    try:
        user_id_for_storage = TEMP_USER_ID

        s3_key = await upload_file_to_s3(
            file=file,
            user_id=user_id_for_storage,
            package_id=str(ingestion_id),
            original_filename=str(file.filename)
        )

        # Simulate UserDataPackage metadata (actual DB save is Task U5.7)
        user_data_package_metadata = {
            "packageID": str(ingestion_id),
            "userID": user_id_for_storage,
            # "consentTokenID": consentTokenID, # Placeholder
            "rawDataReference": f"s3://{settings.S3_BUCKET_NAME}/{s3_key}",
            "dataType": file.content_type,
            "sourceDescription": sourceDescription,
            "metadata": {
                "originalFilename": str(file.filename),
                "fileSizeBytes": size_bytes if size_bytes is not None else -1,
            },
            "uploadTimestamp": datetime.now(timezone.utc).isoformat(),
            "status": "pending_processing" # This would be updated by UDIM after DB record creation
        }
        logger.info(f"Simulated UserDataPackage metadata for SQS: {user_data_package_metadata['packageID']}")

        # Publish message to SQS for MAIPP (Task U7)
        sqs_payload = {
            "packageID": user_data_package_metadata["packageID"],
            "userID": user_data_package_metadata["userID"],
            # "consentTokenID": user_data_package_metadata["consentTokenID"], # When available
            "rawDataReference": user_data_package_metadata["rawDataReference"],
            "dataType": user_data_package_metadata["dataType"],
            "sourceDescription": user_data_package_metadata["sourceDescription"],
            "metadata": user_data_package_metadata["metadata"]
        }

        try:
            message_id = await send_event_to_maipp_queue(sqs_payload)
            logger.info(f"Successfully sent SQS notification for ingestion_id {ingestion_id}, SQS Message ID: {message_id}")
            # In a real scenario, the UserDataPackage DB record status might be updated here to 'notified_maipp'
        except HTTPException as sqs_http_exc:
            logger.critical(
                f"CRITICAL: File uploaded (ingestion_id: {ingestion_id}, S3 key: {s3_key}) " +
                f"but FAILED to send SQS notification to MAIPP. Manual intervention may be required. Error: {sqs_http_exc.detail}"
            )
            # The upload itself succeeded, so we still return 202. Alerting/monitoring is key for this failure.
        except Exception as sqs_e: # Catch any other unexpected errors from SQS service
             logger.critical(
                f"CRITICAL: File uploaded (ingestion_id: {ingestion_id}, S3 key: {s3_key}) " +
                f"but FAILED unexpectedly during SQS notification. Error: {str(sqs_e)}", exc_info=True
            )

        logger.info(f"File '{file.filename}' (Ingestion ID: {ingestion_id}) processing accepted. S3 Key: {s3_key}")
        return FileUploadResponse(
            ingestion_id=ingestion_id,
            s3_object_key=s3_key,
            filename=str(file.filename),
            content_type=file.content_type,
            size_bytes=size_bytes if size_bytes is not None else -1,
            status="accepted_for_processing",
            message=f"File '{file.filename}' received and accepted for processing. Ingestion ID: {ingestion_id}"
        )
    except HTTPException as http_exc:
        logger.error(f"HTTPException during upload for {file.filename}, ingestion_id {ingestion_id}: {http_exc.detail}", exc_info=True)
        raise http_exc
    except Exception as e:
        log_message = f"Unexpected error processing upload for {file.filename}"
        if 'ingestion_id' in locals() and ingestion_id: # Check if ingestion_id was generated
            log_message += f", ingestion_id {ingestion_id}"
        if s3_key: # Check if s3_key was set (i.e., S3 upload might have happened)
             log_message += f", s3_key {s3_key}"
        log_message += f": {str(e)}"
        logger.error(log_message, exc_info=True)
        raise HTTPException(status_code=500, detail=f"An unexpected server error occurred while processing your file.")

if __name__ == "__main__":
    log_config = uvicorn.config.LOGGING_CONFIG
    log_config["formatters"]["access"]["fmt"] = '%(asctime)s - %(levelname)s - %(client_addr)s - "%(request_line)s" %(status_code)s'
    log_config["formatters"]["default"]["fmt"] = '%(asctime)s - %(levelname)s - %(name)s - %(message)s'
    # Ensure Uvicorn loggers respect the application's configured log level
    for logger_name in ["uvicorn", "uvicorn.error", "uvicorn.access"]:
        log_config["loggers"][logger_name]["level"] = settings.LOG_LEVEL.upper()

    logger.info(f"Starting Uvicorn server for {settings.APP_NAME} in {settings.APP_ENV} mode on http://0.0.0.0:8000")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
```
