# echosystem/maipp/models.py
from pydantic import BaseModel, Field # Field was already used by RawAnalysisFeatureSet
from typing import Dict, Any, List, Optional
import uuid
from datetime import datetime, timezone

class RawAnalysisFeatureSet(BaseModel):
    """
    Pydantic model for a set of raw analysis features from a single AI model run.
    This structure will be stored in MongoDB.
    """
    featureSetID: uuid.UUID = Field(default_factory=uuid.uuid4, alias="_id")
    userID: uuid.UUID
    sourceUserDataPackageID: uuid.UUID
    modality: str
    modelNameOrType: str
    extractedFeatures: Dict[str, Any]
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    processingTimeMs: Optional[int] = None
    status: str = "success"
    errorDetails: Optional[str] = None
    consentTokenID_used: Optional[uuid.UUID] = None
    required_scope_for_consent: Optional[str] = None

    class Config:
        populate_by_name = True
        json_encoders = {
            uuid.UUID: lambda u: str(u),
            datetime: lambda dt: dt.isoformat()
        }

class EvidenceSnippet(BaseModel):
    type: str # e.g., 'text_snippet_from_analysis', 'direct_text_quote', 'audio_segment_ref', 'image_ref'
    content: Optional[str] = None # Actual text snippet or description of non-text evidence
    sourcePackageID: uuid.UUID # References UserDataPackage.packageID
    sourceDetail: Optional[str] = None # e.g., "document_xyz.txt, line 52" or "Derived from model: Gemini_Topic_Extraction on featureset_abc" or "audio_timestamp_10.5-12.3s"
    relevance_score: Optional[float] = Field(default=None, ge=0.0, le=1.0) # Optional score of how relevant this snippet is to the trait

class ExtractedTraitCandidateModel(BaseModel):
    candidateID: uuid.UUID = Field(default_factory=uuid.uuid4)
    userID: uuid.UUID
    traitName: str = Field(..., min_length=3, max_length=255)
    traitDescription: str = Field(..., min_length=10) # Require some description
    traitCategory: str # TODO: Define as ENUM later using Literal from typing for stricter validation
                       # Example ENUMs: 'LinguisticStyle', 'EmotionalResponsePattern', 'KnowledgeDomain',
                       # 'PhilosophicalStance', 'CommunicationStyle', 'BehavioralPattern', 'Interest', 'Skill', 'Other'
    supportingEvidenceSnippets: List[EvidenceSnippet] = Field(default_factory=list)
    confidenceScore: float = Field(ge=0.0, le=1.0) # Overall confidence from MAIPP's derivation logic
    originatingModels: List[str] = Field(default_factory=list) # List of modelNameOrType from RawAnalysisFeatures
    associatedFeatureSetIDs: List[uuid.UUID] = Field(default_factory=list) # List of featureSetIDs
    status: str = "candidate" # Default status. Others: 'awaiting_refinement', 'confirmed_by_user', etc.
    creationTimestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    lastUpdatedTimestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Example validator for traitCategory if we had a predefined list
    # @validator('traitCategory')
    # def trait_category_must_be_in_defined_set(cls, value):
    #     defined_categories = {'LinguisticStyle', 'EmotionalResponsePattern', ...}
    #     if value not in defined_categories:
    #         raise ValueError(f"traitCategory must be one of {defined_categories}")
    #     return value

    class Config:
         json_encoders = { # Ensure UUIDs and datetimes are JSON serializable easily
            uuid.UUID: str,
            datetime: lambda dt: dt.isoformat()
        }
```
