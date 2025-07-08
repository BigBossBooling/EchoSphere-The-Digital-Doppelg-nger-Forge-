from enum import Enum
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Dict, List, Optional

from .data_attribute import DataCategory, Purpose # Relative import

class ConsentStatus(Enum):
    GRANTED = "Granted"
    DENIED = "Denied"
    REVOKED = "Revoked"
    PENDING = "Pending"
    EXPIRED = "Expired"

    def to_dict(self):
        return self.value

    @classmethod
    def from_dict(cls, value: str):
        for member in cls:
            if member.value == value:
                return member
        raise ValueError(f"Invalid ConsentStatus value: {value}")

@dataclass
class ConsentRecord:
    data_category: DataCategory
    purpose: Purpose
    status: ConsentStatus
    timestamp: datetime # UTC timestamp of when this consent status was set
    details: Optional[str] = None # Optional details, e.g., for denial or revocation

    def to_dict(self) -> dict:
        return {
            "data_category": self.data_category.to_dict(),
            "purpose": self.purpose.to_dict(),
            "status": self.status.to_dict(),
            "timestamp": self.timestamp.isoformat(),
            "details": self.details
        }

    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            data_category=DataCategory.from_dict(data["data_category"]),
            purpose=Purpose.from_dict(data["purpose"]),
            status=ConsentStatus.from_dict(data["status"]),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            details=data.get("details")
        )

@dataclass
class UserConsent:
    user_id: str
    persona_id: str # Identifies the doppelganger persona this consent applies to
    consent_records: Dict[str, ConsentRecord] = field(default_factory=dict) # Key: f"{data_category.value}_{purpose.value}"
    version: int = 1
    last_updated: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def _make_key(self, data_category: DataCategory, purpose: Purpose) -> str:
        return f"{data_category.value}_{purpose.value}"

    def grant(self, data_category: DataCategory, purpose: Purpose, details: Optional[str] = None):
        key = self._make_key(data_category, purpose)
        self.consent_records[key] = ConsentRecord(
            data_category=data_category,
            purpose=purpose,
            status=ConsentStatus.GRANTED,
            timestamp=datetime.now(timezone.utc),
            details=details
        )
        self.last_updated = datetime.now(timezone.utc)
        self.version += 1

    def deny(self, data_category: DataCategory, purpose: Purpose, details: Optional[str] = None):
        key = self._make_key(data_category, purpose)
        self.consent_records[key] = ConsentRecord(
            data_category=data_category,
            purpose=purpose,
            status=ConsentStatus.DENIED,
            timestamp=datetime.now(timezone.utc),
            details=details
        )
        self.last_updated = datetime.now(timezone.utc)
        self.version += 1

    def revoke(self, data_category: DataCategory, purpose: Purpose, details: Optional[str] = None):
        key = self._make_key(data_category, purpose)
        if key in self.consent_records:
            self.consent_records[key].status = ConsentStatus.REVOKED
            self.consent_records[key].timestamp = datetime.now(timezone.utc)
            self.consent_records[key].details = details
            self.last_updated = datetime.now(timezone.utc)
            self.version +=1
        else:
            # Or raise error, or log warning
            print(f"Warning: Attempting to revoke consent for non-existent record: {key}")


    def get_consent_status(self, data_category: DataCategory, purpose: Purpose) -> Optional[ConsentStatus]:
        key = self._make_key(data_category, purpose)
        record = self.consent_records.get(key)
        return record.status if record else None

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "persona_id": self.persona_id,
            "consent_records": {k: v.to_dict() for k, v in self.consent_records.items()},
            "version": self.version,
            "last_updated": self.last_updated.isoformat()
        }

    @classmethod
    def from_dict(cls, data: dict):
        consent = cls(
            user_id=data["user_id"],
            persona_id=data["persona_id"],
            version=data.get("version", 1),
            last_updated=datetime.fromisoformat(data.get("last_updated", datetime.now(timezone.utc).isoformat()))
        )
        consent.consent_records = {
            k: ConsentRecord.from_dict(v) for k, v in data.get("consent_records", {}).items()
        }
        return consent

# Example Usage:
if __name__ == "__main__":
    user_consent = UserConsent(user_id="user123", persona_id="doppelganger_of_user123")

    user_consent.grant(DataCategory.COMMUNICATION_CONTENT, Purpose.PERSONA_CREATION, "Granted for initial model training")
    user_consent.grant(DataCategory.VOICE_RECORDINGS, Purpose.VOICE_CLONING)
    user_consent.deny(DataCategory.SOCIAL_MEDIA_POSTS, Purpose.PERSONA_CREATION, "User prefers not to use social media.")

    print(f"UserConsent object: {user_consent}")

    consent_dict = user_consent.to_dict()
    print(f"\nto_dict(): {consent_dict}")

    rehydrated_consent = UserConsent.from_dict(consent_dict)
    print(f"\nfrom_dict(): {rehydrated_consent}")

    assert user_consent.user_id == rehydrated_consent.user_id
    assert user_consent.version == rehydrated_consent.version
    assert len(user_consent.consent_records) == len(rehydrated_consent.consent_records)

    key_comm_persona = user_consent._make_key(DataCategory.COMMUNICATION_CONTENT, Purpose.PERSONA_CREATION)
    assert user_consent.consent_records[key_comm_persona].status == ConsentStatus.GRANTED
    assert rehydrated_consent.consent_records[key_comm_persona].status == ConsentStatus.GRANTED
    assert rehydrated_consent.consent_records[key_comm_persona].details == "Granted for initial model training"

    user_consent.revoke(DataCategory.VOICE_RECORDINGS, Purpose.VOICE_CLONING, "User changed mind.")
    key_voice_cloning = user_consent._make_key(DataCategory.VOICE_RECORDINGS, Purpose.VOICE_CLONING)
    assert user_consent.consent_records[key_voice_cloning].status == ConsentStatus.REVOKED

    print(f"\nStatus for Voice Cloning after revoke: {user_consent.get_consent_status(DataCategory.VOICE_RECORDINGS, Purpose.VOICE_CLONING)}")

    # Test non-existent record
    print(f"Status for non-existent consent: {user_consent.get_consent_status(DataCategory.OTHER, Purpose.OTHER_SPECIFIED)}")

    print("\nAll assertions passed.")
