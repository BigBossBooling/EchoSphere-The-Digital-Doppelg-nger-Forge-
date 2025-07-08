from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from .data_attribute import DataCategory, Purpose # Relative import
from .consent import UserConsent, ConsentStatus   # Relative import

@dataclass
class PolicyRule:
    rule_id: str
    description: str
    data_categories: List[DataCategory] # Which categories this rule applies to
    purposes: List[Purpose]             # Which purposes this rule applies to
    allowed: bool                       # True if allowed, False if prohibited (can be nuanced by conditions)
    conditions: Optional[Dict[str, Any]] = field(default_factory=dict) # e.g., {"requires_anonymization": True}
    priority: int = 0                   # For rule ordering if conflicts arise

    def to_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "description": self.description,
            "data_categories": [dc.to_dict() for dc in self.data_categories],
            "purposes": [p.to_dict() for p in self.purposes],
            "allowed": self.allowed,
            "conditions": self.conditions,
            "priority": self.priority,
        }

    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            rule_id=data["rule_id"],
            description=data["description"],
            data_categories=[DataCategory.from_dict(dc) for dc in data["data_categories"]],
            purposes=[Purpose.from_dict(p) for p in data["purposes"]],
            allowed=data["allowed"],
            conditions=data.get("conditions"),
            priority=data.get("priority", 0),
        )

@dataclass
class PrivacyPolicy:
    policy_id: str
    version: str
    rules: List[PolicyRule] = field(default_factory=list)
    default_action: bool = False # False = deny by default if no rule matches
    last_updated: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def add_rule(self, rule: PolicyRule):
        self.rules.append(rule)
        self.rules.sort(key=lambda r: r.priority, reverse=True) # Higher priority first
        self.last_updated = datetime.now(timezone.utc)

    def is_processing_allowed(self, data_category: DataCategory, purpose: Purpose, user_consent: Optional[UserConsent] = None) -> bool:
        """
        Checks if processing data of a certain category for a specific purpose is allowed
        according to this policy and, if provided, user consent.
        """
        # 1. Check user consent first (if provided)
        if user_consent:
            consent_status = user_consent.get_consent_status(data_category, purpose)
            if consent_status == ConsentStatus.DENIED or consent_status == ConsentStatus.REVOKED:
                return False # User explicitly denied/revoked
            if consent_status == ConsentStatus.GRANTED:
                # User granted, now check policy rules for any overriding prohibitions or conditions
                pass # Fall through to policy check
            else: # PENDING, EXPIRED, or not set
                # If consent is not explicitly GRANTED, policy must allow AND it must be a case where consent is not strictly required by policy
                # This part can get complex depending on "consent not required" interpretation.
                # For now, if consent is not GRANTED, we will rely on policy rules that might allow without explicit consent.
                pass


        # 2. Check policy rules
        for rule in self.rules:
            if data_category in rule.data_categories and purpose in rule.purposes:
                # Rule applies. Now check conditions if any.
                # This is a simplified condition check. Real-world might be more complex.
                if "requires_anonymization" in rule.conditions and rule.conditions["requires_anonymization"]:
                    if data_category != DataCategory.ANONYMIZED_DATA: # Example condition
                        # If data is not anonymized, this rule (even if 'allowed') might not permit yet.
                        # Or, this might be a transformation step. For now, assume it means data must BE anonymized.
                        continue # Skip to next rule or default if data isn't already anonymized

                if "requires_explicit_consent" in rule.conditions and rule.conditions["requires_explicit_consent"]:
                    if not user_consent or user_consent.get_consent_status(data_category, purpose) != ConsentStatus.GRANTED:
                        return False # Explicit consent required by policy but not granted by user

                return rule.allowed # Return the rule's verdict

        # 3. Default action if no specific rule matched
        # If default_action is False (deny by default), and we reached here, it means no rule explicitly allowed it.
        # However, if consent was GRANTED and no policy rule *prohibited* it, it should be allowed.
        if user_consent and user_consent.get_consent_status(data_category, purpose) == ConsentStatus.GRANTED:
            # If user granted consent, and no policy rule specifically denied it, then it's allowed.
            # (Assuming default_action might be 'deny' but consent overrides if no prohibitive rule found)
            return True

        return self.default_action

    def to_dict(self) -> dict:
        return {
            "policy_id": self.policy_id,
            "version": self.version,
            "rules": [r.to_dict() for r in self.rules],
            "default_action": self.default_action,
            "last_updated": self.last_updated.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict):
        policy = cls(
            policy_id=data["policy_id"],
            version=data["version"],
            default_action=data.get("default_action", False),
            last_updated=datetime.fromisoformat(data.get("last_updated", datetime.now(timezone.utc).isoformat()))
        )
        policy.rules = [PolicyRule.from_dict(r_data) for r_data in data.get("rules", [])]
        policy.rules.sort(key=lambda r: r.priority, reverse=True) # Ensure sort order
        return policy

# Example Usage:
if __name__ == "__main__":
    # Define some rules
    rule1 = PolicyRule(
        rule_id="R001",
        description="Allow PII for Persona Creation with explicit consent.",
        data_categories=[DataCategory.PERSONAL_IDENTIFIABLE_INFORMATION, DataCategory.COMMUNICATION_CONTENT],
        purposes=[Purpose.PERSONA_CREATION],
        allowed=True,
        conditions={"requires_explicit_consent": True},
        priority=10
    )
    rule2 = PolicyRule(
        rule_id="R002",
        description="Allow Anonymized Data for Analytics.",
        data_categories=[DataCategory.ANONYMIZED_DATA],
        purposes=[Purpose.ANALYTICS_AND_IMPROVEMENT],
        allowed=True,
        priority=5
    )
    rule3 = PolicyRule(
        rule_id="R003",
        description="Prohibit Social Media for Persona Creation by default.",
        data_categories=[DataCategory.SOCIAL_MEDIA_POSTS],
        purposes=[Purpose.PERSONA_CREATION],
        allowed=False,
        priority=20 # High priority prohibition
    )

    # Create a policy
    policy = PrivacyPolicy(policy_id="PP-Doppelganger-v1", version="1.0", default_action=False) # Deny by default
    policy.add_rule(rule1)
    policy.add_rule(rule2)
    policy.add_rule(rule3)

    print(f"PrivacyPolicy object: {policy}")
    policy_dict = policy.to_dict()
    print(f"\nto_dict(): {policy_dict}")
    rehydrated_policy = PrivacyPolicy.from_dict(policy_dict)
    print(f"\nfrom_dict(): {rehydrated_policy}")

    assert policy.policy_id == rehydrated_policy.policy_id
    assert len(policy.rules) == len(rehydrated_policy.rules)

    # Test policy logic
    # Scenario 1: PII for Persona Creation WITHOUT consent
    print(f"\nScenario 1 (PII for Persona Creation, no consent):")
    print(f"Allowed? {policy.is_processing_allowed(DataCategory.PERSONAL_IDENTIFIABLE_INFORMATION, Purpose.PERSONA_CREATION)}")
    assert not policy.is_processing_allowed(DataCategory.PERSONAL_IDENTIFIABLE_INFORMATION, Purpose.PERSONA_CREATION)


    # Scenario 2: PII for Persona Creation WITH consent
    print(f"\nScenario 2 (PII for Persona Creation, with consent):")
    user_consent_s2 = UserConsent(user_id="test_user", persona_id="test_persona")
    user_consent_s2.grant(DataCategory.PERSONAL_IDENTIFIABLE_INFORMATION, Purpose.PERSONA_CREATION)
    print(f"Allowed? {policy.is_processing_allowed(DataCategory.PERSONAL_IDENTIFIABLE_INFORMATION, Purpose.PERSONA_CREATION, user_consent_s2)}")
    assert policy.is_processing_allowed(DataCategory.PERSONAL_IDENTIFIABLE_INFORMATION, Purpose.PERSONA_CREATION, user_consent_s2)

    # Scenario 3: Anonymized data for Analytics (no specific consent needed by this rule)
    print(f"\nScenario 3 (Anonymized for Analytics, no consent object):")
    print(f"Allowed? {policy.is_processing_allowed(DataCategory.ANONYMIZED_DATA, Purpose.ANALYTICS_AND_IMPROVEMENT)}")
    assert policy.is_processing_allowed(DataCategory.ANONYMIZED_DATA, Purpose.ANALYTICS_AND_IMPROVEMENT)

    # Scenario 4: Social Media for Persona Creation (prohibited by high priority rule R003)
    print(f"\nScenario 4 (Social Media for Persona Creation, with consent):")
    user_consent_s4 = UserConsent(user_id="test_user", persona_id="test_persona")
    user_consent_s4.grant(DataCategory.SOCIAL_MEDIA_POSTS, Purpose.PERSONA_CREATION) # User consents
    # Policy R003 should override this consent due to 'allowed=False'
    print(f"Allowed? {policy.is_processing_allowed(DataCategory.SOCIAL_MEDIA_POSTS, Purpose.PERSONA_CREATION, user_consent_s4)}")
    assert not policy.is_processing_allowed(DataCategory.SOCIAL_MEDIA_POSTS, Purpose.PERSONA_CREATION, user_consent_s4)

    # Scenario 5: Communication Content for Persona Adaptation (No specific rule, consent granted, default policy deny)
    # This should be allowed because consent is GRANTED and no rule *prohibits* it.
    print(f"\nScenario 5 (Comm Content for Adaptation, consent granted, no specific rule, default deny policy):")
    user_consent_s5 = UserConsent(user_id="test_user", persona_id="test_persona")
    user_consent_s5.grant(DataCategory.COMMUNICATION_CONTENT, Purpose.PERSONA_ADAPTATION)
    print(f"Allowed? {policy.is_processing_allowed(DataCategory.COMMUNICATION_CONTENT, Purpose.PERSONA_ADAPTATION, user_consent_s5)}")
    assert policy.is_processing_allowed(DataCategory.COMMUNICATION_CONTENT, Purpose.PERSONA_ADAPTATION, user_consent_s5)

    # Scenario 6: Communication Content for Persona Adaptation (No specific rule, consent NOT granted, default policy deny)
    print(f"\nScenario 6 (Comm Content for Adaptation, consent NOT granted, no specific rule, default deny policy):")
    user_consent_s6 = UserConsent(user_id="test_user", persona_id="test_persona") # No grant for this
    print(f"Allowed? {policy.is_processing_allowed(DataCategory.COMMUNICATION_CONTENT, Purpose.PERSONA_ADAPTATION, user_consent_s6)}")
    assert not policy.is_processing_allowed(DataCategory.COMMUNICATION_CONTENT, Purpose.PERSONA_ADAPTATION, user_consent_s6)


    print("\nAll assertions passed.")
