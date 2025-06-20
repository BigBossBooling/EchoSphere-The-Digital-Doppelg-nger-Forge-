# echosystem/phase2_feedback_engine/tests/test_feedback_models.py
import pytest
import uuid
from datetime import datetime, timezone
from pydantic import ValidationError, HttpUrl # Added HttpUrl for sandbox_models

from app.models.feedback_models import FeedbackInput, FeedbackResponse, FeedbackEventModel
from app.models.behavioral_model_models import ModelFileReference, BehavioralRule, StyleParameter, PersonaBehavioralModel
from app.models.sandbox_models import SandboxRequest, SandboxInstanceDetails, SandboxCreationResponse, SandboxStatusResponse, SandboxTerminationResponse

def test_feedback_input_valid():
    data = {
        "persona_id": uuid.uuid4(),
        "interaction_id": uuid.uuid4(),
        "feedback_type": "rating_positive",
        "user_rating_value": 5
    }
    fb_input = FeedbackInput(**data)
    assert fb_input.persona_id == data["persona_id"]
    assert fb_input.feedback_type == "rating_positive"
    assert fb_input.user_rating_value == 5

def test_feedback_input_correction_text_requires_text():
    with pytest.raises(ValidationError) as exc_info:
        FeedbackInput(
            persona_id=uuid.uuid4(),
            interaction_id=uuid.uuid4(),
            feedback_type="correction_text"
            # user_provided_text is missing
        )
    assert "user_provided_text is required for feedback_type \"correction_text\"" in str(exc_info.value)

    # Should pass if text is provided
    FeedbackInput(
        persona_id=uuid.uuid4(),
        interaction_id=uuid.uuid4(),
        feedback_type="correction_text",
        user_provided_text="This is the correction."
    )

def test_feedback_input_invalid_type():
    with pytest.raises(ValidationError):
        FeedbackInput(
            persona_id="not-a-uuid", # Invalid UUID
            interaction_id=uuid.uuid4(),
            feedback_type="invalid_feedback_type" # Invalid Literal
        )

def test_feedback_response_serialization():
    fb_input_data = {
        "persona_id": uuid.uuid4(),
        "interaction_id": uuid.uuid4(),
        "feedback_type": "custom_feedback",
        "user_provided_text": "Great!"
    }
    fb_input = FeedbackInput(**fb_input_data)
    fb_response = FeedbackResponse(
        feedback_event_id=uuid.uuid4(),
        message="Feedback received.",
        received_feedback=fb_input
    )
    # Pydantic V2 uses model_dump_json()
    json_output = fb_response.model_dump_json()
    assert str(fb_response.feedback_event_id) in json_output
    assert str(fb_input.persona_id) in json_output # Check nested model's UUID

def test_feedback_event_model_defaults():
    fb_input_data = {
        "persona_id": uuid.uuid4(),
        "interaction_id": uuid.uuid4(),
        "feedback_type": "rating_positive",
    }
    event_id = uuid.uuid4()
    # Pass only required fields from FeedbackInput and feedback_event_id
    fb_event = FeedbackEventModel(feedback_event_id=event_id, **fb_input_data)

    assert fb_event.feedback_event_id == event_id
    assert fb_event.persona_id == fb_input_data["persona_id"]
    assert isinstance(fb_event.received_timestamp, datetime)
    assert fb_event.received_timestamp.tzinfo == timezone.utc
    assert fb_event.processing_status == "pending"
    assert fb_event.error_message is None

# --- Behavioral Model Tests ---

def test_model_file_reference_valid():
    data = {"storage_type": "S3", "path_uri": "s3://bucket/model.tar.gz"}
    ref = ModelFileReference(**data)
    assert ref.storage_type == "S3"
    assert ref.path_uri == data["path_uri"]

def test_behavioral_rule_defaults():
    rule = BehavioralRule(description="Test rule", condition_script="true", action_to_take="log_message")
    assert isinstance(rule.rule_id, uuid.UUID)
    assert rule.is_active is True
    assert isinstance(rule.created_at, datetime)

def test_style_parameter_valid():
    param = StyleParameter(parameter_name="Formality", value="neutral")
    assert param.parameter_name == "Formality"
    assert param.value == "neutral"
    assert isinstance(param.updated_at, datetime)

def test_persona_behavioral_model_defaults():
    persona_id = uuid.uuid4()
    model = PersonaBehavioralModel(persona_id=persona_id)
    assert model.persona_id == persona_id
    assert isinstance(model.model_version_id, uuid.UUID)
    assert model.is_active_model is False
    assert model.behavioral_rules == []
    assert model.style_parameters == []
    assert isinstance(model.created_at, datetime)

# --- Sandbox Model Tests ---

def test_sandbox_request_valid():
    data = {
        "persona_id": uuid.uuid4(),
        "behavioral_model_version_id": uuid.uuid4(),
        "test_scenarios": [{"prompt": "Hello"}],
        "callback_url": "http://localhost:8888/callback"
    }
    req = SandboxRequest(**data)
    assert req.persona_id == data["persona_id"]
    assert isinstance(req.callback_url, HttpUrl) # Pydantic converts string to HttpUrl

def test_sandbox_request_invalid_scenario():
    with pytest.raises(ValidationError):
        SandboxRequest(
            persona_id=uuid.uuid4(),
            behavioral_model_version_id=uuid.uuid4(),
            test_scenarios=[] # Must have at least one item
        )

def test_sandbox_instance_details_defaults():
    details = SandboxInstanceDetails(
        sandbox_id=uuid.uuid4(),
        persona_id=uuid.uuid4(),
        behavioral_model_version_id=uuid.uuid4(),
        status="provisioning"
    )
    assert isinstance(details.created_at, datetime)
    assert details.created_at.tzinfo == timezone.utc

def test_sandbox_models_serialization():
    details = SandboxInstanceDetails(
        sandbox_id=uuid.uuid4(),
        persona_id=uuid.uuid4(),
        behavioral_model_version_id=uuid.uuid4(),
        status="ready",
        access_endpoint="http://sandbox.example.com/123"
    )
    creation_resp = SandboxCreationResponse(message="Created", sandbox_details=details)
    json_output = creation_resp.model_dump_json() # Pydantic V2
    assert str(details.sandbox_id) in json_output
    assert str(details.access_endpoint) in json_output

    status_resp = SandboxStatusResponse(**details.model_dump()) # Pydantic V2
    json_output_status = status_resp.model_dump_json()
    assert str(details.sandbox_id) in json_output_status

    term_resp = SandboxTerminationResponse(sandbox_id=details.sandbox_id, status="terminated", message="Done")
    json_output_term = term_resp.model_dump_json()
    assert str(details.sandbox_id) in json_output_term

# Add more tests for edge cases, specific validation rules, and all fields for completeness.
# Example: Test HttpUrl validation for callback_url in SandboxRequest
def test_sandbox_request_invalid_url():
    with pytest.raises(ValidationError):
        SandboxRequest(
            persona_id=uuid.uuid4(),
            behavioral_model_version_id=uuid.uuid4(),
            test_scenarios=[{"prompt": "Hello"}],
            callback_url="not_a_valid_url"
        )

# Test Literal validation
def test_model_file_reference_invalid_storage_type():
    with pytest.raises(ValidationError):
        ModelFileReference(storage_type="FTP", path_uri="ftp://server/file")

def test_feedback_event_model_json_serialization_deserialization():
    original_event_id = uuid.uuid4()
    original_persona_id = uuid.uuid4()
    original_interaction_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    event_data = {
        "feedback_event_id": original_event_id,
        "persona_id": original_persona_id,
        "interaction_id": original_interaction_id,
        "feedback_type": "rating_positive",
        "user_rating_value": 5,
        "received_timestamp": now, # Provide datetime object
        "processing_status": "pending"
    }
    fb_event = FeedbackEventModel(**event_data)

    # Serialize to JSON
    json_data = fb_event.model_dump_json()

    # Deserialize back to model
    # Pydantic V2 uses parse_raw for this
    deserialized_fb_event = FeedbackEventModel.model_validate_json(json_data) # Pydantic V2

    assert deserialized_fb_event.feedback_event_id == original_event_id
    assert deserialized_fb_event.persona_id == original_persona_id
    assert deserialized_fb_event.received_timestamp.replace(microsecond=0) == now.replace(microsecond=0) # Compare without microseconds for safety
    assert deserialized_fb_event.processing_status == "pending"
    assert fb_event.model_dump()['received_timestamp'] == now.isoformat() # Check custom encoder output
    assert json_data.count(now.isoformat().replace('+00:00', 'Z')) # Ensure ISO format in JSON (Z for UTC)
    assert json_data.count(str(original_event_id))

# Example for BehavioralRule with datetime
def test_behavioral_rule_serialization():
    rule = BehavioralRule(
        description="Test rule",
        condition_script="true",
        action_to_take="log_message",
        created_at=datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        updated_at=datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    )
    json_data = rule.model_dump_json()
    assert "2023-01-01T12:00:00Z" in json_data # Check ISO format with Z for UTC

    deserialized_rule = BehavioralRule.model_validate_json(json_data)
    assert deserialized_rule.created_at == rule.created_at
    assert deserialized_rule.updated_at == rule.updated_at

# Example for PersonaBehavioralModel with nested models and datetimes
def test_persona_behavioral_model_serialization():
    persona_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    model = PersonaBehavioralModel(
        persona_id=persona_id,
        created_at=now,
        last_updated_at=now,
        style_parameters=[StyleParameter(parameter_name="Test", value=1, updated_at=now)]
    )
    json_data = model.model_dump_json()
    assert str(persona_id) in json_data
    # Check for datetime ISO format, potentially with 'Z' if no microseconds or specific formatting is applied by Pydantic's default.
    # Pydantic's default for datetimes in JSON is .isoformat().
    # If timezone is UTC, it might end with +00:00 or Z depending on Pydantic version and settings.
    # Our custom encoder ensures isoformat.
    assert now.isoformat().replace('+00:00', 'Z') in json_data # Check if Z is used for UTC

    deserialized_model = PersonaBehavioralModel.model_validate_json(json_data)
    assert deserialized_model.persona_id == persona_id
    assert deserialized_model.created_at.replace(microsecond=0) == now.replace(microsecond=0)
    assert deserialized_model.style_parameters[0].updated_at.replace(microsecond=0) == now.replace(microsecond=0)

# Test HttpUrl validation again for SandboxInstanceDetails
def test_sandbox_instance_details_url_validation():
    with pytest.raises(ValidationError):
        SandboxInstanceDetails(
            sandbox_id=uuid.uuid4(),
            persona_id=uuid.uuid4(),
            behavioral_model_version_id=uuid.uuid4(),
            status="provisioning",
            access_endpoint="not a valid url"
        )

    # Valid URL
    details = SandboxInstanceDetails(
        sandbox_id=uuid.uuid4(),
        persona_id=uuid.uuid4(),
        behavioral_model_version_id=uuid.uuid4(),
        status="provisioning",
        access_endpoint="http://example.com/sandbox"
    )
    assert isinstance(details.access_endpoint, HttpUrl)

# Test SandboxRequest min_length for test_scenarios
def test_sandbox_request_test_scenarios_min_length():
    with pytest.raises(ValidationError) as exc_info:
        SandboxRequest(
            persona_id=uuid.uuid4(),
            behavioral_model_version_id=uuid.uuid4(),
            test_scenarios=[] # Empty list
        )
    # Pydantic V2 error messages are more structured
    assert any(err['type'] == 'too_short' and err['loc'] == ('test_scenarios',) for err in exc_info.value.errors())

    # Should pass with one item
    SandboxRequest(
        persona_id=uuid.uuid4(),
        behavioral_model_version_id=uuid.uuid4(),
        test_scenarios=[{"prompt": "Hi"}]
    )
