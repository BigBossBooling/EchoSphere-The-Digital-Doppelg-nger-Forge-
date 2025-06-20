# echosystem/phase1/core_trait_definition/trait_refinement_data_structures.py
import uuid
from typing import Optional, List, Dict, Any

# Attempt to import base trait structure for reference, if needed
try:
    from echosystem.phase1.ai_persona_analysis.analysis_data_structures import ExtractedTraitCandidate
except ImportError:
    print("Warning: UserRefinedTrait could not import ExtractedTraitCandidate. Defining a placeholder if needed.")
    # Define a placeholder if it's critical for inheritance or type hinting and import fails
    class ExtractedTraitCandidate:
        def __init__(self, trait_id:str, trait_name:str, trait_category:str):
            self.trait_id = trait_id
            self.trait_name = trait_name
            self.trait_category = trait_category


class UserRefinedTrait:
    """
    Represents a trait after user review and refinement.
    This structure captures the user's final decision and any modifications
    to an AI-suggested trait, or a completely new trait defined by the user.
    """
    def __init__(self,
                 user_id: str,
                 trait_id: str, # Original AI trait ID if applicable, or new ID for user-defined
                 trait_name: str,
                 trait_category: str,
                 user_decision: str, # 'confirmed', 'rejected', 'modified', 'user_added'
                 user_description: Optional[str] = None, # User's own description or modification
                 user_confidence: Optional[float] = None, # How strongly user feels this represents them (1-5 scale or similar)
                 linked_evidence_override: Optional[List[str]] = None, # If user changes/validates specific evidence
                 origin_ai_trait_id: Optional[str] = None, # If this refines an AI trait, its original ID
                 ai_confidence_score: Optional[float] = None # Original AI confidence, for reference
                 ):

        if not all([user_id, trait_id, trait_name, trait_category, user_decision]):
            raise ValueError("Core fields for UserRefinedTrait must be provided.")

        valid_decisions = ['confirmed', 'rejected', 'modified', 'user_added']
        if user_decision not in valid_decisions:
            raise ValueError(f"Invalid user_decision. Must be one of {valid_decisions}")

        self.refined_trait_id: str = str(uuid.uuid4()) # Unique ID for this refinement action/version
        self.trait_id: str = trait_id # The ID of the trait in the PKG
        self.user_id: str = user_id

        self.trait_name: str = trait_name # Can be modified by user
        self.trait_category: str = trait_category # Can be modified by user
        self.user_decision: str = user_decision
        self.user_description: Optional[str] = user_description # User's own words
        self.user_confidence: Optional[float] = user_confidence

        self.linked_evidence_override: Optional[List[str]] = linked_evidence_override
        self.origin_ai_trait_id: Optional[str] = origin_ai_trait_id
        self.ai_confidence_score: Optional[float] = ai_confidence_score # For context if it was an AI trait

        self.timestamp: str = self._get_current_timestamp()

    def _get_current_timestamp(self) -> str:
        import datetime
        return datetime.datetime.now().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        """Serializes the object to a dictionary."""
        return {
            "refined_trait_id": self.refined_trait_id,
            "trait_id": self.trait_id,
            "user_id": self.user_id,
            "trait_name": self.trait_name,
            "trait_category": self.trait_category,
            "user_decision": self.user_decision,
            "user_description": self.user_description,
            "user_confidence": self.user_confidence,
            "linked_evidence_override": self.linked_evidence_override,
            "origin_ai_trait_id": self.origin_ai_trait_id,
            "ai_confidence_score": self.ai_confidence_score,
            "timestamp": self.timestamp,
        }

    def __repr__(self) -> str:
        return (f"UserRefinedTrait(id={self.refined_trait_id}, name='{self.trait_name}', "
                f"decision='{self.user_decision}', user='{self.user_id}')")

# Example Usage
if __name__ == '__main__':
    try:
        # Example 1: User confirms an AI trait
        confirmed_trait = UserRefinedTrait(
            user_id="user123",
            trait_id="ai_trait_abc", # ID of the trait in PKG (originally from ExtractedTraitCandidate)
            trait_name="Detail-Oriented (AI)", # Name might be kept or slightly adjusted
            trait_category="Cognitive Style",
            user_decision="confirmed",
            user_description="Yes, I agree with this assessment by the AI.",
            user_confidence=5.0, # e.g., on a 1-5 scale
            origin_ai_trait_id="ai_trait_abc",
            ai_confidence_score=0.88
        )
        print(confirmed_trait)
        print(confirmed_trait.to_dict())

        # Example 2: User modifies an AI trait
        modified_trait = UserRefinedTrait(
            user_id="user123",
            trait_id="ai_trait_def",
            trait_name="Creative Thinker", # User changed name from "Unconventional (AI)"
            trait_category="Cognitive Style",
            user_decision="modified",
            user_description="I see it more as creative thinking rather than just unconventional.",
            user_confidence=4.5,
            origin_ai_trait_id="ai_trait_def",
            ai_confidence_score=0.75
        )
        print(modified_trait)

        # Example 3: User rejects an AI trait
        rejected_trait = UserRefinedTrait(
            user_id="user123",
            trait_id="ai_trait_ghi",
            trait_name="Reserved (AI)", # Original name
            trait_category="Interpersonal Style",
            user_decision="rejected",
            user_description="I don't think this is accurate at all.",
            origin_ai_trait_id="ai_trait_ghi",
            ai_confidence_score=0.60
        )
        print(rejected_trait)

        # Example 4: User adds a completely new trait
        user_added_trait = UserRefinedTrait(
            user_id="user123",
            trait_id=str(uuid.uuid4()), # New ID for this user-defined trait in PKG
            trait_name="Passionate about History",
            trait_category="Interests",
            user_decision="user_added",
            user_description="I spend a lot of my free time reading history books and visiting museums.",
            user_confidence=5.0
        )
        print(user_added_trait)

    except ValueError as e:
        print(f"Error creating UserRefinedTrait: {e}")
```
