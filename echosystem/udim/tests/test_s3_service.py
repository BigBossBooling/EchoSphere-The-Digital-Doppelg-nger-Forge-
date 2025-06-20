import pytest
from unittest.mock import patch, MagicMock, ANY
from fastapi import HTTPException, UploadFile
import io
from botocore.exceptions import ClientError # Import ClientError for mocking

# Adjust import path based on how you run pytest
# This structure assumes 'echosystem' is the top-level package in PYTHONPATH,
# or tests are run from the 'echosystem' directory.
from udim import s3_service # This will be resolved if 'echosystem' is in sys.path
from udim.config import Settings


@pytest.fixture
def mock_settings(monkeypatch):
    # This fixture provides a fresh Settings object for each test that uses it,
    # and patches it into the s3_service module where 'settings' is imported.
    test_s3_bucket = "test-bucket-s3-service"
    test_kms_key = "test-kms-key-id-s3-service"

    # Create an instance of Settings
    settings_obj = Settings(S3_BUCKET_NAME=test_s3_bucket, KMS_KEY_ID=test_kms_key)

    # Use monkeypatch to replace s3_service.settings with our test instance
    monkeypatch.setattr(s3_service, "settings", settings_obj)
    return settings_obj

@pytest.fixture
def mock_upload_file():
    file_content = b"This is test file content for S3."
    file_like_object = io.BytesIO(file_content)

    # Create a MagicMock that quacks like an UploadFile
    mock_file = MagicMock(spec=UploadFile)
    mock_file.file = file_like_object # This is the actual file-like object
    mock_file.filename = "s3_test_file.txt"
    mock_file.content_type = "text/plain" # Keep consistent
    mock_file.size = len(file_content) # Add size attribute

    # Mock async methods 'seek' and 'close'
    async def mock_seek_method(offset, whence=0):
        return file_like_object.seek(offset, whence)

    async def mock_close_method():
        file_like_object.close() # This will mark the BytesIO as closed

    mock_file.seek = MagicMock(side_effect=mock_seek_method)
    mock_file.close = MagicMock(side_effect=mock_close_method)

    return mock_file

@patch("udim.s3_service.boto3.client") # Patch the client at the source where it's looked up
@pytest.mark.asyncio
async def test_upload_file_to_s3_success(mock_boto_s3_client, mock_settings, mock_upload_file):
    # mock_settings fixture already patches s3_service.settings

    # Configure the mock S3 client that boto3.client("s3") will return
    mock_s3_instance = MagicMock()
    mock_boto_s3_client.return_value = mock_s3_instance

    user_id = "s3-user"
    package_id = "s3-package"

    s3_key = await s3_service.upload_file_to_s3(
        file=mock_upload_file,
        user_id=user_id,
        package_id=package_id,
        original_filename=mock_upload_file.filename
    )

    expected_s3_key = f"users/{user_id}/packages/{package_id}/{mock_upload_file.filename}.enc"
    assert s3_key == expected_s3_key

    mock_upload_file.seek.assert_called_once_with(0)
    mock_s3_instance.upload_fileobj.assert_called_once_with(
        mock_upload_file.file, # The BytesIO object
        mock_settings.S3_BUCKET_NAME,
        expected_s3_key,
        ExtraArgs={"ServerSideEncryption": "aws:kms", "SSEKMSKeyId": mock_settings.KMS_KEY_ID}
    )
    mock_upload_file.close.assert_called_once()

@patch("udim.s3_service.boto3.client")
@pytest.mark.asyncio
async def test_upload_file_to_s3_no_kms_key_id_success(mock_boto_s3_client, mock_settings, mock_upload_file):
    mock_settings.KMS_KEY_ID = "" # Override KMS_KEY_ID for this specific test case
                                  # mock_settings fixture ensures this change is localized

    mock_s3_instance = MagicMock()
    mock_boto_s3_client.return_value = mock_s3_instance

    user_id = "s3-user-no-kms"
    package_id = "s3-package-no-kms"

    s3_key = await s3_service.upload_file_to_s3(
        file=mock_upload_file,
        user_id=user_id,
        package_id=package_id,
        original_filename=mock_upload_file.filename
    )

    expected_s3_key = f"users/{user_id}/packages/{package_id}/{mock_upload_file.filename}.enc"
    assert s3_key == expected_s3_key
    mock_s3_instance.upload_fileobj.assert_called_once_with(
        mock_upload_file.file,
        mock_settings.S3_BUCKET_NAME,
        expected_s3_key,
        ExtraArgs={"ServerSideEncryption": "aws:kms"} # SSEKMSKeyId should not be present
    )
    mock_upload_file.close.assert_called_once()

@patch("udim.s3_service.boto3.client")
@pytest.mark.asyncio
async def test_upload_file_to_s3_client_error(mock_boto_s3_client, mock_settings, mock_upload_file):
    mock_s3_instance = MagicMock()
    # Simulate a ClientError from S3. Ensure the error object has a 'response' attribute.
    error_response = {"Error": {"Code": "AccessDenied", "Message": "Simulated S3 Access Denied"}}
    mock_s3_instance.upload_fileobj.side_effect = ClientError(error_response, "PutObject")
    mock_boto_s3_client.return_value = mock_s3_instance

    with pytest.raises(HTTPException) as exc_info:
        await s3_service.upload_file_to_s3(
            file=mock_upload_file,
            user_id="test-user-fail",
            package_id="test-package-s3-fail",
            original_filename=mock_upload_file.filename
        )
    assert exc_info.value.status_code == 500
    assert "Could not upload file to S3 storage" in exc_info.value.detail # Generic message shown to client
    mock_upload_file.close.assert_called_once()

@pytest.mark.asyncio
async def test_upload_file_to_s3_no_bucket_configured(monkeypatch, mock_upload_file):
    # Create a new Settings instance with S3_BUCKET_NAME as empty or None
    settings_no_bucket = Settings(S3_BUCKET_NAME="", KMS_KEY_ID="test-kms-key")
    monkeypatch.setattr(s3_service, "settings", settings_no_bucket)

    with pytest.raises(HTTPException) as exc_info:
        await s3_service.upload_file_to_s3(
            file=mock_upload_file,
            user_id="test-user-no-bucket",
            package_id="test-package-no-bucket-cfg",
            original_filename=mock_upload_file.filename
        )
    assert exc_info.value.status_code == 500
    assert "S3 storage bucket is not configured" in exc_info.value.detail
    # Depending on where the check for S3_BUCKET_NAME happens, close might or might not be called.
    # If check is before try-finally, close won't be called. If inside try, it will.
    # Current s3_service.py calls it after the check, so close() will be called.
    mock_upload_file.close.assert_called_once()

@patch("udim.s3_service.boto3.client", None) # Simulate s3_client being None (failed initialization)
@pytest.mark.asyncio
async def test_upload_file_to_s3_client_not_initialized(mock_settings, mock_upload_file, monkeypatch):
    # Need to ensure s3_service.s3_client is None for this test
    # This can be tricky if it's a module global.
    # One way is to patch it directly if the import structure allows or re-import under patch.
    # For this test, we are patching boto3.client to be None *when s3_service module is loaded*.
    # A more robust way is to make s3_client injectable or part of a class.
    # Given current s3_service.py structure, we can monkeypatch the s3_service.s3_client global.
    monkeypatch.setattr(s3_service, "s3_client", None)

    with pytest.raises(HTTPException) as exc_info:
        await s3_service.upload_file_to_s3(
            file=mock_upload_file,
            user_id="test-user",
            package_id="test-package-s3-init-fail",
            original_filename=mock_upload_file.filename
        )
    assert exc_info.value.status_code == 500
    assert "S3 storage service is not available" in exc_info.value.detail
    mock_upload_file.close.assert_called_once()
