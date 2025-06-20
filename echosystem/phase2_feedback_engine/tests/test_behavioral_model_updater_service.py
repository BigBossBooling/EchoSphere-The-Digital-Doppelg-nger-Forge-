# echosystem/phase2_feedback_engine/tests/test_behavioral_model_updater_service.py
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
import uuid
from datetime import datetime, timezone

# Attempt to import modules based on common execution contexts for pytest
try:
    # Assumes pytest is run from a context where 'echosystem' is a top-level package
    from echosystem.phase2_feedback_engine.app.services import behavioral_model_updater_service
    from echosystem.phase2_feedback_engine.app.models.feedback_models import FeedbackEventModel
    from echosystem.phase2_feedback_engine.app.models.behavioral_model_models import PersonaBehavioralModel, StyleParameter, BehavioralRule
except ImportError:
    # Fallback if 'echosystem' is not directly in path, e.g., running pytest from phase2_feedback_engine directory
    # This requires 'app' to be discoverable.
    # Adding sys.path modification is generally discouraged in tests if project structure + PYTHONPATH is correct.
    # However, for this tool's execution, it might be necessary if the context isn't the project root.
    # For robust local testing, ensure PYTHONPATH or `python -m pytest` from root is used.
    # The prompt's original sys.path modification is kept here as a fallback for the tool's environment.
    try:
        from app.services import behavioral_model_updater_service
        from app.models.feedback_models import FeedbackEventModel
        from app.models.behavioral_model_models import PersonaBehavioralModel, StyleParameter, BehavioralRule
    except ImportError:
        import sys
        import os
        # This assumes the test file is in echosystem/phase2_feedback_engine/tests/
        # It adds the 'echosystem' directory to sys.path to allow imports like echosystem.module
        # This is a common pattern if tests are run from the specific test directory or if the project isn't installed.
        # For this tool, we'll assume this path adjustment might be needed.
        project_root_for_echosystem = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..'))
        if project_root_for_echosystem not in sys.path:
            sys.path.insert(0, project_root_for_echosystem)

        # Retry imports with adjusted path
        from echosystem.phase2_feedback_engine.app.services import behavioral_model_updater_service
        from echosystem.phase2_feedback_engine.app.models.feedback_models import FeedbackEventModel
        from echosystem.phase2_feedback_engine.app.models.behavioral_model_models import PersonaBehavioralModel, StyleParameter, BehavioralRule


@pytest.fixture
def sample_persona_id() -> uuid.UUID: # Added return type hint
    return uuid.uuid4()

@pytest.fixture
def sample_interaction_id() -> uuid.UUID: # Added return type hint
    return uuid.uuid4()

@pytest.fixture
def initial_behavioral_model(sample_persona_id: uuid.UUID) -> PersonaBehavioralModel: # Added type hint for arg
    return PersonaBehavioralModel(
        persona_id=sample_persona_id,
        model_version_id=uuid.uuid4(),
        style_parameters=[
            StyleParameter(parameter_name="FormalityLevel", value="neutral", source_of_truth="pkg_derived", updated_at=datetime.now(timezone.utc)),
            StyleParameter(parameter_name="HumorUsage", value="low", source_of_truth="pkg_derived", updated_at=datetime.now(timezone.utc))
        ],
        behavioral_rules=[],
        created_at=datetime.now(timezone.utc),
        last_updated_at=datetime.now(timezone.utc),
        is_active_model=True
    )

@pytest.mark.asyncio
async def test_apply_feedback_style_too_formal(initial_behavioral_model: PersonaBehavioralModel, sample_persona_id: uuid.UUID, sample_interaction_id: uuid.UUID):
    feedback_event = FeedbackEventModel(
        feedback_event_id=uuid.uuid4(),
        persona_id=sample_persona_id,
        interaction_id=sample_interaction_id,
        feedback_type="style_too_formal",
        user_provided_text=None, # Explicitly None for clarity
        user_rating_value=None, # Explicitly None
        feedback_context=None, # Explicitly None
        # Pydantic V2 will use default_factory for received_timestamp, processing_status
    )

    updated_model = await behavioral_model_updater_service.apply_feedback_to_behavioral_model(
        feedback_event, initial_behavioral_model
    )

    assert updated_model is not None, "Model should have been updated."
    assert updated_model.model_version_id != initial_behavioral_model.model_version_id, "Model version should change."
    formality_param = next((p for p in updated_model.style_parameters if p.parameter_name == "FormalityLevel"), None)
    assert formality_param is not None, "FormalityLevel parameter should exist."
    assert formality_param.value == "informal", "Formality should shift from neutral to informal."
    assert formality_param.source_of_truth == "feedback_refined", "Source of truth should be updated."
    assert formality_param.updated_at == updated_model.last_updated_at, "Timestamp should be updated."

@pytest.mark.asyncio
async def test_apply_feedback_style_too_casual(initial_behavioral_model: PersonaBehavioralModel, sample_persona_id: uuid.UUID, sample_interaction_id: uuid.UUID):
    # Set initial formality to 'informal' for this test case
    for p in initial_behavioral_model.style_parameters:
        if p.parameter_name == "FormalityLevel":
            p.value = "informal"
            break
    else: # Add if not present (though fixture should have it)
        initial_behavioral_model.style_parameters.append(
            StyleParameter(parameter_name="FormalityLevel", value="informal", source_of_truth="pkg_derived")
        )

    feedback_event = FeedbackEventModel(
        feedback_event_id=uuid.uuid4(),
        persona_id=sample_persona_id,
        interaction_id=sample_interaction_id,
        feedback_type="style_too_casual",
    )
    updated_model = await behavioral_model_updater_service.apply_feedback_to_behavioral_model(
        feedback_event, initial_behavioral_model
    )
    assert updated_model is not None
    formality_param = next((p for p in updated_model.style_parameters if p.parameter_name == "FormalityLevel"), None)
    assert formality_param is not None
    assert formality_param.value == "neutral" # informal -> neutral
    assert formality_param.source_of_truth == "feedback_refined"

@pytest.mark.asyncio
async def test_apply_feedback_correction_text_adds_conceptual_rule(initial_behavioral_model: PersonaBehavioralModel, sample_persona_id: uuid.UUID, sample_interaction_id: uuid.UUID):
    correction_text = "Actually, I prefer to say it this way."
    feedback_event = FeedbackEventModel(
        feedback_event_id=uuid.uuid4(),
        persona_id=sample_persona_id,
        interaction_id=sample_interaction_id,
        feedback_type="correction_text",
        user_provided_text=correction_text
    )
    updated_model = await behavioral_model_updater_service.apply_feedback_to_behavioral_model(
        feedback_event, initial_behavioral_model
    )
    assert updated_model is not None, "Model should be updated for correction_text."
    assert updated_model.model_version_id != initial_behavioral_model.model_version_id, "Version should change."

    # Check if a rule was added (as per current implementation of apply_feedback...)
    assert len(updated_model.behavioral_rules) > len(initial_behavioral_model.behavioral_rules), "A behavioral rule should have been added."
    new_rule = updated_model.behavioral_rules[-1] # Assuming it's appended
    assert new_rule.description.startswith("User correction for interaction similar to")
    assert f"'{correction_text[:100]}...'" in new_rule.action_to_take


@pytest.mark.asyncio
async def test_apply_feedback_no_change_for_unhandled_type(initial_behavioral_model: PersonaBehavioralModel, sample_persona_id: uuid.UUID, sample_interaction_id: uuid.UUID):
    feedback_event = FeedbackEventModel(
        feedback_event_id=uuid.uuid4(),
        persona_id=sample_persona_id,
        interaction_id=sample_interaction_id,
        feedback_type="rating_positive", # Assuming this type doesn't make direct model changes yet
    )
    updated_model = await behavioral_model_updater_service.apply_feedback_to_behavioral_model(
        feedback_event, initial_behavioral_model
    )
    assert updated_model is None, "No change expected for this feedback type yet, so model should be None."

@pytest.mark.asyncio
@patch(f"{behavioral_model_updater_service.__name__}.logger") # Patch logger within the service module
async def test_get_active_behavioral_model_placeholder(mock_logger: MagicMock, sample_persona_id: uuid.UUID):
    # Test the placeholder function (which now accepts a db_client=None)
    model = await behavioral_model_updater_service.get_active_behavioral_model(sample_persona_id, db_client=None)
    assert model is not None
    assert model.persona_id == sample_persona_id
    # Example: Check if the logger was called with the expected message
    # This requires the logger patch to be correctly targeting where the logger is used.
    # The f-string in the patch path ensures we're patching the logger instance in the *module under test*.
    mock_logger.info.assert_any_call(f"Placeholder: Fetching active behavioral model for persona_id: {sample_persona_id} using db_client: None")


@pytest.mark.asyncio
@patch(f"{behavioral_model_updater_service.__name__}.logger")
async def test_save_behavioral_model_placeholder(mock_logger: MagicMock, initial_behavioral_model: PersonaBehavioralModel):
    # Test the placeholder function
    result = await behavioral_model_updater_service.save_behavioral_model(initial_behavioral_model, db_client=None)
    assert result is True
    mock_logger.info.assert_any_call(f"Placeholder: Saving behavioral model version {initial_behavioral_model.model_version_id} for persona_id: {initial_behavioral_model.persona_id} using db_client: None")

@pytest.mark.asyncio
async def test_apply_feedback_formality_level_extreme_cases(initial_behavioral_model: PersonaBehavioralModel, sample_persona_id: uuid.UUID, sample_interaction_id: uuid.UUID):
    # Test "style_too_formal" when already at "very_informal"
    for p in initial_behavioral_model.style_parameters:
        if p.parameter_name == "FormalityLevel":
            p.value = "very_informal"
            break

    feedback_formal = FeedbackEventModel(feedback_event_id=uuid.uuid4(), persona_id=sample_persona_id, interaction_id=sample_interaction_id, feedback_type="style_too_formal")
    updated_model_formal = await behavioral_model_updater_service.apply_feedback_to_behavioral_model(feedback_formal, initial_behavioral_model)

    # Should not change if already at the lowest
    formality_param_formal = next((p for p in updated_model_formal.style_parameters if p.parameter_name == "FormalityLevel"), None)
    assert formality_param_formal.value == "very_informal"
    # The model version ID should not change if no actual change in value was made.
    # However, current implementation creates a new version ID if made_change is true,
    # and made_change is true if the parameter is found, even if value doesn't change from extreme.
    # This might be an area for refinement in the service itself.
    # For this test, we'll assert based on current service logic.
    assert updated_model_formal.model_version_id != initial_behavioral_model.model_version_id

    # Test "style_too_casual" when already at "very_formal"
    for p in initial_behavioral_model.style_parameters:
        if p.parameter_name == "FormalityLevel":
            p.value = "very_formal"
            break

    feedback_casual = FeedbackEventModel(feedback_event_id=uuid.uuid4(), persona_id=sample_persona_id, interaction_id=sample_interaction_id, feedback_type="style_too_casual")
    updated_model_casual = await behavioral_model_updater_service.apply_feedback_to_behavioral_model(feedback_casual, initial_behavioral_model)

    formality_param_casual = next((p for p in updated_model_casual.style_parameters if p.parameter_name == "FormalityLevel"), None)
    assert formality_param_casual.value == "very_formal"
    assert updated_model_casual.model_version_id != initial_behavioral_model.model_version_id


@pytest.mark.asyncio
async def test_apply_feedback_formality_level_param_missing(initial_behavioral_model: PersonaBehavioralModel, sample_persona_id: uuid.UUID, sample_interaction_id: uuid.UUID):
    # Remove FormalityLevel from initial model
    initial_behavioral_model.style_parameters = [p for p in initial_behavioral_model.style_parameters if p.parameter_name != "FormalityLevel"]

    feedback_event = FeedbackEventModel(feedback_event_id=uuid.uuid4(), persona_id=sample_persona_id, interaction_id=sample_interaction_id, feedback_type="style_too_formal")
    updated_model = await behavioral_model_updater_service.apply_feedback_to_behavioral_model(feedback_event, initial_behavioral_model)

    assert updated_model is not None
    formality_param = next((p for p in updated_model.style_parameters if p.parameter_name == "FormalityLevel"), None)
    assert formality_param is not None
    assert formality_param.value == "informal" # Default initialization when too formal
    assert formality_param.source_of_truth == "feedback_refined"

    initial_behavioral_model.style_parameters = [] # Reset for next case
    feedback_event_casual = FeedbackEventModel(feedback_event_id=uuid.uuid4(), persona_id=sample_persona_id, interaction_id=sample_interaction_id, feedback_type="style_too_casual")
    updated_model_casual = await behavioral_model_updater_service.apply_feedback_to_behavioral_model(feedback_event_casual, initial_behavioral_model)
    formality_param_casual = next((p for p in updated_model_casual.style_parameters if p.parameter_name == "FormalityLevel"), None)
    assert formality_param_casual is not None
    assert formality_param_casual.value == "formal" # Default initialization when too casual
    assert formality_param_casual.source_of_truth == "feedback_refined"
