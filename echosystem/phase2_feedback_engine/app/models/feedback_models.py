# echosystem/phase2_feedback_engine/app/models/feedback_models.py
from pydantic import BaseModel, Field, validator
from typing import Optional, Dict, Any, List, Literal # Added List
import uuid
from datetime import datetime, timezone

class FeedbackInput(BaseModel):
    persona_id: uuid.UUID
    interaction_id: uuid.UUID
    output_id: Optional[uuid.UUID] = None
    feedback_type: Literal[
        "rating_positive", "rating_negative", "correction_text",
        "style_too_formal", "style_too_casual", "style_tone_off",
        "factual_error", "custom_feedback"
    ]
    user_provided_text: Optional[str] = Field(None, description="Corrected text, or detailed custom feedback.")
    user_rating_value: Optional[int] = Field(None, ge=1, le=5, description="Optional 1-5 star rating.")
    feedback_context: Optional[Dict[str, Any]] = Field(None, description="Additional context.")

    @validator('user_provided_text', always=True)
    def check_text_for_correction(cls, v, values):
        # Ensure 'feedback_type' is present in values before accessing
        if 'feedback_type' in values and values.get('feedback_type') == 'correction_text' and not v:
            raise ValueError('user_provided_text is required for feedback_type "correction_text"')
        return v

class FeedbackResponse(BaseModel):
    feedback_event_id: uuid.UUID
    message: str
    received_feedback: FeedbackInput

    # Pydantic V2 uses model_config. Assuming this is intended for V2.
    model_config = {
        "json_encoders": {
            uuid.UUID: str
        }
    }

class FeedbackEventModel(FeedbackInput): # Inherits from FeedbackInput
    feedback_event_id: uuid.UUID # This was in the SQS payload, now part of the stored model
    received_timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    processing_status: Literal["pending", "processed", "error"] = "pending"
    processed_timestamp: Optional[datetime] = None # Added as per DDL
    error_message: Optional[str] = None

    # Pydantic V2 model_config for proper datetime and UUID serialization
    model_config = {
        "json_encoders": {
            uuid.UUID: str,
            datetime: lambda dt: dt.isoformat()
        },
        "populate_by_name": True, # Allows using field names or alias
        "arbitrary_types_allowed": True # If any complex types were used not directly supported
    }
