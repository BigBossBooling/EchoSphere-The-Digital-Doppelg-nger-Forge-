import pytest
from unittest.mock import patch, MagicMock, AsyncMock # Added AsyncMock
import io
import os
from typing import Dict, Any, Optional
from PyPDF2 import PdfReader # For creating mock PDF content
import docx # For creating mock DOCX content

# Adjust import path for tests
try:
    from maipp import data_handler_service
    from maipp.data_handler_service import UserDataPackageInfo
    from maipp.config import Settings
except ImportError:
    import sys
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
    from maipp import data_handler_service
    from maipp.data_handler_service import UserDataPackageInfo
    from maipp.config import Settings


@pytest.fixture
def mock_settings_for_data_handler(monkeypatch):
    # Settings relevant to data_handler_service are minimal, mostly S3 bucket if used directly
    # For now, data_handler_service doesn't directly use settings for S3 bucket name (it's in package_info)
    settings_obj = Settings() # Use default settings for this test module
    monkeypatch.setattr(data_handler_service, "settings", settings_obj)
    return settings_obj

@pytest.fixture
def sample_user_data_package_info() -> UserDataPackageInfo:
    return UserDataPackageInfo(
        package_id="pkg_test_123",
        user_id="user_test_456",
        consent_token_id="consent_test_789",
        raw_data_reference="s3://test-bucket/users/user_test_456/packages/pkg_test_123/data.enc",
        encryption_key_id="kms_key_arn_example",
        data_type="text/plain",
        source_description="Test text file",
        metadata={"originalFilename": "test_file.txt", "fileSizeBytes": 100}
    )

# --- Tests for fetch_user_data_package_metadata ---
@pytest.mark.asyncio
async def test_fetch_user_data_package_metadata_success(sample_user_data_package_info):
    mock_pool = AsyncMock(spec=asyncpg.Pool)
    mock_conn = AsyncMock(spec=asyncpg.Connection)
    # Make pool.acquire() return our mock connection
    mock_pool.acquire.return_value = mock_conn
    # Make the connection itself a context manager that returns the mock connection
    mock_conn.__aenter__.return_value = mock_conn

    # Simulate a successful fetchrow call
    # The keys in the returned record must match what UserDataPackageInfo expects
    # after aliasing (package_id, user_id, etc.)
    db_record_data = sample_user_data_package_info.model_dump(by_alias=False) # Use model fields for mock DB
    # asyncpg.Record is not easily mockable, so we use a MagicMock that behaves like one for dict conversion
    mock_db_record = MagicMock(spec=asyncpg.Record)
    mock_db_record.__iter__.return_value = iter(db_record_data.keys()) # For dict(record)
    mock_db_record.get.side_effect = lambda key, default=None: db_record_data.get(key, default)
    # Make fetchrow return our mock record
    mock_conn.fetchrow.return_value = mock_db_record

    # Patching the pool directly in the function call if it's passed as an argument
    # Or if it's a global in data_handler_service, patch it there.
    # For this test, we pass the mock_pool.

    result = await data_handler_service.fetch_user_data_package_metadata("pkg_test_123", mock_pool)

    assert result is not None
    assert isinstance(result, UserDataPackageInfo)
    assert result.package_id == sample_user_data_package_info.package_id
    assert result.user_id == sample_user_data_package_info.user_id
    mock_conn.fetchrow.assert_called_once()


@pytest.mark.asyncio
async def test_fetch_user_data_package_metadata_not_found():
    mock_pool = AsyncMock(spec=asyncpg.Pool)
    mock_conn = AsyncMock(spec=asyncpg.Connection)
    mock_pool.acquire.return_value = mock_conn
    mock_conn.__aenter__.return_value = mock_conn
    mock_conn.fetchrow.return_value = None # Simulate no record found

    result = await data_handler_service.fetch_user_data_package_metadata("pkg_not_found", mock_pool)
    assert result is None

@pytest.mark.asyncio
async def test_fetch_user_data_package_metadata_db_error():
    mock_pool = AsyncMock(spec=asyncpg.Pool)
    mock_conn = AsyncMock(spec=asyncpg.Connection)
    mock_pool.acquire.return_value = mock_conn
    mock_conn.__aenter__.return_value = mock_conn
    mock_conn.fetchrow.side_effect = asyncpg.PostgresError("Simulated DB connection error")

    result = await data_handler_service.fetch_user_data_package_metadata("pkg_db_error", mock_pool)
    assert result is None # Function should catch exception and return None

@pytest.mark.asyncio
async def test_fetch_user_data_package_metadata_no_pool():
    result = await data_handler_service.fetch_user_data_package_metadata("pkg_no_pool", None)
    assert result is None


# --- Tests for retrieve_and_decrypt_s3_object ---
@pytest.mark.asyncio
async def test_retrieve_and_decrypt_s3_object_success(sample_user_data_package_info):
    mock_s3_client = MagicMock(spec=boto3.client("s3"))
    mock_kms_client = MagicMock(spec=boto3.client("kms")) # Not directly used by func if SSE-KMS

    decrypted_bytes = b"decrypted data"
    mock_s3_response_body = MagicMock()
    mock_s3_response_body.read.return_value = decrypted_bytes
    mock_s3_client.get_object.return_value = {"Body": mock_s3_response_body}

    result = await data_handler_service.retrieve_and_decrypt_s3_object(
        sample_user_data_package_info, mock_s3_client, mock_kms_client
    )

    assert result == decrypted_bytes
    mock_s3_client.get_object.assert_called_once_with(
        Bucket="test-bucket", Key="users/user_test_456/packages/pkg_test_123/data.enc"
    )

@pytest.mark.asyncio
async def test_retrieve_and_decrypt_s3_object_s3_client_error(sample_user_data_package_info):
    mock_s3_client = MagicMock(spec=boto3.client("s3"))
    mock_kms_client = MagicMock(spec=boto3.client("kms"))

    # Simulate S3 ClientError
    from botocore.exceptions import ClientError as BotoClientError # Import for type
    mock_s3_client.get_object.side_effect = BotoClientError(
        {"Error": {"Code": "NoSuchKey", "Message": "The specified key does not exist."}},
        "GetObject"
    )

    result = await data_handler_service.retrieve_and_decrypt_s3_object(
        sample_user_data_package_info, mock_s3_client, mock_kms_client
    )
    assert result is None

@pytest.mark.asyncio
async def test_retrieve_and_decrypt_s3_object_invalid_uri(sample_user_data_package_info):
    mock_s3_client = MagicMock()
    mock_kms_client = MagicMock()
    invalid_package_info = sample_user_data_package_info.model_copy(update={"raw_data_reference": "invalid_uri"})

    result = await data_handler_service.retrieve_and_decrypt_s3_object(
        invalid_package_info, mock_s3_client, mock_kms_client
    )
    assert result is None
    mock_s3_client.get_object.assert_not_called()


# --- Tests for extract_text_from_decrypted_data ---
@pytest.mark.asyncio
async def test_extract_text_from_plain_text():
    content = b"This is a simple plain text."
    result = await data_handler_service.extract_text_from_decrypted_data(content, "text/plain", "test.txt")
    assert result == "This is a simple plain text."

@pytest.mark.asyncio
async def test_extract_text_from_pdf_mocked():
    # Create a mock PDF in memory
    pdf_buffer = io.BytesIO()
    # PyPDF2 doesn't have a simple "add text" and save, so we mock PdfReader
    with patch("udim.maipp.data_handler_service.PdfReader") as mock_pdf_reader_class: # Corrected patch path
        mock_reader_instance = MagicMock()
        mock_page1 = MagicMock()
        mock_page1.extract_text.return_value = "Page 1 text."
        mock_page2 = MagicMock()
        mock_page2.extract_text.return_value = "Page 2 text."
        mock_reader_instance.pages = [mock_page1, mock_page2]
        mock_pdf_reader_class.return_value = mock_reader_instance

        pdf_bytes = b"dummy pdf bytes" # Actual bytes don't matter as PdfReader is mocked
        result = await data_handler_service.extract_text_from_decrypted_data(pdf_bytes, "application/pdf", "test.pdf")

        assert result == "Page 1 text.\nPage 2 text."

@pytest.mark.asyncio
async def test_extract_text_from_docx_mocked():
    # Create a mock DOCX in memory
    # python-docx Document object is complex to build from scratch with text. Mock it.
    with patch("udim.maipp.data_handler_service.docx.Document") as mock_docx_document_class: # Corrected patch path
        mock_doc_instance = MagicMock()
        mock_para1 = MagicMock()
        mock_para1.text = "Paragraph 1."
        mock_para2 = MagicMock()
        mock_para2.text = "Paragraph 2."
        mock_doc_instance.paragraphs = [mock_para1, mock_para2]
        mock_docx_document_class.return_value = mock_doc_instance

        docx_bytes = b"dummy docx bytes" # Actual bytes don't matter
        result = await data_handler_service.extract_text_from_decrypted_data(docx_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "test.docx")

        assert result == "Paragraph 1.\nParagraph 2."

@pytest.mark.asyncio
async def test_extract_text_cleaning():
    raw_text = b"  Extra   spaces  \n\n   and\n\n\nmultiple\n  newlines. \tTabs too.  "
    result = await data_handler_service.extract_text_from_decrypted_data(raw_text, "text/plain", "test_cleaning.txt")
    # Expected: "Extra spaces\n\nand\n\nmultiple\nnewlines. Tabs too."
    # Current cleaning: "Extra spaces\n\nand\nmultiple\nnewlines. Tabs too." (leading/trailing on lines gone)
    # The regex `\n\s*\n\s*\n+` -> `\n\n` and `\s*\n\s*` -> `\n` and then stripping lines.
    # "  Extra   spaces  " -> "Extra spaces"
    # "\n\n   and\n\n\nmultiple\n  newlines. \tTabs too.  "
    # "\n\nand\n\nmultiple\nnewlines. Tabs too." (after line strips)
    assert result == "Extra spaces\n\nand\nmultiple\nnewlines. Tabs too."


@pytest.mark.asyncio
async def test_extract_text_unsupported_type():
    content = b"<xml>data</xml>"
    result = await data_handler_service.extract_text_from_decrypted_data(content, "application/xml", "test.xml")
    assert result is None

@pytest.mark.asyncio
async def test_extract_text_extraction_error_pdf():
    with patch("udim.maipp.data_handler_service.PdfReader", side_effect=Exception("PDF Read Error")): # Corrected patch path
        pdf_bytes = b"corrupted pdf bytes"
        result = await data_handler_service.extract_text_from_decrypted_data(pdf_bytes, "application/pdf", "test_error.pdf")
        assert result is None

# --- Tests for securely_dispose_of_decrypted_data ---
# These are harder to assert directly for in-memory objects beyond checking for no exceptions.
# For file paths, we can check if os.remove was called.

@patch("udim.maipp.data_handler_service.os.remove") # Corrected patch path
@patch("udim.maipp.data_handler_service.os.path.exists", return_value=True)
def test_securely_dispose_temp_file(mock_path_exists, mock_os_remove):
    temp_file_path = "/tmp/test_temp_file.data"
    data_handler_service.securely_dispose_of_decrypted_data(temp_file_path, "pkg_dispose_test")
    mock_os_remove.assert_called_once_with(temp_file_path)

def test_securely_dispose_bytes():
    byte_data = b"some secret data"
    # This test mainly ensures no exceptions are raised.
    # Actual memory clearing is up to Python's GC.
    data_handler_service.securely_dispose_of_decrypted_data(byte_data, "pkg_dispose_test_bytes")
    # To truly test if 'del' was effective, you'd need more complex memory inspection,
    # which is beyond typical unit testing. Assume 'del' works as intended by Python.

def test_securely_dispose_bytesio():
    bytes_io_data = io.BytesIO(b"some secret data")
    assert not bytes_io_data.closed
    data_handler_service.securely_dispose_of_decrypted_data(bytes_io_data, "pkg_dispose_test_bytesio")
    assert bytes_io_data.closed
