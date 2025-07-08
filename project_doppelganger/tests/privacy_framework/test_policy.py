import unittest
from datetime import datetime, timezone
from project_doppelganger.src.privacy_framework.policy import PrivacyPolicy, PolicyRule
from project_doppelganger.src.privacy_framework.consent import UserConsent, ConsentStatus
from project_doppelganger.src.privacy_framework.data_attribute import DataCategory, Purpose

class TestPrivacyPolicy(unittest.TestCase):

    def test_policy_rule_serialization(self):
        rule = PolicyRule(
            rule_id="TestRule001",
            description="Test rule description",
            data_categories=[DataCategory.BEHAVIORAL_PATTERNS, DataCategory.USAGE_METADATA],
            purposes=[Purpose.ANALYTICS_AND_IMPROVEMENT],
            allowed=True,
            conditions={"min_anonymization_level": "strong"},
            priority=100
        )
        rule_dict = rule.to_dict()
        expected_dict = {
            "rule_id": "TestRule001",
            "description": "Test rule description",
            "data_categories": [DataCategory.BEHAVIORAL_PATTERNS.value, DataCategory.USAGE_METADATA.value],
            "purposes": [Purpose.ANALYTICS_AND_IMPROVEMENT.value],
            "allowed": True,
            "conditions": {"min_anonymization_level": "strong"},
            "priority": 100
        }
        self.assertEqual(rule_dict, expected_dict)
        rule_from_dict = PolicyRule.from_dict(expected_dict)
        self.assertEqual(rule_from_dict, rule)

        # Test with optional fields being None/default
        rule_simple = PolicyRule(
            rule_id="TestRule002",
            description="Simple rule",
            data_categories=[DataCategory.ANONYMIZED_DATA],
            purposes=[Purpose.RESEARCH_CONSENTED],
            allowed=True
        )
        rule_simple_dict = rule_simple.to_dict()
        self.assertEqual(rule_simple_dict["conditions"], {}) # Default factory
        self.assertEqual(rule_simple_dict["priority"], 0)    # Default value
        rule_simple_from_dict = PolicyRule.from_dict(rule_simple_dict)
        self.assertEqual(rule_simple_from_dict, rule_simple)


    def test_privacy_policy_serialization(self):
        policy = PrivacyPolicy(policy_id="MainPolicy", version="1.1", default_action=False)
        rule1 = PolicyRule(
            rule_id="R1", description="Allow PII for Persona Creation",
            data_categories=[DataCategory.PERSONAL_IDENTIFIABLE_INFORMATION],
            purposes=[Purpose.PERSONA_CREATION], allowed=True, priority=10
        )
        policy.add_rule(rule1)

        policy_dict = policy.to_dict()

        self.assertEqual(policy_dict["policy_id"], "MainPolicy")
        self.assertEqual(policy_dict["version"], "1.1")
        self.assertEqual(policy_dict["default_action"], False)
        self.assertEqual(len(policy_dict["rules"]), 1)
        self.assertEqual(policy_dict["rules"][0]["rule_id"], "R1")

        policy_from_dict = PrivacyPolicy.from_dict(policy_dict)
        self.assertEqual(policy_from_dict.policy_id, policy.policy_id)
        self.assertEqual(policy_from_dict.version, policy.version)
        self.assertEqual(policy_from_dict.default_action, policy.default_action)
        self.assertEqual(policy_from_dict.last_updated, policy.last_updated)
        self.assertEqual(len(policy_from_dict.rules), 1)
        self.assertEqual(policy_from_dict.rules[0], rule1)

    def test_policy_rule_sorting(self):
        policy = PrivacyPolicy(policy_id="SortTest", version="1.0")
        rule_low_priority = PolicyRule("R_Low", "", [DataCategory.OTHER], [Purpose.OTHER_SPECIFIED], True, priority=1)
        rule_high_priority = PolicyRule("R_High", "", [DataCategory.OTHER], [Purpose.OTHER_SPECIFIED], False, priority=10)

        policy.add_rule(rule_low_priority)
        policy.add_rule(rule_high_priority)

        self.assertEqual(policy.rules[0].rule_id, "R_High")
        self.assertEqual(policy.rules[1].rule_id, "R_Low")

    def test_is_processing_allowed_logic(self):
        policy = PrivacyPolicy(policy_id="LogicTest", version="1.0", default_action=False) # Deny by default

        # Rule: Allow PII for Persona Creation IF consent is given
        rule_consent_needed = PolicyRule(
            "R_ConsentPII", "Allow PII for Persona Creation with consent",
            [DataCategory.PERSONAL_IDENTIFIABLE_INFORMATION], [Purpose.PERSONA_CREATION],
            allowed=True, conditions={"requires_explicit_consent": True}, priority=10
        )
        # Rule: Prohibit Social Media for Persona Creation, regardless of consent
        rule_prohibit_social = PolicyRule(
            "R_NoSocial", "No Social Media for Persona Creation",
            [DataCategory.SOCIAL_MEDIA_POSTS], [Purpose.PERSONA_CREATION],
            allowed=False, priority=20 # Higher priority
        )
        # Rule: Allow Anonymized Data for Analytics (no consent condition in rule)
        rule_allow_anon = PolicyRule(
            "R_AnonAnalytics", "Allow Anonymized for Analytics",
            [DataCategory.ANONYMIZED_DATA], [Purpose.ANALYTICS_AND_IMPROVEMENT],
            allowed=True, priority=5
        )
        policy.add_rule(rule_consent_needed)
        policy.add_rule(rule_prohibit_social)
        policy.add_rule(rule_allow_anon)

        # --- Test Scenarios ---
        user_consent = UserConsent("u1", "p1")

        # 1. PII for Persona Creation - NO consent
        self.assertFalse(policy.is_processing_allowed(
            DataCategory.PERSONAL_IDENTIFIABLE_INFORMATION, Purpose.PERSONA_CREATION, user_consent
        ))

        # 2. PII for Persona Creation - WITH consent
        user_consent.grant(DataCategory.PERSONAL_IDENTIFIABLE_INFORMATION, Purpose.PERSONA_CREATION)
        self.assertTrue(policy.is_processing_allowed(
            DataCategory.PERSONAL_IDENTIFIABLE_INFORMATION, Purpose.PERSONA_CREATION, user_consent
        ))
        user_consent.revoke(DataCategory.PERSONAL_IDENTIFIABLE_INFORMATION, Purpose.PERSONA_CREATION) # reset

        # 3. Social Media for Persona Creation - WITH consent (should still be denied by policy)
        user_consent.grant(DataCategory.SOCIAL_MEDIA_POSTS, Purpose.PERSONA_CREATION)
        self.assertFalse(policy.is_processing_allowed(
            DataCategory.SOCIAL_MEDIA_POSTS, Purpose.PERSONA_CREATION, user_consent
        ))

        # 4. Social Media for Persona Creation - WITHOUT consent (also denied)
        user_consent_no_social_grant = UserConsent("u2", "p2")
        self.assertFalse(policy.is_processing_allowed(
             DataCategory.SOCIAL_MEDIA_POSTS, Purpose.PERSONA_CREATION, user_consent_no_social_grant
        ))

        # 5. Anonymized Data for Analytics - no consent object passed (allowed by rule)
        self.assertTrue(policy.is_processing_allowed(
            DataCategory.ANONYMIZED_DATA, Purpose.ANALYTICS_AND_IMPROVEMENT
        ))

        # 6. Anonymized Data for Analytics - with irrelevant consent (still allowed)
        user_consent.grant(DataCategory.OTHER, Purpose.OTHER_SPECIFIED) # Irrelevant consent
        self.assertTrue(policy.is_processing_allowed(
            DataCategory.ANONYMIZED_DATA, Purpose.ANALYTICS_AND_IMPROVEMENT, user_consent
        ))

        # 7. Data/Purpose not covered by any rule - NO consent (denied by default_action=False)
        self.assertFalse(policy.is_processing_allowed(
            DataCategory.USAGE_METADATA, Purpose.PERSONA_ADAPTATION, user_consent
        ))

        # 8. Data/Purpose not covered by any rule - WITH consent (allowed because consent given and no rule prohibits)
        user_consent.grant(DataCategory.USAGE_METADATA, Purpose.PERSONA_ADAPTATION)
        self.assertTrue(policy.is_processing_allowed(
            DataCategory.USAGE_METADATA, Purpose.PERSONA_ADAPTATION, user_consent
        ))

        # 9. Data/Purpose not covered - consent DENIED (denied by consent status)
        user_consent.deny(DataCategory.WRITTEN_DOCUMENTS, Purpose.RESEARCH_CONSENTED)
        self.assertFalse(policy.is_processing_allowed(
            DataCategory.WRITTEN_DOCUMENTS, Purpose.RESEARCH_CONSENTED, user_consent
        ))

if __name__ == '__main__':
    unittest.main()
