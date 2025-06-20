# echosystem/ptfi/models.py
from pydantic import BaseModel, Field, field_validator, validator
from typing import List, Optional, Dict, Any, Literal
import uuid
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)

class EvidenceSnippet(BaseModel):
    type: str = Field(..., description="Type of evidence, e.g., 'text_snippet_from_analysis', 'direct_text_quote', 'user_provided_example'")
    content: Optional[str] = Field(default=None, description="Actual text snippet or description of non-text evidence")
    sourcePackageID: uuid.UUID = Field(..., description="References UserDataPackage.packageID from which this evidence originates or is related to")
    sourceDetail: Optional[str] = Field(default=None, description="Specifics about the source, e.g., 'document_xyz.txt, line 52', 'Derived from model X', 'audio_timestamp_10.5-12.3s'")
    relevance_score: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="Optional score of how relevant this snippet is to the trait")

    class Config:
        model_config = {
            "json_encoders": {uuid.UUID: str},
            "populate_by_name": True
        }

UserDecisionEnum = Literal[
    'confirmed_asis',
    'confirmed_modified',
    'rejected',
    'user_added_confirmed',
    'superseded'
]

TraitCategoryEnum = Literal[
    'LinguisticStyle', 'EmotionalResponsePattern', 'KnowledgeDomain',
    'PhilosophicalStance', 'CommunicationStyle', 'BehavioralPattern',
    'Interest', 'Skill', 'Other'
]

class UserRefinedTraitActionModel(BaseModel):
    refinementActionID: uuid.UUID = Field(default_factory=uuid.uuid4, description="Unique ID for this specific refinement action/event.")
    userID: uuid.UUID = Field(..., description="Identifier of the user performing the refinement.")
    traitID_in_pkg: uuid.UUID = Field(..., description="The ID of the corresponding Trait node in the Persona Knowledge Graph.")
    originalCandidateID: Optional[uuid.UUID] = Field(default=None, description="If this action pertains to an AI-suggested ExtractedTraitCandidate, this links to it. Null if user-defined.")
    userDecision: UserDecisionEnum = Field(..., description="The user's final decision on this trait action.")
    refinedTraitName: Optional[str] = Field(default=None, max_length=255, description="User-modified name for the trait. For 'user_added', this is the name.")
    refinedTraitDescription: Optional[str] = Field(default=None, description="User's own description or modification. For 'user_added', this is the description.")
    refinedTraitCategory: Optional[TraitCategoryEnum] = Field(default=None, description="User-modified category. For 'user_added', this is the chosen category.")
    userConfidenceRating: Optional[int] = Field(default=None, ge=1, le=5, description="User's subjective confidence (1-5 scale).")
    customizationNotes: Optional[str] = Field(default=None, description="Qualitative feedback or rationale from the user.")
    linkedEvidenceOverride: Optional[List[EvidenceSnippet]] = Field(default_factory=list, description="User-validated, invalidated, or newly added evidence snippets.")
    actionTimestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Timestamp of when this refinement action was recorded.")

    @field_validator('refinedTraitName', 'refinedTraitDescription', 'refinedTraitCategory', 'userConfidenceRating', 'customizationNotes', 'linkedEvidenceOverride', mode='before')
    @classmethod
    def ensure_none_if_empty_string(cls, value: Any, info) -> Optional[Any]:
        if isinstance(value, str) and not value.strip() and info.field_name in [
            'refinedTraitName', 'refinedTraitDescription',
            # 'refinedTraitCategory', # Category should not be empty string if provided
            'customizationNotes'
        ]: # Removed refinedTraitCategory as it should be from ENUM or None
            return None
        return value

    class Config:
        model_config = {
             "json_encoders": {uuid.UUID: str, datetime: lambda dt: dt.isoformat()}
         }

class TraitCandidateDisplayModel(BaseModel):
    candidateID: uuid.UUID = Field(..., alias="candidate_id")
    userID: uuid.UUID = Field(..., alias="user_id")
    traitName: str = Field(..., alias="trait_name")
    traitDescription: str = Field(..., alias="trait_description")
    traitCategory: str = Field(..., alias="trait_category")
    supportingEvidenceSnippets: List[EvidenceSnippet] = Field(default_factory=list, alias="supporting_evidence_snippets")
    confidenceScore: float = Field(..., alias="confidence_score")
    originatingModels: List[str] = Field(default_factory=list, alias="originating_models")
    status: str
    creationTimestamp: datetime = Field(..., alias="creation_timestamp")
    lastUpdatedTimestamp: datetime = Field(..., alias="last_updated_timestamp")

    class Config:
        populate_by_name = True
        json_encoders = {
            uuid.UUID: str,
            datetime: lambda dt: dt.isoformat()
        }
        # Pydantic v2 model_config
        # model_config = {
        #     "populate_by_name": True,
        #     "json_encoders": { uuid.UUID: str, datetime: lambda dt: dt.isoformat() }
        # }

class PaginatedTraitCandidateResponseModel(BaseModel):
    data: List[TraitCandidateDisplayModel]
    total: int
    page: int
    limit: int

class TraitModifications(BaseModel):
    refinedTraitName: Optional[str] = Field(default=None, min_length=3, max_length=255)
    refinedTraitDescription: Optional[str] = Field(default=None)
    refinedTraitCategory: Optional[TraitCategoryEnum] = Field(default=None)
    userConfidenceRating: Optional[int] = Field(default=None, ge=1, le=5)
    customizationNotes: Optional[str] = Field(default=None)

class TraitActionRequestModel(BaseModel):
    userDecision: Literal['confirmed_asis', 'confirmed_modified', 'rejected']
    modifications: Optional[TraitModifications] = None
    rejectionReason: Optional[str] = Field(default=None, max_length=1000)

    @field_validator('modifications', mode='before')
    @classmethod
    def check_modifications_for_action(cls, v: Optional[Dict[str, Any]], info) -> Optional[Dict[str, Any]]:
        action = info.data.get('userDecision')
        if action == 'confirmed_modified' and v is None:
            raise ValueError("modifications (refinedTraitName, etc.) are required when userDecision is 'confirmed_modified'")
        if action != 'confirmed_modified' and v is not None:
            logger.warning(f"Modifications provided for userDecision '{action}', but will only be applied if action is 'confirmed_modified'.")
        return v

class UpdatedTraitDetailsDisplay(BaseModel):
    traitID_in_pkg: uuid.UUID
    name: str
    description: Optional[str] = None
    category: TraitCategoryEnum
    status_in_pkg: str
    origin: Optional[str] = None
    userConfidence: Optional[int] = Field(default=None, ge=1, le=5)
    lastRefinedTimestamp: datetime

    class Config:
        model_config = {
            "json_encoders": { uuid.UUID: str, datetime: lambda dt: dt.isoformat() }
        }

class TraitActionResponseModel(BaseModel):
    message: str
    refinementActionID: uuid.UUID
    updatedTraitCandidateStatus: Optional[str] = None
    updatedTraitInPKG: Optional[UpdatedTraitDetailsDisplay] = None

    class Config:
        model_config = {
            "json_encoders": { uuid.UUID: str }
        }

# --- Models for Custom Trait Endpoint ---

class CustomTraitRequestModel(BaseModel):
    traitName: str = Field(..., min_length=3, max_length=255, description="Name for the new custom trait.")
    traitDescription: Optional[str] = Field(default=None, description="User's description of this trait.")
    traitCategory: TraitCategoryEnum = Field(..., description="Category for the new custom trait.")
    userConfidenceRating: Optional[int] = Field(default=None, ge=1, le=5, description="User's confidence in this trait (1-5 scale).")
    customizationNotes: Optional[str] = Field(default=None, description="Any additional notes from the user about this trait.")
    # For Phase 1, user-provided evidence for custom traits will be simple text strings.
    # These can be stored as `EvidenceSnippet` with type 'user_provided_text'.
    supportingEvidence_userText: Optional[List[str]] = Field(default_factory=list, description="Simple text snippets provided by user as evidence for this custom trait.")

class CustomTraitResponseModel(BaseModel):
    message: str
    newTrait: UpdatedTraitDetailsDisplay # Reuse the model for displaying trait details from PKG
    refinementActionID: uuid.UUID # From UserRefinedTraitActionModel log that records this 'user_added_confirmed' action

    class Config:
        model_config = {
            "json_encoders": {uuid.UUID: str}
        }
```
