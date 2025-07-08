import re
import hashlib
from typing import Any, Dict, List, Tuple, Callable

from .consent import UserConsent, ConsentStatus  # Relative import
from .data_attribute import DataCategory, Purpose # Relative import
from .policy import PrivacyPolicy # Relative import (though policy evaluation might be conceptual here)

# Placeholder for a more sophisticated PolicyEvaluator if needed later.
# For now, process_data will directly use UserConsent.
class PolicyEvaluator:
    def __init__(self, policy: PrivacyPolicy):
        self.policy = policy

    def is_allowed(self, data_category: DataCategory, purpose: Purpose, user_consent: UserConsent) -> bool:
        return self.policy.is_processing_allowed(data_category, purpose, user_consent)

class DataClassifier:
    """
    Identifies PII and other data categories within raw data.
    Uses rule-based/regex for PII detection.
    """
    # Basic regex patterns for common PII. These would need to be significantly more robust for production.
    PATTERNS = {
        DataCategory.PERSONAL_IDENTIFIABLE_INFORMATION: {
            "EMAIL": re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'),
            "PHONE_NUMBER_US": re.compile(r'\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b'),
            # Add more specific PII like SSN, Credit Card if within scope and handled extremely carefully
        },
        # Potentially other categories if they can be regex-detected from unstructured text
    }

    def classify_text_data(self, text: str) -> Dict[DataCategory, List[Tuple[str, str, Tuple[int, int]]]]:
        """
        Classifies text data, identifying occurrences of different data categories.
        Returns a dictionary mapping DataCategory to a list of (type, value, (start_index, end_index)).
        Example: {DataCategory.PII: [("EMAIL", "test@example.com", (10, 25))]}
        """
        classifications: Dict[DataCategory, List[Tuple[str, str, Tuple[int, int]]]] = {}

        for category, patterns in self.PATTERNS.items():
            for pii_type, regex in patterns.items():
                for match in regex.finditer(text):
                    if category not in classifications:
                        classifications[category] = []
                    classifications[category].append(
                        (pii_type, match.group(0), (match.start(), match.end()))
                    )
        return classifications

class ObfuscationEngine:
    """
    Provides methods for obfuscating identified sensitive data.
    """
    def redact(self, text: str, start: int, end: int, redaction_char: str = "*") -> str:
        """Redacts a portion of text."""
        return text[:start] + redaction_char * (end - start) + text[end:]

    def hash_value(self, value: str, algorithm: str = "sha256") -> str:
        """Hashes a string value."""
        hasher = hashlib.new(algorithm)
        hasher.update(value.encode('utf-8'))
        return f"<{algorithm}:{hasher.hexdigest()}>"

    def tokenize_value(self, value: str, token_prefix: str = "TOKEN_") -> str:
        """Replaces a value with a generic token (conceptual, needs a token management system for reversibility if required)."""
        # This is a simplistic non-reversible tokenization.
        # Real tokenization might involve a secure vault for reversible de-tokenization.
        value_type = "VALUE" # Could be derived or passed in
        return f"<{token_prefix}{value_type}_{hashlib.sha256(value.encode('utf-8')).hexdigest()[:8]}>"

class MinimizerEngine:
    """
    The EchoSphere Minimizer Engine.
    Processes data according to user consent and privacy policies,
    classifying and obfuscating sensitive information.
    """
    def __init__(self, policy: Optional[PrivacyPolicy] = None): # Policy is optional for now
        self.classifier = DataClassifier()
        self.obfuscator = ObfuscationEngine()
        self.policy = policy # A full policy might be used for more complex decisions

    def process_text_data(self, raw_text: str, user_consent: UserConsent,
                          purpose: Purpose,
                          # Default obfuscation methods per PII type
                          obfuscation_map: Optional[Dict[str, Callable[[str], str]]] = None
                         ) -> str:
        """
        Processes raw text data based on user consent for a given purpose.
        Identifies PII, checks consent, and applies obfuscation.

        Args:
            raw_text: The input text string.
            user_consent: The UserConsent object.
            purpose: The Purpose for which this data is being processed.
            obfuscation_map: Optional map of PII type (e.g., "EMAIL") to an obfuscation function.
                             Defaults to redaction for PII if not specified.

        Returns:
            The processed (potentially obfuscated) text.
        """
        if obfuscation_map is None:
            obfuscation_map = {
                "EMAIL": lambda val: self.obfuscator.redact(val, 0, len(val)), # Full redact email by default
                "PHONE_NUMBER_US": lambda val: self.obfuscator.redact(val, 0, len(val)), # Full redact phone
                # Default for unknown PII types if any were to be classified
                "DEFAULT_PII": lambda val: self.obfuscator.redact(val, 0, len(val))
            }

        processed_text = raw_text
        identified_pii = self.classifier.classify_text_data(raw_text)

        # Apply obfuscations in reverse order of start index to avoid index shifting issues
        all_matches: List[Tuple[DataCategory, str, str, Tuple[int, int]]] = []
        for category, matches in identified_pii.items():
            for pii_type, value, (start, end) in matches:
                all_matches.append((category, pii_type, value, (start, end)))

        all_matches.sort(key=lambda x: x[3][0], reverse=True)

        for category, pii_type, value, (start, end) in all_matches:
            consent_status = user_consent.get_consent_status(category, purpose)

            # Policy check (simplified: if policy exists and denies, it overrides everything)
            if self.policy:
                if not self.policy.is_processing_allowed(category, purpose, user_consent):
                    # Policy denies processing for this category/purpose, even if consent might exist.
                    # Strongest action: redact or remove.
                    obfuscation_func = obfuscation_map.get(pii_type, obfuscation_map.get("DEFAULT_PII"))
                    # We need to apply this to the *original* raw_text substring to get the obfuscated value,
                    # then replace it in the *current* processed_text. This is tricky.
                    # Simpler: just redact in place on processed_text.
                    processed_text = self.obfuscator.redact(processed_text, start, end)
                    print(f"Policy DENIED {category.value}/{pii_type} for {purpose.value}. Redacting.")
                    continue

            if consent_status == ConsentStatus.GRANTED:
                # User granted consent. Data can be used as is (for this simplified model).
                # In a more complex scenario, policy might still enforce some transformation.
                print(f"Consent GRANTED for {category.value}/{pii_type} for {purpose.value}. No obfuscation based on consent.")
                # No obfuscation applied here based on consent, but policy override already checked.
                pass
            elif consent_status == ConsentStatus.DENIED or consent_status == ConsentStatus.REVOKED:
                # User denied or revoked consent. Obfuscate.
                obfuscation_fn = obfuscation_map.get(pii_type, obfuscation_map.get("DEFAULT_PII"))
                # As above, simpler to redact in place on processed_text
                processed_text = self.obfuscator.redact(processed_text, start, end)
                print(f"Consent DENIED/REVOKED for {category.value}/{pii_type} for {purpose.value}. Redacting.")

            else: # PENDING, EXPIRED, or not set. Treat as if denied for safety.
                obfuscation_fn = obfuscation_map.get(pii_type, obfuscation_map.get("DEFAULT_PII"))
                processed_text = self.obfuscator.redact(processed_text, start, end)
                print(f"Consent PENDING/EXPIRED/UNSET for {category.value}/{pii_type} for {purpose.value}. Redacting for safety.")

        return processed_text

    def process_data(self, raw_data: Any, data_category_hint: DataCategory,
                     user_consent: UserConsent, purpose: Purpose) -> Any:
        """
        Generic data processing router.
        For now, focuses on text data. Other types would need specific handlers.
        `data_category_hint` is what the system believes the bulk data type is.
        Individual parts might be classified differently (e.g., PII within text).
        """
        if isinstance(raw_data, str) and \
           (data_category_hint == DataCategory.COMMUNICATION_CONTENT or \
            data_category_hint == DataCategory.WRITTEN_DOCUMENTS or \
            data_category_hint == DataCategory.SOCIAL_MEDIA_POSTS or \
            data_category_hint == DataCategory.PERSONAL_IDENTIFIABLE_INFORMATION # if raw_data is a block of PII
           ):
            # Check overall consent for processing this category for this purpose
            overall_consent_status = user_consent.get_consent_status(data_category_hint, purpose)

            if self.policy and not self.policy.is_processing_allowed(data_category_hint, purpose, user_consent):
                print(f"Policy DENIES processing of {data_category_hint.value} for {purpose.value}. Returning placeholder.")
                return f"[Data of type {data_category_hint.value} withheld due to policy]"

            if overall_consent_status == ConsentStatus.DENIED or overall_consent_status == ConsentStatus.REVOKED:
                print(f"Consent DENIED/REVOKED for bulk category {data_category_hint.value} for {purpose.value}. Returning placeholder.")
                return f"[Data of type {data_category_hint.value} withheld due to consent]"

            # If overall consent is pending/expired/unset, we might still process to strip PII,
            # but the result should reflect that the main data itself isn't fully consented for the purpose.
            # For now, we proceed to PII stripping.

            return self.process_text_data(raw_text=raw_data, user_consent=user_consent, purpose=purpose)

        # Placeholder for other data types
        print(f"Processing for data type {type(raw_data)} with hint {data_category_hint.value} not fully implemented. Passing through.")
        return raw_data


# Example Usage for MinimizerEngine (conceptual, better in tests)
if __name__ == "__main__":
    from .policy import PolicyRule # For creating a sample policy

    # --- Setup ---
    sample_policy = PrivacyPolicy("SampleMinimizerPolicy", "1.0", default_action=False)
    # Rule: Allow PII for Persona Creation IF consent is given
    sample_policy.add_rule(PolicyRule(
        "R_ConsentPII_Minimizer", "Allow PII for Persona Creation with consent",
        [DataCategory.PERSONAL_IDENTIFIABLE_INFORMATION], [Purpose.PERSONA_CREATION],
        allowed=True, conditions={"requires_explicit_consent": True}, priority=10
    ))
    # Rule: Prohibit Social Media data for Persona Creation
    sample_policy.add_rule(PolicyRule(
        "R_NoSocial_Minimizer", "No Social Media for Persona Creation",
        [DataCategory.SOCIAL_MEDIA_POSTS], [Purpose.PERSONA_CREATION],
        allowed=False, priority=20
    ))
     # Rule: Allow communication content for persona creation (will allow PII stripping if PII consent is also there)
    sample_policy.add_rule(PolicyRule(
        "R_AllowCommContent_Minimizer", "Allow Comm Content for Persona Creation",
        [DataCategory.COMMUNICATION_CONTENT], [Purpose.PERSONA_CREATION],
        allowed=True, priority=5
    ))


    engine = MinimizerEngine(policy=sample_policy)
    user_consent_granted_pii = UserConsent("user1", "persona1")
    user_consent_granted_pii.grant(DataCategory.PERSONAL_IDENTIFIABLE_INFORMATION, Purpose.PERSONA_CREATION)
    user_consent_granted_pii.grant(DataCategory.COMMUNICATION_CONTENT, Purpose.PERSONA_CREATION)


    user_consent_denied_pii = UserConsent("user2", "persona2")
    user_consent_denied_pii.deny(DataCategory.PERSONAL_IDENTIFIABLE_INFORMATION, Purpose.PERSONA_CREATION)
    user_consent_denied_pii.grant(DataCategory.COMMUNICATION_CONTENT, Purpose.PERSONA_CREATION) # Grant for main category

    user_consent_no_comm_content = UserConsent("user3", "persona3")
    user_consent_no_comm_content.grant(DataCategory.PERSONAL_IDENTIFIABLE_INFORMATION, Purpose.PERSONA_CREATION)
    # No grant/deny for COMMUNICATION_CONTENT

    raw_text_example = "Hello, my email is test@example.com and phone is (123) 456-7890. Please reply."
    purpose_to_test = Purpose.PERSONA_CREATION

    print("--- Scenario 1: PII Consent GRANTED for PII and Communication Content ---")
    processed_text1 = engine.process_data(
        raw_text_example,
        DataCategory.COMMUNICATION_CONTENT,
        user_consent_granted_pii,
        purpose_to_test
    )
    print(f"Original: {raw_text_example}")
    print(f"Processed: {processed_text1}") # Expect: PII visible as PII consent is granted.

    print("\n--- Scenario 2: PII Consent DENIED for PII, Granted for Communication Content ---")
    processed_text2 = engine.process_data(
        raw_text_example,
        DataCategory.COMMUNICATION_CONTENT,
        user_consent_denied_pii,
        purpose_to_test
    )
    print(f"Original: {raw_text_example}")
    print(f"Processed: {processed_text2}") # Expect: PII redacted as PII consent is denied.

    print("\n--- Scenario 3: Consent for PII granted, but NO specific consent for Communication Content (main category) ---")
    # Current process_data logic will deny if the main category (COMMUNICATION_CONTENT) is not granted.
    processed_text3 = engine.process_data(
        raw_text_example,
        DataCategory.COMMUNICATION_CONTENT,
        user_consent_no_comm_content, # No consent for COMMUNICATION_CONTENT
        purpose_to_test
    )
    print(f"Original: {raw_text_example}")
    print(f"Processed for User3: {processed_text3}") # Expect: placeholder like "[Data of type ... withheld ...]"

    print("\n--- Scenario 4: Social Media Data (Policy Denies) ---")
    social_post = "My email is social@example.com from my social media."
    user_consent_social_granted = UserConsent("user4", "persona4")
    user_consent_social_granted.grant(DataCategory.SOCIAL_MEDIA_POSTS, Purpose.PERSONA_CREATION)
    user_consent_social_granted.grant(DataCategory.PERSONAL_IDENTIFIABLE_INFORMATION, Purpose.PERSONA_CREATION)

    processed_social = engine.process_data(
        social_post,
        DataCategory.SOCIAL_MEDIA_POSTS,
        user_consent_social_granted,
        purpose_to_test
    )
    print(f"Original: {social_post}")
    print(f"Processed Social: {processed_social}") # Expect: placeholder due to policy denying SOCIAL_MEDIA_POSTS

    print("\n--- Test Obfuscator directly ---")
    obf = ObfuscationEngine()
    email = "test@example.com"
    print(f"Redact '{email}': {obf.redact(email, 0, len(email))}")
    print(f"Hash '{email}': {obf.hash_value(email)}")
    print(f"Tokenize '{email}': {obf.tokenize_value(email)}")
