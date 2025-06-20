# echosystem/phase2_feedback_engine/tests/test_feedback_processor_service.py
import pytest
import uuid
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch # Added patch

from app.models.feedback_models import FeedbackEventModel
from app.models.behavioral_model_models import PersonaBehavioralModel # For type hint
from app.services.feedback_processor_service import (
    store_initial_feedback_event,
    update_feedback_event_status,
    process_sqs_feedback_message
)

# Mark all tests in this module as asyncio
pytestmark = pytest.mark.asyncio

@pytest.fixture
def mock_pg_pool():
    pool = MagicMock()
    # Mock acquire to return an async context manager
    acquire_cm = MagicMock()
    connection = AsyncMock() # Connection object needs to be an AsyncMock for awaitable methods
    acquire_cm.__aenter__.return_value = connection
    acquire_cm.__aexit__.return_value = None # Or an awaitable mock if needed
    pool.acquire.return_value = acquire_cm
    return pool, connection # Return connection to assert calls on it

@pytest.fixture
def sample_feedback_event_id():
    return uuid.uuid4()

@pytest.fixture
def sample_feedback_event_payload(sample_feedback_event_id):
    return {
        "feedback_event_id": str(sample_feedback_event_id),
        "persona_id": str(uuid.uuid4()),
        "interaction_id": str(uuid.uuid4()),
        "output_id": str(uuid.uuid4()),
        "feedback_type": "rating_positive",
        "user_rating_value": 5,
        "feedback_context": {"test": "context"},
        "received_timestamp": datetime.now(timezone.utc).isoformat(), # Ensure ISO format as from SQS
        "processing_status": "pending" # Initial status
    }

@pytest.fixture
def sample_feedback_event_model(sample_feedback_event_payload):
    # Pydantic V2 model_validate will parse ISO string for datetime
    return FeedbackEventModel.model_validate(sample_feedback_event_payload)


async def test_store_initial_feedback_event_success(mock_pg_pool, sample_feedback_event_model: FeedbackEventModel):
    pool, conn = mock_pg_pool
    conn.execute.return_value = "INSERT 0 1" # Simulate successful insert

    result = await store_initial_feedback_event(pool, sample_feedback_event_model)

    assert result is True
    conn.execute.assert_called_once()
    # Check query and params (simplified check, could be more specific)
    args = conn.execute.call_args[0]
    assert "INSERT INTO feedback_events" in args[0]
    assert args[1] == sample_feedback_event_model.feedback_event_id
    assert args[10] == "pending" # processing_status

async def test_store_initial_feedback_event_already_exists(mock_pg_pool, sample_feedback_event_model: FeedbackEventModel):
    pool, conn = mock_pg_pool
    conn.execute.return_value = "INSERT 0 0" # Simulate conflict / no insert

    result = await store_initial_feedback_event(pool, sample_feedback_event_model)
    assert result is True # Still true as it's considered "stored"
    conn.execute.assert_called_once()

async def test_store_initial_feedback_event_db_error(mock_pg_pool, sample_feedback_event_model: FeedbackEventModel):
    pool, conn = mock_pg_pool
    conn.execute.side_effect = Exception("DB Write Error")

    result = await store_initial_feedback_event(pool, sample_feedback_event_model)
    assert result is False

async def test_update_feedback_event_status_success(mock_pg_pool, sample_feedback_event_id: uuid.UUID):
    pool, conn = mock_pg_pool

    await update_feedback_event_status(pool, sample_feedback_event_id, "processed")

    conn.execute.assert_called_once()
    args = conn.execute.call_args[0]
    assert "UPDATE feedback_events" in args[0]
    assert args[1] == "processed"
    assert isinstance(args[2], datetime) # processed_timestamp
    assert args[4] == sample_feedback_event_id

async def test_update_feedback_event_status_error_msg(mock_pg_pool, sample_feedback_event_id: uuid.UUID):
    pool, conn = mock_pg_pool

    await update_feedback_event_status(pool, sample_feedback_event_id, "error", "Test error message")

    conn.execute.assert_called_once()
    args = conn.execute.call_args[0]
    assert args[1] == "error"
    assert args[3] == "Test error message" # error_message
    assert args[4] == sample_feedback_event_id


# --- Tests for process_sqs_feedback_message ---

@pytest.fixture
def mock_behavioral_updater_services():
    with patch("app.services.feedback_processor_service.get_active_behavioral_model", new_callable=AsyncMock) as mock_get_active, \
         patch("app.services.feedback_processor_service.apply_feedback_to_behavioral_model", new_callable=AsyncMock) as mock_apply_feedback, \
         patch("app.services.feedback_processor_service.save_behavioral_model", new_callable=AsyncMock) as mock_save_model:

        yield mock_get_active, mock_apply_feedback, mock_save_model

async def test_process_sqs_feedback_message_success_no_model_change(
    mock_pg_pool, sample_feedback_event_payload, mock_behavioral_updater_services
):
    pg_pool, pg_conn = mock_pg_pool
    pg_conn.execute.return_value = "INSERT 0 1" # For initial store and status update

    mock_get_active, mock_apply_feedback, mock_save_model = mock_behavioral_updater_services

    # Setup mocks from behavioral_model_updater_service
    active_model = PersonaBehavioralModel(persona_id=uuid.UUID(sample_feedback_event_payload["persona_id"]))
    mock_get_active.return_value = active_model
    mock_apply_feedback.return_value = None # No changes to the model

    message_body = json.dumps(sample_feedback_event_payload)
    result = await process_sqs_feedback_message(message_body, pg_pool, model_db_client=None)

    assert result is True # SQS message should be deleted

    # store_initial_feedback_event call (implicitly checked by two execute calls)
    # update_feedback_event_status call
    assert pg_conn.execute.call_count == 2
    update_call_args = pg_conn.execute.call_args_list[1][0] # Second call to execute
    assert "UPDATE feedback_events" in update_call_args[0]
    assert update_call_args[1] == "processed" # status
    assert "No model changes applied" in update_call_args[3] # error_message (used for info here)

    mock_get_active.assert_called_once_with(uuid.UUID(sample_feedback_event_payload["persona_id"]), None)
    mock_apply_feedback.assert_called_once()
    mock_save_model.assert_not_called()


async def test_process_sqs_feedback_message_success_with_model_change(
    mock_pg_pool, sample_feedback_event_payload, mock_behavioral_updater_services
):
    pg_pool, pg_conn = mock_pg_pool
    pg_conn.execute.return_value = "INSERT 0 1"

    mock_get_active, mock_apply_feedback, mock_save_model = mock_behavioral_updater_services

    active_model = PersonaBehavioralModel(persona_id=uuid.UUID(sample_feedback_event_payload["persona_id"]))
    updated_model = active_model.model_copy(deep=True)
    updated_model.model_version_id = uuid.uuid4() # Simulate a change

    mock_get_active.return_value = active_model
    mock_apply_feedback.return_value = updated_model
    mock_save_model.return_value = True # Simulate successful save

    message_body = json.dumps(sample_feedback_event_payload)
    result = await process_sqs_feedback_message(message_body, pg_pool, model_db_client=None)

    assert result is True
    assert pg_conn.execute.call_count == 2
    update_call_args = pg_conn.execute.call_args_list[1][0]
    assert update_call_args[1] == "processed"

    mock_get_active.assert_called_once()
    mock_apply_feedback.assert_called_once()
    mock_save_model.assert_called_once_with(updated_model, None)


async def test_process_sqs_feedback_message_json_decode_error(mock_pg_pool):
    pg_pool, _ = mock_pg_pool
    invalid_json_body = "this is not json"

    result = await process_sqs_feedback_message(invalid_json_body, pg_pool)
    assert result is True # Malformed message, should be deleted from SQS

async def test_process_sqs_feedback_message_pydantic_error(mock_pg_pool, sample_feedback_event_payload):
    pg_pool, _ = mock_pg_pool
    sample_feedback_event_payload["feedback_type"] = "INVALID_TYPE" # Make it invalid
    invalid_body = json.dumps(sample_feedback_event_payload)

    result = await process_sqs_feedback_message(invalid_body, pg_pool)
    assert result is True # Pydantic error, delete from SQS

async def test_process_sqs_initial_store_fails(mock_pg_pool, sample_feedback_event_payload):
    pg_pool, pg_conn = mock_pg_pool
    pg_conn.execute.side_effect = Exception("Initial DB store failed") # First call (store_initial) fails

    message_body = json.dumps(sample_feedback_event_payload)
    result = await process_sqs_feedback_message(message_body, pg_pool)

    assert result is False # Initial store failed, message should be retried by SQS
    pg_conn.execute.assert_called_once() # Only store_initial_feedback_event should be attempted

async def test_process_sqs_no_active_model_found(
    mock_pg_pool, sample_feedback_event_payload, mock_behavioral_updater_services
):
    pg_pool, pg_conn = mock_pg_pool
    pg_conn.execute.return_value = "INSERT 0 1"

    mock_get_active, _, _ = mock_behavioral_updater_services
    mock_get_active.return_value = None # No active model

    message_body = json.dumps(sample_feedback_event_payload)
    result = await process_sqs_feedback_message(message_body, pg_pool)

    assert result is True
    assert pg_conn.execute.call_count == 2 # Initial store + status update
    update_call_args = pg_conn.execute.call_args_list[1][0]
    assert update_call_args[1] == "error"
    assert "No active behavioral model found" in update_call_args[3]


async def test_process_sqs_save_updated_model_fails(
    mock_pg_pool, sample_feedback_event_payload, mock_behavioral_updater_services
):
    pg_pool, pg_conn = mock_pg_pool
    pg_conn.execute.return_value = "INSERT 0 1" # For initial store and status update

    mock_get_active, mock_apply_feedback, mock_save_model = mock_behavioral_updater_services

    active_model = PersonaBehavioralModel(persona_id=uuid.UUID(sample_feedback_event_payload["persona_id"]))
    updated_model = active_model.model_copy(deep=True)
    updated_model.model_version_id = uuid.uuid4()

    mock_get_active.return_value = active_model
    mock_apply_feedback.return_value = updated_model
    mock_save_model.return_value = False # Simulate save failure

    message_body = json.dumps(sample_feedback_event_payload)
    result = await process_sqs_feedback_message(message_body, pg_pool)

    assert result is True # Processed with error, delete from SQS
    assert pg_conn.execute.call_count == 2
    update_call_args = pg_conn.execute.call_args_list[1][0]
    assert update_call_args[1] == "error"
    assert "Failed to save updated behavioral model" in update_call_args[3]
    mock_save_model.assert_called_once()


async def test_process_sqs_model_update_phase_generic_exception(
    mock_pg_pool, sample_feedback_event_payload, mock_behavioral_updater_services
):
    pg_pool, pg_conn = mock_pg_pool
    pg_conn.execute.return_value = "INSERT 0 1"

    mock_get_active, _, _ = mock_behavioral_updater_services
    mock_get_active.side_effect = Exception("Error during get_active_model")

    message_body = json.dumps(sample_feedback_event_payload)
    result = await process_sqs_feedback_message(message_body, pg_pool)

    assert result is True # Processed with error, delete from SQS
    assert pg_conn.execute.call_count == 2 # Initial store + status update
    update_call_args = pg_conn.execute.call_args_list[1][0]
    assert update_call_args[1] == "error"
    assert "Model update failure: Error during get_active_model" in update_call_args[3] # Error message
    mock_get_active.assert_called_once()

# Test for UndefinedFunctionError during store_initial_feedback_event
async def test_store_initial_feedback_event_undefined_function_error(mock_pg_pool, sample_feedback_event_model: FeedbackEventModel):
    pool, conn = mock_pg_pool
    # Simulate asyncpg.exceptions.UndefinedFunctionError
    # This typically happens if custom ENUM types are not correctly recognized/casted.
    conn.execute.side_effect = asyncpg.exceptions.UndefinedFunctionError("Mocked UndefinedFunctionError")

    result = await store_initial_feedback_event(pool, sample_feedback_event_model)
    assert result is False # Should fail to store
    conn.execute.assert_called_once()
    # Logger should have been called with specific error message (checked manually or with log capture)
