from enum import Enum
from dataclasses import dataclass, asdict, fields

class DataCategory(Enum):
    PERSONAL_IDENTIFIABLE_INFORMATION = "PII"
    COMMUNICATION_CONTENT = "Communication Content" # Emails, chat logs
    BEHAVIORAL_PATTERNS = "Behavioral Patterns" # How user interacts, response times
    USAGE_METADATA = "Usage Metadata" # Timestamps, frequencies of interaction
    VOICE_RECORDINGS = "Voice Recordings"
    WRITTEN_DOCUMENTS = "Written Documents"
    SOCIAL_MEDIA_POSTS = "Social Media Posts"
    USER_PREFERENCES = "User Preferences" # Explicitly set preferences
    SYSTEM_INTERACTIONS = "System Interactions" # How user uses Doppelganger itself
    ANONYMIZED_DATA = "Anonymized Data"
    OTHER = "Other"

    def to_dict(self):
        return self.value

    @classmethod
    def from_dict(cls, value: str):
        for member in cls:
            if member.value == value:
                return member
        raise ValueError(f"Invalid DataCategory value: {value}")

class Purpose(Enum):
    PERSONA_CREATION = "Persona Creation" # Core model training
    PERSONA_ADAPTATION = "Persona Adaptation" # Ongoing learning/refinement
    VOICE_CLONING = "Voice Cloning"
    INTERACTION_PERSONALIZATION = "Interaction Personalization"
    ANALYTICS_AND_IMPROVEMENT = "Analytics and System Improvement"
    SECURITY_AND_MONITORING = "Security and System Monitoring"
    RESEARCH_CONSENTED = "Research (Consented)"
    OTHER_SPECIFIED = "Other (Specified)"

    def to_dict(self):
        return self.value

    @classmethod
    def from_dict(cls, value: str):
        for member in cls:
            if member.value == value:
                return member
        raise ValueError(f"Invalid Purpose value: {value}")

@dataclass
class DataAttribute:
    name: str
    category: DataCategory
    description: str
    sensitivity_level: int # e.g., 1 (low) to 5 (high)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "category": self.category.to_dict(),
            "description": self.description,
            "sensitivity_level": self.sensitivity_level,
        }

    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            name=data["name"],
            category=DataCategory.from_dict(data["category"]),
            description=data["description"],
            sensitivity_level=data["sensitivity_level"],
        )

# Example Usage:
if __name__ == "__main__":
    email_attr = DataAttribute(
        name="EmailAddress",
        category=DataCategory.PERSONAL_IDENTIFIABLE_INFORMATION,
        description="User's email address.",
        sensitivity_level=5
    )
    print(f"DataAttribute: {email_attr}")
    email_dict = email_attr.to_dict()
    print(f"to_dict(): {email_dict}")
    email_from_dict = DataAttribute.from_dict(email_dict)
    print(f"from_dict(): {email_from_dict}")
    assert email_attr == email_from_dict

    print(f"Purpose Enum (Persona Creation): {Purpose.PERSONA_CREATION.to_dict()}")
    purpose_from_val = Purpose.from_dict("Persona Creation")
    print(f"Purpose Enum from_dict: {purpose_from_val}")
    assert purpose_from_val == Purpose.PERSONA_CREATION
