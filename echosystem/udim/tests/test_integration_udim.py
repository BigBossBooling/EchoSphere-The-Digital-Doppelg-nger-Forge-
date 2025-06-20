import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock, ANY # Still need some mocking for external calls if not using live test env
import uuid
import io
import json
import os

# Adjust import path as in previous test files
# This structure assumes 'echosystem' is the top-level package in PYTHONPATH,
# or tests are run from the 'echosystem' directory, or the current working directory is 'echosystem/udim'.
# For robust testing, ensuring PYTHONPATH is correctly set for your test runner is key.
try:
    from udim.main import app, TEMP_USER_ID # Import app and TEMP_USER_ID
    from udim.config import Settings
    from udim import s3_service # To allow mocking ClientError if not present
    from udim import sqs_service # To allow mocking ClientError if not present
except ImportError:
    import sys
    # Add 'echosystem' directory to sys.path to allow imports like 'from udim.main import app'
    # This assumes the tests are in 'echosystem/udim/tests/' and 'echosystem' is the project root.
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
    from udim.main import app, TEMP_USER_ID
    from udim.config import Settings
    from udim import s3_service
    from udim import sqs_service


# It's common for integration tests to use a separate configuration or override settings
# For example, pointing to a test S3 bucket or a local mock like LocalStack/MinIO.
# For this subtask, we'll assume some level of mocking for AWS services for simplicity
# and to avoid requiring live AWS resources for the test to run in this environment.
# A true integration test might use environment variables to point to test AWS resources.

@pytest.fixture(scope="module")
def client():
    # Configure app for testing if needed, e.g., override dependencies for external services
    return TestClient(app)

@pytest.fixture(scope="function") # Use function scope to reset mocks for each test
def mock_aws_services(monkeypatch):
    # Mock S3 client within s3_service
    mock_s3_client_instance = MagicMock()
    # Simulate successful upload_fileobj
    mock_s3_client_instance.upload_fileobj.return_value = None
    monkeypatch.setattr(s3_service, "s3_client", mock_s3_client_instance)

    # Mock SQS client within sqs_service
    mock_sqs_client_instance = MagicMock()
    mock_sqs_client_instance.send_message.return_value = {"MessageId": "test-sqs-message-id"}
    monkeypatch.setattr(sqs_service, "sqs_client", mock_sqs_client_instance)

    # Mock KMS (if s3_service explicitly calls KMS, though for SSE-S3 with KMS key, S3 client handles it)
    # As per current s3_service.py, direct KMS calls are not made by the service itself for SSE-KMS.
    # Boto3 S3 client handles interaction with KMS based on ExtraArgs.

    return mock_s3_client_instance, mock_sqs_client_instance

@pytest.fixture(scope="function") # Function scope to ensure settings are fresh for each test
def test_settings_override(monkeypatch):
    # Override settings for integration tests to use test resource names/URLs
    # These would typically point to LocalStack or actual test AWS resources
    # For this subtask, we'll use mock names, as the clients are mocked anyway.
    # Note: We are patching the 'settings' object that is imported by other modules.
    # This requires that those modules import 'settings' from 'udim.config'
    # (e.g., from .config import settings) and not create their own instances.

    # Store original settings to restore if needed, though pytest fixtures handle isolation.
    # from udim.config import settings as original_settings_module_instance
    # original_s3_bucket = original_settings_module_instance.S3_BUCKET_NAME

    test_settings_values = {
        "S3_BUCKET_NAME": "integration-test-bucket",
        "KMS_KEY_ID": "integration-test-kms-key-id", # Used by s3_service
        "SQS_MAIPP_NOTIFICATION_QUEUE_URL": "https://sqs.test-region.amazonaws.com/test-account/integration-maipp-queue",
        "API_V1_STR": "/api/v1",
        "APP_ENV": "test_integration",
        "LOG_LEVEL": "DEBUG" # Example override
    }

    # Create a new Settings instance with overrides for the test
    settings_override_obj = Settings(**test_settings_values)

    monkeypatch.setattr("udim.config.settings", settings_override_obj)
    monkeypatch.setattr("udim.main.settings", settings_override_obj)
    monkeypatch.setattr("udim.s3_service.settings", settings_override_obj)
    monkeypatch.setattr("udim.sqs_service.settings", settings_override_obj)

    # yield settings_override_obj # if you need to use the object in the test function
    # monkeypatch.setattr(original_settings_module_instance, "S3_BUCKET_NAME", original_s3_bucket) # Restore
    return settings_override_obj


@pytest.mark.asyncio
async def test_udim_ingestion_flow_success(client, test_settings_override, mock_aws_services):
    mock_s3_client, mock_sqs_client = mock_aws_services

    file_content = b"Integration test file content."
    test_filename = "integration_test.txt"
    files = {"file": (test_filename, io.BytesIO(file_content), "text/plain")}
    data = {"sourceDescription": "Integration test upload"}

    # Act
    response = client.post(f"{test_settings_override.API_V1_STR}/ingest/upload_file", files=files, data=data)

    # Assert API Response
    assert response.status_code == 202
    json_response = response.json()
    assert "ingestion_id" in json_response
    ingestion_id_str = json_response["ingestion_id"]
    assert uuid.UUID(ingestion_id_str) # Validate it's a UUID string
    assert json_response["filename"] == test_filename
    assert json_response["status"] == "accepted_for_processing"

    # Assert S3 Interaction (via mock)
    # The filename in S3 key includes '.enc' added by s3_service
    # s3_service.py uses str(ingestion_id) for package_id in path
    expected_s3_key = f"users/{TEMP_USER_ID}/packages/{ingestion_id_str}/{test_filename}.enc"

    mock_s3_client.upload_fileobj.assert_called_once()
    args_s3, kwargs_s3 = mock_s3_client.upload_fileobj.call_args

    assert args_s3[1] == test_settings_override.S3_BUCKET_NAME # Bucket name
    assert args_s3[2] == expected_s3_key # Object key

    assert "ExtraArgs" in kwargs_s3
    assert kwargs_s3["ExtraArgs"]["ServerSideEncryption"] == "aws:kms"
    assert kwargs_s3["ExtraArgs"]["SSEKMSKeyId"] == test_settings_override.KMS_KEY_ID

    # Assert SQS Interaction (via mock)
    mock_sqs_client.send_message.assert_called_once()
    args_sqs, kwargs_sqs = mock_sqs_client.send_message.call_args

    assert kwargs_sqs["QueueUrl"] == test_settings_override.SQS_MAIPP_NOTIFICATION_QUEUE_URL
    message_body = json.loads(kwargs_sqs["MessageBody"])

    assert message_body["packageID"] == ingestion_id_str
    assert message_body["userID"] == TEMP_USER_ID
    assert message_body["rawDataReference"] == f"s3://{test_settings_override.S3_BUCKET_NAME}/{expected_s3_key}"
    assert message_body["dataType"] == "text/plain"
    assert message_body["metadata"]["originalFilename"] == test_filename

@pytest.mark.asyncio
async def test_udim_ingestion_flow_s3_upload_fails(client, test_settings_override, mock_aws_services):
    mock_s3_client, mock_sqs_client = mock_aws_services

    # Ensure ClientError is available in s3_service for mocking its type
    if not hasattr(s3_service, 'ClientError'): # If boto3 is not imported in s3_service, ClientError won't be defined
        from botocore.exceptions import ClientError as BotoClientError # Import it for the test
        s3_service.ClientError = BotoClientError # Make it available for the mock's side_effect

    mock_s3_client.upload_fileobj.side_effect = s3_service.ClientError(
        error_response={"Error": {"Code": "InternalError", "Message": "Simulated S3 Network Error"}},
        operation_name="PutObject"
    )

    file_content = b"Content for S3 failure test."
    test_filename = "s3_fail_test.txt"
    files = {"file": (test_filename, io.BytesIO(file_content), "text/plain")}
    data = {"sourceDescription": "Test S3 upload failure"}

    response = client.post(f"{test_settings_override.API_V1_STR}/ingest/upload_file", files=files, data=data)

    assert response.status_code == 500
    json_response = response.json()
    # The actual detail message comes from s3_service.py's exception handling
    assert "Could not upload file to S3 storage" in json_response["detail"]

    mock_sqs_client.send_message.assert_not_called()

@pytest.mark.asyncio
async def test_udim_ingestion_flow_sqs_fails_still_returns_202(client, test_settings_override, mock_aws_services):
    mock_s3_client, mock_sqs_client = mock_aws_services

    if not hasattr(sqs_service, 'ClientError'): # Ensure ClientError is available in sqs_service for mocking
        from botocore.exceptions import ClientError as BotoClientError
        sqs_service.ClientError = BotoClientError

    mock_sqs_client.send_message.side_effect = sqs_service.ClientError(
        error_response={"Error": {"Code": "InternalError", "Message": "Simulated SQS Error"}},
        operation_name="SendMessage"
    )

    file_content = b"Content for SQS failure test."
    test_filename = "sqs_fail_test.txt"
    files = {"file": (test_filename, io.BytesIO(file_content), "text/plain")}
    data = {"sourceDescription": "Test SQS failure"}

    response = client.post(f"{test_settings_override.API_V1_STR}/ingest/upload_file", files=files, data=data)

    assert response.status_code == 202 # As per current logic in main.py
    json_response = response.json()
    assert "ingestion_id" in json_response
    # (The critical error is logged internally, not returned to user in the 202 response)

    mock_s3_client.upload_fileobj.assert_called_once()
    mock_sqs_client.send_message.assert_called_once() # It was called, and it failed
```
