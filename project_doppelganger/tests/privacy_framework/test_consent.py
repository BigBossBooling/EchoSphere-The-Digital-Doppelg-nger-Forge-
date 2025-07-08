import unittest
from datetime import datetime, timezone
from project_doppelganger.src.privacy_framework.consent import UserConsent, ConsentStatus, ConsentRecord
from project_doppelganger.src.privacy_framework.data_attribute import DataCategory, Purpose

class TestConsent(unittest.TestCase):

    def test_consent_status_serialization(self):
        status = ConsentStatus.GRANTED
        self.assertEqual(status.to_dict(), "Granted")
        self.assertEqual(ConsentStatus.from_dict("Granted"), status)
        with self.assertRaises(ValueError):
            ConsentStatus.from_dict("Invalid Status")

    def test_consent_record_serialization(self):
        ts = datetime.now(timezone.utc)
        record = ConsentRecord(
            data_category=DataCategory.VOICE_RECORDINGS,
            purpose=Purpose.VOICE_CLONING,
            status=ConsentStatus.GRANTED,
            timestamp=ts,
            details="User agreed on setup"
        )
        record_dict = record.to_dict()
        expected_dict = {
            "data_category": "Voice Recordings",
            "purpose": "Voice Cloning",
            "status": "Granted",
            "timestamp": ts.isoformat(),
            "details": "User agreed on setup"
        }
        self.assertEqual(record_dict, expected_dict)

        record_from_dict = ConsentRecord.from_dict(expected_dict)
        self.assertEqual(record_from_dict, record)

        # Test with optional fields being None
        record_no_details = ConsentRecord(
            data_category=DataCategory.VOICE_RECORDINGS,
            purpose=Purpose.VOICE_CLONING,
            status=ConsentStatus.GRANTED,
            timestamp=ts
        )
        record_no_details_dict = record_no_details.to_dict()
        self.assertIsNone(record_no_details_dict["details"])
        record_no_details_from_dict = ConsentRecord.from_dict(record_no_details_dict)
        self.assertEqual(record_no_details_from_dict, record_no_details)


    def test_user_consent_initialization(self):
        uc = UserConsent(user_id="u1", persona_id="p1")
        self.assertEqual(uc.user_id, "u1")
        self.assertEqual(uc.persona_id, "p1")
        self.assertEqual(uc.consent_records, {})
        self.assertEqual(uc.version, 1)
        self.assertIsNotNone(uc.last_updated)

    def test_user_consent_grant_deny_revoke(self):
        uc = UserConsent(user_id="u1", persona_id="p1")

        # Grant
        uc.grant(DataCategory.COMMUNICATION_CONTENT, Purpose.PERSONA_CREATION, "Initial grant")
        self.assertEqual(uc.version, 2)
        key = uc._make_key(DataCategory.COMMUNICATION_CONTENT, Purpose.PERSONA_CREATION)
        self.assertIn(key, uc.consent_records)
        self.assertEqual(uc.consent_records[key].status, ConsentStatus.GRANTED)
        self.assertEqual(uc.consent_records[key].details, "Initial grant")
        self.assertEqual(uc.get_consent_status(DataCategory.COMMUNICATION_CONTENT, Purpose.PERSONA_CREATION), ConsentStatus.GRANTED)

        # Deny
        uc.deny(DataCategory.SOCIAL_MEDIA_POSTS, Purpose.PERSONA_CREATION, "User dislikes social media")
        self.assertEqual(uc.version, 3)
        key_deny = uc._make_key(DataCategory.SOCIAL_MEDIA_POSTS, Purpose.PERSONA_CREATION)
        self.assertEqual(uc.consent_records[key_deny].status, ConsentStatus.DENIED)
        self.assertEqual(uc.get_consent_status(DataCategory.SOCIAL_MEDIA_POSTS, Purpose.PERSONA_CREATION), ConsentStatus.DENIED)

        # Revoke
        uc.revoke(DataCategory.COMMUNICATION_CONTENT, Purpose.PERSONA_CREATION, "User changed mind")
        self.assertEqual(uc.version, 4)
        self.assertEqual(uc.consent_records[key].status, ConsentStatus.REVOKED)
        self.assertEqual(uc.consent_records[key].details, "User changed mind")
        self.assertEqual(uc.get_consent_status(DataCategory.COMMUNICATION_CONTENT, Purpose.PERSONA_CREATION), ConsentStatus.REVOKED)

        # Revoke non-existent
        original_version = uc.version
        uc.revoke(DataCategory.OTHER, Purpose.OTHER_SPECIFIED) # Should not error, just warn (printed)
        self.assertEqual(uc.version, original_version) # Version should not change if no record was updated

    def test_user_consent_serialization_deserialization(self):
        uc = UserConsent(user_id="u1", persona_id="p1")
        uc.grant(DataCategory.COMMUNICATION_CONTENT, Purpose.PERSONA_CREATION)
        uc.grant(DataCategory.VOICE_RECORDINGS, Purpose.VOICE_CLONING, "For voice output")

        uc_dict = uc.to_dict()

        uc_from_dict = UserConsent.from_dict(uc_dict)

        self.assertEqual(uc_from_dict.user_id, uc.user_id)
        self.assertEqual(uc_from_dict.persona_id, uc.persona_id)
        self.assertEqual(uc_from_dict.version, uc.version)
        self.assertEqual(uc_from_dict.last_updated, uc.last_updated)
        self.assertEqual(len(uc_from_dict.consent_records), len(uc.consent_records))

        key_comm = uc._make_key(DataCategory.COMMUNICATION_CONTENT, Purpose.PERSONA_CREATION)
        key_voice = uc._make_key(DataCategory.VOICE_RECORDINGS, Purpose.VOICE_CLONING)

        self.assertEqual(uc_from_dict.consent_records[key_comm].status, ConsentStatus.GRANTED)
        self.assertEqual(uc_from_dict.consent_records[key_voice].status, ConsentStatus.GRANTED)
        self.assertEqual(uc_from_dict.consent_records[key_voice].details, "For voice output")

    def test_get_consent_status_non_existent(self):
        uc = UserConsent(user_id="u1", persona_id="p1")
        status = uc.get_consent_status(DataCategory.OTHER, Purpose.OTHER_SPECIFIED)
        self.assertIsNone(status)

if __name__ == '__main__':
    unittest.main()
