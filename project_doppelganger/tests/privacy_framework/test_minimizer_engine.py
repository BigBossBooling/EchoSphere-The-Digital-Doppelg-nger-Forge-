import unittest
import re
from project_doppelganger.src.privacy_framework.minimizer_engine import DataClassifier, ObfuscationEngine, MinimizerEngine
from project_doppelganger.src.privacy_framework.data_attribute import DataCategory, Purpose
from project_doppelganger.src.privacy_framework.consent import UserConsent, ConsentStatus
from project_doppelganger.src.privacy_framework.policy import PrivacyPolicy, PolicyRule

class TestDataClassifier(unittest.TestCase):
    def setUp(self):
        self.classifier = DataClassifier()

    def test_classify_email(self):
        text = "Contact me at test.user@example.com or other@domain.co.uk."
        classifications = self.classifier.classify_text_data(text)
        self.assertIn(DataCategory.PERSONAL_IDENTIFIABLE_INFORMATION, classifications)
        pii_matches = classifications[DataCategory.PERSONAL_IDENTIFIABLE_INFORMATION]
        self.assertEqual(len(pii_matches), 2)
        self.assertEqual(pii_matches[0][0], "EMAIL")
        self.assertEqual(pii_matches[0][1], "test.user@example.com")
        self.assertEqual(pii_matches[1][0], "EMAIL")
        self.assertEqual(pii_matches[1][1], "other@domain.co.uk")

    def test_classify_phone_number_us(self):
        text = "Call (123) 456-7890 or 987-654-3210 or +1 555.555.5555"
        classifications = self.classifier.classify_text_data(text)
        self.assertIn(DataCategory.PERSONAL_IDENTIFIABLE_INFORMATION, classifications)
        pii_matches = classifications[DataCategory.PERSONAL_IDENTIFIABLE_INFORMATION]
        self.assertEqual(len(pii_matches), 3)
        self.assertEqual(pii_matches[0][0], "PHONE_NUMBER_US")
        self.assertEqual(pii_matches[0][1], "(123) 456-7890")
        self.assertEqual(pii_matches[1][1], "987-654-3210")
        self.assertEqual(pii_matches[2][1], "+1 555.555.5555")

    def test_no_pii_found(self):
        text = "This is a generic sentence without any PII."
        classifications = self.classifier.classify_text_data(text)
        self.assertNotIn(DataCategory.PERSONAL_IDENTIFIABLE_INFORMATION, classifications)

class TestObfuscationEngine(unittest.TestCase):
    def setUp(self):
        self.obfuscator = ObfuscationEngine()

    def test_redact(self):
        text = "sensitive_data"
        redacted = self.obfuscator.redact(text, 0, len(text))
        self.assertEqual(redacted, "*" * len(text))

        partial_redact = self.obfuscator.redact(text, 0, 8, "-")
        self.assertEqual(partial_redact, "--------data")

    def test_hash_value(self):
        value = "test_value"
        hashed = self.obfuscator.hash_value(value)
        self.assertTrue(hashed.startswith("<sha256:"))
        self.assertTrue(hashed.endswith(">"))
        self.assertEqual(len(hashed), len("<sha256:") + 64 + len(">")) # 64 hex chars for sha256

        hashed_md5 = self.obfuscator.hash_value(value, algorithm="md5")
        self.assertTrue(hashed_md5.startswith("<md5:"))
        self.assertEqual(len(hashed_md5), len("<md5:") + 32 + len(">")) # 32 hex chars for md5

    def test_tokenize_value(self):
        value = "secret_info"
        tokenized = self.obfuscator.tokenize_value(value)
        self.assertTrue(tokenized.startswith("<TOKEN_VALUE_"))
        self.assertTrue(tokenized.endswith(">"))
        # Check that different values produce different tokens
        tokenized2 = self.obfuscator.tokenize_value("another_secret")
        self.assertNotEqual(tokenized, tokenized2)
        # Check that same value produces same token (for this simple version)
        tokenized_same = self.obfuscator.tokenize_value(value)
        self.assertEqual(tokenized, tokenized_same)


class TestMinimizerEngine(unittest.TestCase):
    def setUp(self):
        self.sample_policy = PrivacyPolicy("TestPolicy", "1.0", default_action=False)
        self.sample_policy.add_rule(PolicyRule(
            "R_AllowComm", "Allow Comm Content",
            [DataCategory.COMMUNICATION_CONTENT], [Purpose.PERSONA_CREATION], allowed=True, priority=1
        ))
        self.sample_policy.add_rule(PolicyRule(
            "R_PIIConsent", "PII Needs Consent",
            [DataCategory.PERSONAL_IDENTIFIABLE_INFORMATION], [Purpose.PERSONA_CREATION],
            allowed=True, conditions={"requires_explicit_consent": True}, priority=10
        ))
        self.sample_policy.add_rule(PolicyRule(
            "R_DenySocial", "Deny Social",
            [DataCategory.SOCIAL_MEDIA_POSTS], [Purpose.PERSONA_CREATION], allowed=False, priority=20
        ))
        self.engine = MinimizerEngine(policy=self.sample_policy)

        self.raw_text = "My email is test@example.com, and my friend's is friend@example.org. Call 123-456-7890."
        self.purpose = Purpose.PERSONA_CREATION

    def test_process_text_data_pii_consent_granted(self):
        uc = UserConsent("u1", "p1")
        uc.grant(DataCategory.COMMUNICATION_CONTENT, self.purpose)
        uc.grant(DataCategory.PERSONAL_IDENTIFIABLE_INFORMATION, self.purpose)

        processed = self.engine.process_text_data(self.raw_text, uc, self.purpose)
        # With PII consent granted, and policy allowing PII with consent, text should be unchanged
        self.assertEqual(processed, self.raw_text)

    def test_process_text_data_pii_consent_denied(self):
        uc = UserConsent("u1", "p1")
        uc.grant(DataCategory.COMMUNICATION_CONTENT, self.purpose)
        uc.deny(DataCategory.PERSONAL_IDENTIFIABLE_INFORMATION, self.purpose) # Explicitly deny PII

        processed = self.engine.process_text_data(self.raw_text, uc, self.purpose)

        # PII should be redacted
        expected = "My email is ****************, and my friend's is ******************. Call ************."
        self.assertEqual(processed, expected)

    def test_process_text_data_pii_consent_not_set(self):
        uc = UserConsent("u1", "p1")
        uc.grant(DataCategory.COMMUNICATION_CONTENT, self.purpose)
        # No specific consent for PII (neither grant nor deny)

        processed = self.engine.process_text_data(self.raw_text, uc, self.purpose)
        # PII should be redacted as it's treated as "denied for safety" if not explicitly granted
        # and policy has "requires_explicit_consent" (even if allowed=True in rule, condition not met)
        # The MinimizerEngine's process_text_data has a fallback redaction for PENDING/EXPIRED/UNSET PII
        expected = "My email is ****************, and my friend's is ******************. Call ************."
        self.assertEqual(processed, expected)

    def test_process_data_main_category_consent_denied(self):
        uc = UserConsent("u1", "p1")
        uc.deny(DataCategory.COMMUNICATION_CONTENT, self.purpose) # Deny the main category
        uc.grant(DataCategory.PERSONAL_IDENTIFIABLE_INFORMATION, self.purpose) # Grant PII (won't matter)

        processed = self.engine.process_data(self.raw_text, DataCategory.COMMUNICATION_CONTENT, uc, self.purpose)
        self.assertEqual(processed, f"[Data of type {DataCategory.COMMUNICATION_CONTENT.value} withheld due to consent]")

    def test_process_data_policy_denies_main_category(self):
        uc = UserConsent("u1", "p1")
        uc.grant(DataCategory.SOCIAL_MEDIA_POSTS, self.purpose) # Grant consent
        uc.grant(DataCategory.PERSONAL_IDENTIFIABLE_INFORMATION, self.purpose)

        social_text = "This is a social media post with email social@example.com."
        processed = self.engine.process_data(social_text, DataCategory.SOCIAL_MEDIA_POSTS, uc, self.purpose)
        # Policy R_DenySocial should prevent processing of SOCIAL_MEDIA_POSTS
        self.assertEqual(processed, f"[Data of type {DataCategory.SOCIAL_MEDIA_POSTS.value} withheld due to policy]")

    def test_process_text_data_custom_obfuscation_map(self):
        uc = UserConsent("u1", "p1")
        uc.grant(DataCategory.COMMUNICATION_CONTENT, self.purpose)
        uc.deny(DataCategory.PERSONAL_IDENTIFIABLE_INFORMATION, self.purpose) # Deny PII to trigger obfuscation

        custom_map = {
            "EMAIL": lambda val: self.engine.obfuscator.hash_value(val),
            "PHONE_NUMBER_US": lambda val: "PHONE_TOKENIZED",
            "DEFAULT_PII": lambda val: "DEFAULT_REDACTED" # Should not be used if types match
        }

        processed = self.engine.process_text_data(self.raw_text, uc, self.purpose, obfuscation_map=custom_map)

        # Expected: email hashed, phone tokenized
        email1_hashed = self.engine.obfuscator.hash_value("test@example.com")
        email2_hashed = self.engine.obfuscator.hash_value("friend@example.org")
        expected = f"My email is {email1_hashed}, and my friend's is {email2_hashed}. Call PHONE_TOKENIZED."
        self.assertEqual(processed, expected)

if __name__ == '__main__':
    unittest.main()
