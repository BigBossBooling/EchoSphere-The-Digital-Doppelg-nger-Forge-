import logging
import boto3
from botocore.exceptions import ClientError
from fastapi import UploadFile, HTTPException

# Assuming config.py is in the same directory or path is configured
from .config import settings

logger = logging.getLogger(__name__)

# Initialize S3 client once
# In a production FastAPI app, Boto3 clients are often managed within lifespan events
# or via a dependency injection system to facilitate testing and configuration.
# For this focused task, initializing it here based on environment configuration for credentials/region.
try:
    s3_client = boto3.client(
        "s3",
        # region_name=settings.S3_AWS_REGION # If S3_AWS_REGION is added to settings
        # Credentials will be picked up from environment variables, IAM role, or ~/.aws/credentials
    )
except Exception as e:
    logger.error(f"Failed to initialize S3 client: {e}")
    s3_client = None # Ensure it's None if initialization fails

async def upload_file_to_s3(
    file: UploadFile,
    user_id: str,
    package_id: str,
    original_filename: str
) -> str:
    """
    Uploads a file to S3 with server-side encryption using KMS.

    Args:
        file: The FastAPI UploadFile object.
        user_id: The ID of the user uploading the file.
        package_id: The unique package ID for this upload.
        original_filename: The original name of the file.

    Returns:
        The S3 object key (path within the bucket).

    Raises:
        HTTPException: If S3 client is not initialized, configuration is missing, or upload fails.
    """
    if not s3_client:
        logger.error("S3 client is not initialized. Cannot upload file.")
        raise HTTPException(status_code=500, detail="S3 storage service is not available.")

    if not settings.S3_BUCKET_NAME:
        logger.error("S3_BUCKET_NAME is not configured in settings.")
        raise HTTPException(status_code=500, detail="S3 storage bucket is not configured.")

    # Basic sanitization for S3 key compatibility and security.
    # Replace non-alphanumeric (excluding '.', '_', '-') with '_'.
    # Ensure it doesn't start or end with problematic characters if necessary.
    safe_filename_chars = []
    for char_code in original_filename.encode('utf-8'):
        char = chr(char_code)
        if char.isalnum() or char in ('.', '_', '-'):
            safe_filename_chars.append(char)
        else:
            safe_filename_chars.append('_')

    safe_filename = "".join(safe_filename_chars)

    # Prevent empty filename after sanitization
    if not safe_filename.strip('_.- '): # Check if it's empty or only separators
        safe_filename = "uploaded_file"
    # Further S3 key best practices could be applied here (e.g., length checks, no leading slashes)


    s3_object_key = f"users/{user_id}/packages/{package_id}/{safe_filename}.enc"

    logger.info(f"Attempting to upload file to S3. Bucket: {settings.S3_BUCKET_NAME}, Key: {s3_object_key}")

    try:
        # Ensure file pointer is at the beginning for reading
        await file.seek(0)

        extra_args = {
            "ServerSideEncryption": "aws:kms"
        }
        # KMS_KEY_ID from settings should be the Key ARN or Alias ARN
        if settings.KMS_KEY_ID and settings.KMS_KEY_ID.strip():
            extra_args["SSEKMSKeyId"] = settings.KMS_KEY_ID.strip()
            logger.info(f"Using specific KMS Key ID for S3 SSE: {settings.KMS_KEY_ID.strip()}")
        else:
            logger.warning(
                "No specific KMS_KEY_ID configured in settings (KMS_KEY_ID is empty or not set). "
                "Relying on S3 bucket's default KMS encryption settings or AWS managed KMS key for S3."
            )
            # If bucket has default KMS encryption with a specific key, that will be used.
            # If bucket has default SSE-S3 (AES256), then ServerSideEncryption: "aws:kms" would override to AWS managed KMS key.
            # If bucket has no default, ServerSideEncryption: "aws:kms" uses an AWS managed KMS key for S3.

        s3_client.upload_fileobj(
            file.file, # The underlying file-like object from UploadFile
            settings.S3_BUCKET_NAME,
            s3_object_key,
            ExtraArgs=extra_args
        )
        logger.info(f"Successfully uploaded file to S3: s3://{settings.S3_BUCKET_NAME}/{s3_object_key}")
        return s3_object_key
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code")
        error_message = e.response.get("Error", {}).get("Message", "Unknown S3 client error")
        logger.error(f"S3 ClientError for {s3_object_key}: [{error_code}] {error_message}")
        # Provide a more generic message to the client for security reasons
        raise HTTPException(status_code=500, detail="Could not upload file to S3 storage.")
    except Exception as e:
        logger.error(f"Unexpected error during S3 upload for {s3_object_key}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="An unexpected error occurred during file upload.")
    finally:
        await file.close() # Always close the file
```
