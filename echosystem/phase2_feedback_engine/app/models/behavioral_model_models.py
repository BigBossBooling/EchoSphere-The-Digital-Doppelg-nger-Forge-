# echosystem/phase2_feedback_engine/app/models/behavioral_model_models.py
from pydantic import BaseModel, Field, HttpUrl
from typing import Optional, Dict, Any, List, Literal
import uuid
from datetime import datetime, timezone

class ModelFileReference(BaseModel):
    storage_type: Literal["S3", "URL", "LocalPath"] # LocalPath for dev/testing only
    path_uri: str # e.g., S3 URI (s3://bucket/path/to/model.tar.gz) or HTTP URL
    version_id: Optional[str] = None # e.g., S3 object version ID
    checksum_sha256: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None # e.g., base model used for fine-tuning, creation date

class BehavioralRule(BaseModel):
    rule_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    description: str
    # Example condition: "if user_sentiment == 'negative' and topic == 'customer_service'"
    # Example action: "prepend_response('I understand you are frustrated, but...')"
    # For more complex logic, this might point to a script or a pre-defined function ID.
    condition_script: str
    action_to_take: str # Could be a simple string, or JSON representing a structured action
    priority: int = 0 # Higher priority rules are evaluated first
    is_active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    # Optional: versioning for rules themselves, or link to feedback that prompted the rule

class StyleParameter(BaseModel):
    parameter_name: str # e.g., "FormalityLevel", "HumorIntensity", "ResponseLengthConstraint"
    # Value could be simple (float, int, str) or complex (dict for ranges, lists for options)
    value: Any
    # source_of_truth helps track how this parameter was set (e.g., derived from PKG, refined by feedback, direct user override)
    source_of_truth: Optional[str] = "pkg_derived"
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    # Optional: metadata like confidence score, applicable contexts (e.g., only for 'professional_mode')

class PersonaBehavioralModel(BaseModel):
    persona_id: uuid.UUID # Links to the Echo persona (PK of the persona)
    model_version_id: uuid.UUID = Field(default_factory=uuid.uuid4) # Version of this *set* of behavioral configurations

    primary_llm_reference: Optional[ModelFileReference] = None # Reference to a fine-tuned LLM or foundational model

    behavioral_rules: List[BehavioralRule] = Field(default_factory=list)
    style_parameters: List[StyleParameter] = Field(default_factory=list)

    # Example of other potential components:
    # knowledge_embedding_reference: Optional[ModelFileReference] = None
    # voice_model_reference: Optional[ModelFileReference] = None
    # specific_prompt_templates: Dict[str, str] = Field(default_factory=dict) # e.g., {"greeting_prompt": "Hello, I am..."}

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    is_active_model: bool = False # Indicates if this version is the currently active one for the persona

    # Pydantic V2 model_config for proper datetime and UUID serialization
    model_config = {
        "json_encoders": {
            uuid.UUID: str,
            datetime: lambda dt: dt.isoformat()
        },
        "populate_by_name": True,
        "arbitrary_types_allowed": True
    }
