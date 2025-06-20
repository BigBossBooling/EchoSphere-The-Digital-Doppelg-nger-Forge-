import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock, ANY
import uuid
import io
from datetime import datetime, timezone

# Adjust import path
from udim.main import app # Assuming 'app' is the FastAPI instance from main.py
from udim.config import settings as app_settings # Import the global settings from main's perspective
# from udim.main import FileUploadResponse # If this model is used for assertion type checks explicitly

# It's good practice for tests to not modify a global settings object directly if possible.
# TestClient can sometimes be initialized with a specific app instance that might use patched settings.
# Or, use dependency overrides in FastAPI for settings if settings are injected.

@pytest.fixture(scope="module")
def client():
    # TestClient uses the global 'app' which uses the global 'settings'
    # We will use monkeypatch in tests to alter 'app_settings' which 'app' depends on.
    return TestClient(app)

@pytest.fixture(autouse=True) # autouse=True to apply to all tests in this module
def patch_global_settings(monkeypatch):
    # This fixture will patch the settings used by the app instance for all tests in this file.
    # It's important if tests modify settings or rely on specific test settings.
    # Create a copy of original settings if you need to restore, or ensure each test
    # that modifies settings does so carefully via its own monkeypatching of specific values.
    # For this case, we'll set specific values needed for the upload endpoint.
    monkeypatch.setattr(app_settings, "S3_BUCKET_NAME", "test-main-bucket-endpoint")
    monkeypatch.setattr(app_settings, "KMS_KEY_ID", "test-main-kms-key-endpoint")
    # API_V1_STR is already in app_settings from config.py, ensure it's used
    # monkeypatch.setattr(app_settings, "API_V1_STR", "/api/v1") # Assuming it's already this

# Mock the SQS service for all tests in this file as it's called by the endpoint
@pytest.fixture(autouse=True)
def mock_sqs_service_for_main(monkeypatch):
    mock_sqs_send = MagicMock(return_value="sqs-message-id-mocked-in-main-tests")
    # The import path for patching must be where the function is *looked up*
    # In main.py, it's `from .sqs_service import send_event_to_maipp_queue`
    # So, we patch 'udim.main.send_event_to_maipp_queue'
    monkeypatch.setattr("udim.main.send_event_to_maipp_queue", mock_sqs_send)
    return mock_sqs_send


@patch("udim.main.upload_file_to_s3") # Mock the s3_service.upload_file_to_s3 function as it's called by main.py
def test_direct_upload_file_success(mock_upload_s3_call, client): # mock_settings_main is now patch_global_settings
    expected_s3_key = f"users/{app.TEMP_USER_ID}/some_uuid_placeholder_from_test/test_upload.txt.enc"
    mock_upload_s3_call.return_value = expected_s3_key

    file_content = b"Test content for upload endpoint"
    files = {"file": ("test_upload.txt", io.BytesIO(file_content), "text/plain")}
    data = {"sourceDescription": "Test Upload Description"}

    response = client.post(f"{app_settings.API_V1_STR}/ingest/upload_file", files=files, data=data)

    assert response.status_code == 202 # Accepted
    json_response = response.json()

    assert uuid.UUID(json_response["ingestion_id"]) # Valid UUID
    assert json_response["s3_object_key"] == expected_s3_key
    assert json_response["filename"] == "test_upload.txt"
    assert json_response["content_type"] == "text/plain" # This comes from the file tuple
    assert json_response["size_bytes"] == len(file_content)
    assert json_response["status"] == "accepted_for_processing"

    mock_upload_s3_call.assert_called_once()
    # Check arguments passed to the mocked upload_file_to_s3
    args, kwargs = mock_upload_s3_call.call_args
    assert kwargs['user_id'] == app.TEMP_USER_ID
    assert kwargs['original_filename'] == "test_upload.txt"
    assert isinstance(uuid.UUID(kwargs['package_id']), uuid.UUID) # package_id is a string UUID

    # Check that SQS send was called (mocked by mock_sqs_service_for_main)
    from udim.main import send_event_to_maipp_queue as mocked_sqs_in_main # get the mock
    mocked_sqs_in_main.assert_called_once()
    sqs_payload_arg = mocked_sqs_in_main.call_args[0][0]
    assert sqs_payload_arg["packageID"] == json_response["ingestion_id"]
    assert sqs_payload_arg["rawDataReference"] == f"s3://{app_settings.S3_BUCKET_NAME}/{expected_s3_key}"


@patch("udim.main.upload_file_to_s3")
def test_direct_upload_file_s3_fails(mock_upload_s3_call, client):
    mock_upload_s3_call.side_effect = HTTPException(status_code=500, detail="S3 Upload Failed in Test")

    file_content = b"content"
    files = {"file": ("s3_fail_test.txt", io.BytesIO(file_content), "text/plain")}
    data = {"sourceDescription": "Test S3 failure"}

    response = client.post(f"{app_settings.API_V1_STR}/ingest/upload_file", files=files, data=data)

    assert response.status_code == 500
    assert "S3 Upload Failed in Test" in response.json()["detail"]

def test_direct_upload_file_invalid_content_type(client):
    file_content = b"some image data"
    # Assuming "image/gif" is not in ALLOWED_FILE_TYPES in main.py
    files = {"file": ("invalid_type.gif", io.BytesIO(file_content), "image/gif")}
    data = {"sourceDescription": "Test invalid content type"}

    response = client.post(f"{app_settings.API_V1_STR}/ingest/upload_file", files=files, data=data)

    assert response.status_code == 415 # Unsupported Media Type
    assert "Unsupported file type" in response.json()["detail"]

def test_direct_upload_file_too_large(client, monkeypatch):
    # Temporarily reduce MAX_FILE_SIZE_BYTES for this test within main.py's scope
    monkeypatch.setattr("udim.main.MAX_FILE_SIZE_BYTES", 10) # 10 bytes limit

    file_content = b"This content is definitely larger than 10 bytes."
    files = {"file": ("large_file.txt", io.BytesIO(file_content), "text/plain")}
    data = {"sourceDescription": "Test file too large"}

    response = client.post(f"{app_settings.API_V1_STR}/ingest/upload_file", files=files, data=data)

    assert response.status_code == 413 # Payload Too Large
    # The detail message in main.py shows MB, so it might be "0MB" if limit is very small
    assert "File size exceeds maximum limit" in response.json()["detail"]

def test_direct_upload_file_empty_file(client):
    file_content = b"" # Empty content
    files = {"file": ("empty_file.txt", io.BytesIO(file_content), "text/plain")}
    data = {"sourceDescription": "Test empty file"}

    response = client.post(f"{app_settings.API_V1_STR}/ingest/upload_file", files=files, data=data)

    assert response.status_code == 400 # Bad Request
    assert "File cannot be empty" in response.json()["detail"]


def test_direct_upload_missing_form_data(client):
    file_content = b"test content"
    files = {"file": ("test_file.txt", io.BytesIO(file_content), "text/plain")}
    # Missing sourceDescription
    # data = {}

    response = client.post(f"{app_settings.API_V1_STR}/ingest/upload_file", files=files) # No data=...

    assert response.status_code == 422 # Unprocessable Entity (FastAPI validation error)
    # Check for detail structure matching FastAPI's validation errors
    json_response = response.json()
    assert any(err["type"] == "missing" and err["loc"] == ["body", "sourceDescription"] for err in json_response["detail"])


@patch("udim.main.upload_file_to_s3")
@patch("udim.main.send_event_to_maipp_queue") # Already auto-mocked but can be specifically controlled
def test_direct_upload_sqs_failure_still_returns_202(mock_send_sqs, mock_upload_s3_call, client):
    expected_s3_key = f"users/{app.TEMP_USER_ID}/some_uuid_placeholder_from_test/test_upload_sqs_fail.txt.enc"
    mock_upload_s3_call.return_value = expected_s3_key
    # Simulate SQS send raising an HTTPException (as per sqs_service.py)
    mock_send_sqs.side_effect = HTTPException(status_code=500, detail="Simulated SQS Send Failure")

    file_content = b"Test SQS failure scenario"
    files = {"file": ("test_upload_sqs_fail.txt", io.BytesIO(file_content), "text/plain")}
    data = {"sourceDescription": "Test SQS Failure"}

    response = client.post(f"{app_settings.API_V1_STR}/ingest/upload_file", files=files, data=data)

    assert response.status_code == 202 # User request is still accepted
    json_response = response.json()
    assert json_response["s3_object_key"] == expected_s3_key
    # Critical log for SQS failure is expected (can't check logs directly here without more setup)
    # but the API should reflect that the file upload part was accepted.
    mock_upload_s3_call.assert_called_once()
    mock_send_sqs.assert_called_once()


def test_health_check_endpoint(client): # Removed mock_settings_main as it's auto-used
    response = client.get("/health")
    assert response.status_code == 200
    json_response = response.json()
    assert json_response["status"] == "ok"
    assert json_response["service"] == app_settings.APP_NAME # Use app_settings directly
    assert json_response["environment"] == app_settings.APP_ENV
```
