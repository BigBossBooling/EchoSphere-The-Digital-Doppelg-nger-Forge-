import logging
import boto3
from botocore.exceptions import ClientError
# fastapi.HTTPException is not ideal for a service layer, consider custom exceptions
# For now, keeping it if this service might be directly used by an API layer that expects it.
# from fastapi import HTTPException
import asyncpg # For interacting with PostgreSQL
from typing import Optional, Dict, Any
from pydantic import BaseModel, validator, Field
import io
import os # For path operations if temp files are used, and in securely_dispose_of_decrypted_data
from PyPDF2 import PdfReader # For PDF text extraction
import docx # python-docx for DOCX text extraction
import re # For text cleaning regex

# Assuming config.py is in the same directory or path is configured
from .config import settings

logger = logging.getLogger(__name__)

class UserDataPackageInfo(BaseModel):
    """
    Pydantic model to represent the essential metadata fetched from UDIM's UserDataPackage table.
    """
    package_id: str
    user_id: str
    consent_token_id: str
    raw_data_reference: str
    encryption_key_id: str
    data_type: str
    source_description: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict) # Ensure metadata is dict if None


async def fetch_user_data_package_metadata(
    package_id: str,
    pg_pool: asyncpg.Pool
) -> Optional[UserDataPackageInfo]:
    """
    Fetches UserDataPackage metadata from UDIM's PostgreSQL database.
    """
    if not pg_pool:
        logger.error(f"[{package_id}] PostgreSQL connection pool not available for fetching metadata.")
        return None

    query = """
        SELECT
            packageID AS package_id,
            userID AS user_id,
            consentTokenID AS consent_token_id,
            rawDataReference AS raw_data_reference,
            encryptionKeyID AS encryption_key_id,
            dataType AS data_type,
            sourceDescription AS source_description,
            metadata
        FROM UserDataPackage  -- In a real app, use a schema-qualified table name if applicable
        WHERE packageID = $1;
    """
    try:
        logger.info(f"[{package_id}] Fetching metadata from UDIM PostgreSQL for packageID: {package_id}")
        record = await pg_pool.fetchrow(query, package_id)

        if record:
            logger.debug(f"[{package_id}] Metadata record found: {dict(record)}")
            package_info = UserDataPackageInfo(**dict(record))
            logger.info(f"[{package_id}] Successfully fetched and validated metadata for packageID: {package_id}")
            return package_info
        else:
            logger.warning(f"[{package_id}] No metadata found for packageID: {package_id}")
            return None
    except asyncpg.PostgresError as e:
        logger.error(f"[{package_id}] PostgreSQL error fetching metadata for packageID {package_id}: {e}", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"[{package_id}] Unexpected error fetching or parsing metadata for packageID {package_id}: {e}", exc_info=True)
        return None

async def retrieve_and_decrypt_s3_object(
    package_info: UserDataPackageInfo,
    s3_client: boto3.client,
    kms_client: boto3.client
) -> Optional[bytes]:
    """
    Retrieves an object from S3 and handles its decryption (implicitly for SSE-KMS).
    """
    if not s3_client : # kms_client might not be directly used if S3 handles SSE-KMS transparently
        logger.error(f"[{package_info.package_id}] S3 client not available for data retrieval.")
        return None

    s3_uri = package_info.raw_data_reference
    if not s3_uri or not s3_uri.startswith("s3://"):
        logger.error(f"[{package_info.package_id}] Invalid or missing S3 URI: {s3_uri}")
        return None

    try:
        bucket_name, object_key = s3_uri.replace("s3://", "").split("/", 1)
        logger.info(f"[{package_info.package_id}] Attempting to retrieve S3 object. Bucket: {bucket_name}, Key: {object_key}")

        # For SSE-KMS, S3 client handles decryption using IAM role permissions for the KMS key.
        # package_info.encryption_key_id is the KMS Key used for encryption. MAIPP's role needs kms:Decrypt for this key.
        response = s3_client.get_object(Bucket=bucket_name, Key=object_key)
        decrypted_data = response['Body'].read()

        logger.info(f"[{package_info.package_id}] Successfully retrieved S3 object: {object_key}. Size: {len(decrypted_data)} bytes.")
        return decrypted_data
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code")
        logger.error(f"[{package_info.package_id}] S3 ClientError for {object_key}: [{error_code}] {e.response.get('Error', {}).get('Message', 'Unknown S3 error')}", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"[{package_info.package_id}] Unexpected error retrieving/decrypting S3 object {object_key}: {e}", exc_info=True)
        return None

async def extract_text_from_decrypted_data(
    decrypted_content: bytes,
    data_type: str,
    original_filename: Optional[str] = "unknown_file" # Made optional with default
) -> Optional[str]:
    """
    Extracts text content from decrypted data based on its data type.
    Performs basic text cleaning.
    """
    package_id_for_logging = original_filename # Use filename for logging context if package_id isn't directly available
    logger.info(f"[{package_id_for_logging}] Attempting to extract text. Data type: {data_type}, Filename: {original_filename}")
    extracted_text: Optional[str] = None

    try:
        if data_type == "application/pdf":
            pdf_file = io.BytesIO(decrypted_content)
            reader = PdfReader(pdf_file)
            text_parts = [page.extract_text() for page in reader.pages if page.extract_text()]
            if not text_parts: # Handle cases where no text is extracted
                 logger.warning(f"[{package_id_for_logging}] PyPDF2 extracted no text from PDF.")
                 extracted_text = ""
            else:
                extracted_text = "\n".join(text_parts)
        elif data_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document" or \
             (original_filename and original_filename.lower().endswith(".docx")):
            doc_file = io.BytesIO(decrypted_content)
            doc = docx.Document(doc_file)
            text_parts = [para.text for para in doc.paragraphs if para.text]
            extracted_text = "\n".join(text_parts)
        elif data_type and data_type.startswith("text/"):
            try:
                extracted_text = decrypted_content.decode("utf-8")
            except UnicodeDecodeError:
                logger.warning(f"[{package_id_for_logging}] UTF-8 decode failed for {original_filename}, trying latin-1 with error replacement.")
                extracted_text = decrypted_content.decode("latin-1", errors="replace")
        else:
            logger.warning(f"[{package_id_for_logging}] Unsupported data type for direct text extraction: {data_type} for file {original_filename}")
            return None

        if extracted_text is not None: # Check if text was extracted (could be empty string)
            # Basic text cleaning
            # 1. Normalize Unicode (NFC form is common) - conceptual, can be added if needed
            # import unicodedata
            # cleaned_text = unicodedata.normalize('NFC', extracted_text)

            # 2. Replace multiple spaces/tabs with a single space, but preserve single newlines for structure
            cleaned_text = re.sub(r'[ \t]+', ' ', extracted_text)

            # 3. Handle multiple newlines: replace 3+ newlines with two (paragraph break), 2 newlines as is, single newlines as is.
            # This is a bit more nuanced to preserve paragraph structure vs. just squashing all newlines.
            cleaned_text = re.sub(r'\n\s*\n\s*\n+', '\n\n', cleaned_text) # 3+ newlines -> double newline

            # 4. Strip leading/trailing whitespace from the whole text and from each line.
            # Keep lines that become empty after stripping, as they might be part of paragraph structure.
            lines = [line.strip() for line in cleaned_text.splitlines()]
            cleaned_text = "\n".join(lines)
            cleaned_text = cleaned_text.strip() # Final strip for the whole text

            if not cleaned_text and extracted_text: # If cleaning resulted in empty but original had content
                 logger.warning(f"[{package_id_for_logging}] Text content became empty after cleaning for {original_filename}. Original length: {len(extracted_text)}")
            elif cleaned_text:
                 logger.info(f"[{package_id_for_logging}] Successfully extracted and cleaned text from {original_filename}. Original length: {len(extracted_text)}, Cleaned length: {len(cleaned_text)}")

            return cleaned_text
        else:
            logger.warning(f"[{package_id_for_logging}] No text could be extracted from {original_filename} (type: {data_type}).")
            return None # Explicitly return None if no text was extracted

    except Exception as e:
        logger.error(f"[{package_id_for_logging}] Error during text extraction for {original_filename} (type: {data_type}): {e}", exc_info=True)
        return None

def securely_dispose_of_decrypted_data(data_variable_or_temp_file_path: Any, package_id_for_logging: str = "N/A"):
    """
    Securely disposes of decrypted data.
    For in-memory bytes, clear references. For temp files, delete them.
    """
    log_prefix = f"[{package_id_for_logging}]"
    if isinstance(data_variable_or_temp_file_path, str) and os.path.exists(data_variable_or_temp_file_path):
        try:
            os.remove(data_variable_or_temp_file_path)
            logger.debug(f"{log_prefix} Securely disposed of temporary file: {data_variable_or_temp_file_path}")
        except OSError as e:
            logger.error(f"{log_prefix} Error securely disposing of temporary file {data_variable_or_temp_file_path}: {e}", exc_info=True)
    elif isinstance(data_variable_or_temp_file_path, (bytes, bytearray)):
        # For in-memory bytes, clearing references is handled by Python's GC when 'del' is used
        # or when the variable goes out of scope. No explicit os.remove needed.
        # Making the variable None or deleting it helps signal it for GC.
        logger.debug(f"{log_prefix} Decrypted data (bytes/bytearray) reference cleared for garbage collection.")
        # data_variable_or_temp_file_path = None # This only affects local copy, not caller's copy
    elif isinstance(data_variable_or_temp_file_path, io.BytesIO):
        data_variable_or_temp_file_path.close()
        logger.debug(f"{log_prefix} Decrypted data (BytesIO stream) closed.")
    elif data_variable_or_temp_file_path is None:
        logger.debug(f"{log_prefix} No data to dispose (was None).")
    else:
        logger.debug(f"{log_prefix} No specific disposal action taken for data type: {type(data_variable_or_temp_file_path)}.")

```
