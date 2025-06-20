# echosystem/utils/privacy_protocol.py

# Attempt to import ConsentLedgerEntry.
# This might require adjustments to sys.path if running this file directly,
# but should work when the echosystem package is properly structured and installed.
try:
    from echosystem.phase1.user_data_integration.data_structures import ConsentLedgerEntry
except ImportError:
    # Fallback for direct execution or if path issues exist, use a dummy class
    print("Warning: Could not import ConsentLedgerEntry. Using a dummy class for PrivacyProtocol.")
    class ConsentLedgerEntry:
        def __init__(self, user_id, data_hash, consent_scope, consent_description, expiration_date=None):
            self.user_id = user_id
            self.data_hash = data_hash
            self.consent_scope = consent_scope
            self.consent_description = consent_description
            self.expiration_date = expiration_date
            self.revocation_status = False
            self.consent_id = "dummy_consent_id"

        def revoke(self):
            self.revocation_status = True

import datetime
import hashlib

class PrivacyProtocol:
    """
    Manages user consent and enforces data privacy principles like data minimization.
    This class acts as a conceptual placeholder for managing privacy logic.
    In a real system, this would be more complex and integrate with a consent ledger.
    """

    def __init__(self, consent_ledger_adapter=None):
        """
        Initializes the PrivacyProtocol.

        Args:
            consent_ledger_adapter: An adapter to interact with the consent ledger
                                     (e.g., a database, blockchain). For now, a simple dict.
        """
        self.consent_ledger = consent_ledger_adapter if consent_ledger_adapter is not None else {}
        print("PrivacyProtocol initialized.")

    def _hash_data(self, data_description: str) -> str:
        """Helper to create a consistent hash for data description."""
        return hashlib.sha256(data_description.encode()).hexdigest()

    def request_consent(self, user_id: str, data_description: str, consent_scope: str, consent_details: str) -> bool:
        """
        Presents a consent request to the user.
        In a real UI, this would be a detailed prompt. Here, it's simulated.
        """
        print(f"\n--- CONSENT REQUEST ---")
        print(f"User: {user_id}")
        print(f"Data/Activity: {data_description}")
        print(f"Purpose: {consent_scope}")
        print(f"Details: {consent_details}")
        # Simulate user giving consent (e.g., via a UI interaction)
        user_response = input("Do you grant consent? (yes/no): ").strip().lower()
        if user_response == 'yes':
            return True
        return False

    def grant_consent(self, user_id: str, data_description: str, consent_scope: str, consent_details: str, expiration_days: int = None) -> ConsentLedgerEntry | None:
        """
        Records the user's consent in the consent ledger.

        Args:
            user_id: The user's identifier.
            data_description: Description of the data or processing activity.
            consent_scope: The scope for which consent is granted.
            consent_details: More detailed explanation of the consent.
            expiration_days: Optional number of days after which consent expires.

        Returns:
            A ConsentLedgerEntry object if consent was granted, else None.
        """
        # data_hash = self._hash_data(data_description + consent_scope) # More specific hash
        data_hash = self._hash_data(data_description) # Using data_description to link to data

        expiration_date = None
        if expiration_days:
            expiration_date = datetime.datetime.now() + datetime.timedelta(days=expiration_days)

        consent_entry = ConsentLedgerEntry(
            user_id=user_id,
            data_hash=data_hash, # This hash should ideally be of the data itself if available, or a unique descriptor
            consent_scope=consent_scope,
            consent_description=consent_details,
            expiration_date=expiration_date
        )

        # Store in our mock ledger
        self.consent_ledger[consent_entry.consent_id] = consent_entry
        print(f"PrivacyProtocol: Consent granted and recorded. Entry ID: {consent_entry.consent_id}")
        return consent_entry

    def verify_consent(self, user_id: str, consent_id: str, required_scope: str = None) -> bool:
        """
        Verifies if a valid, non-revoked, and non-expired consent exists for a given scope.

        Args:
            user_id: The user's identifier.
            consent_id: The ID of the consent entry to check.
            required_scope: The specific scope required for the action.

        Returns:
            True if valid consent exists, False otherwise.
        """
        consent_entry = self.consent_ledger.get(consent_id)

        if not consent_entry:
            print(f"PrivacyProtocol: Consent ID {consent_id} not found.")
            return False

        if consent_entry.user_id != user_id:
            print(f"PrivacyProtocol: User ID mismatch for consent {consent_id}.")
            return False

        if consent_entry.revocation_status:
            print(f"PrivacyProtocol: Consent {consent_id} has been revoked.")
            return False

        if consent_entry.expiration_date:
            if datetime.datetime.now() > datetime.datetime.fromisoformat(consent_entry.expiration_date):
                print(f"PrivacyProtocol: Consent {consent_id} has expired.")
                return False

        if required_scope and consent_entry.consent_scope != required_scope:
            print(f"PrivacyProtocol: Consent {consent_id} scope ('{consent_entry.consent_scope}') does not match required scope ('{required_scope}').")
            return False

        print(f"PrivacyProtocol: Consent {consent_id} for user {user_id} is valid for scope '{consent_entry.consent_scope}'.")
        return True

    def revoke_consent(self, consent_id: str) -> bool:
        """
        Revokes a specific consent entry.
        """
        consent_entry = self.consent_ledger.get(consent_id)
        if consent_entry:
            consent_entry.revoke() # Uses the method from ConsentLedgerEntry
            # self.consent_ledger[consent_id] = consent_entry # Re-save if not pass-by-reference
            print(f"PrivacyProtocol: Consent {consent_id} successfully revoked.")
            return True
        print(f"PrivacyProtocol: Failed to revoke consent {consent_id}, entry not found.")
        return False

    def enforce_data_minimization(self, data_package, required_fields: list) -> dict:
        """
        Conceptual: Filters a data package to include only necessary fields for a specific purpose.
        This is a simplified example. Actual implementation would be more complex.
        """
        minimized_data = {}
        for field in required_fields:
            if field in data_package:
                minimized_data[field] = data_package[field]
            else:
                print(f"Warning: Required field '{field}' not in data package during minimization.")

        print(f"PrivacyProtocol: Data minimized. Original fields: {list(data_package.keys())}, Minimized fields: {list(minimized_data.keys())}")
        return minimized_data

# Example Usage (Conceptual)
if __name__ == '__main__':
    privacy_protocol = PrivacyProtocol()

    user1_id = "user007"
    data1_description = "User profile information (name, email)"
    scope1 = "account_creation"
    details1 = "This information will be used to create your EchoSphere account and for primary communication."

    # Simulate requesting and granting consent
    if privacy_protocol.request_consent(user1_id, data1_description, scope1, details1):
        consent_entry1 = privacy_protocol.grant_consent(user1_id, data1_description, scope1, details1, expiration_days=30)
        if consent_entry1:
            print(f"Consent granted with ID: {consent_entry1.consent_id}")

            # Verify consent
            is_valid = privacy_protocol.verify_consent(user1_id, consent_entry1.consent_id, required_scope=scope1)
            print(f"Consent validity for '{scope1}': {is_valid}")

            is_valid_wrong_scope = privacy_protocol.verify_consent(user1_id, consent_entry1.consent_id, required_scope="data_analysis")
            print(f"Consent validity for 'data_analysis': {is_valid_wrong_scope}")

            # Data Minimization Example
            full_data = {"name": "Jane Doe", "email": "jane@example.com", "age": 30, "location": "City X"}
            minimized_for_account = privacy_protocol.enforce_data_minimization(full_data, ["name", "email"])
            print(f"Minimized data for account creation: {minimized_for_account}")

            # Revoke consent
            # privacy_protocol.revoke_consent(consent_entry1.consent_id)
            # is_valid_after_revoke = privacy_protocol.verify_consent(user1_id, consent_entry1.consent_id, required_scope=scope1)
            # print(f"Consent validity after revocation: {is_valid_after_revoke}")
    else:
        print("User did not grant consent.")

    # Example of consent for a different activity
    data2_description = "Uploaded text documents for analysis"
    scope2 = "persona_trait_extraction_text"
    details2 = "Your written text will be analyzed by AI to identify linguistic patterns, tone, and sentiment to help build your Echo persona."
    if privacy_protocol.request_consent(user1_id, data2_description, scope2, details2):
        consent_entry2 = privacy_protocol.grant_consent(user1_id, data2_description, scope2, details2, expiration_days=365)
        if consent_entry2:
            print(f"Consent granted for text analysis with ID: {consent_entry2.consent_id}")
            is_valid_text_analysis = privacy_protocol.verify_consent(user1_id, consent_entry2.consent_id, scope2)
            print(f"Consent validity for '{scope2}': {is_valid_text_analysis}")

```
