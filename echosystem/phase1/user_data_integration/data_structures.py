# echosystem/phase1/user_data_integration/data_structures.py
import datetime

class UserDataPackage:
    """
    A temporary, encrypted container holding raw user data.
    """
    def __init__(self, user_id: str, data_type: str, source: str, raw_data_encrypted: bytes, consent_token: str):
        if not all([user_id, data_type, source, raw_data_encrypted, consent_token]):
            raise ValueError("All fields must be provided for UserDataPackage.")

        self.user_id: str = user_id
        self.data_type: str = data_type  # 'text', 'audio', 'video', etc.
        self.source: str = source  # 'upload', 'api_link_gmail', 'api_link_twitter', etc.
        self.raw_data_encrypted: bytes = raw_data_encrypted # Encrypted data
        self.consent_token: str = consent_token # Links to ConsentLedgerEntry
        self.timestamp: str = datetime.datetime.now().isoformat()
        self.package_id: str = self._generate_package_id()

    def _generate_package_id(self) -> str:
        """Generates a unique ID for the package."""
        import uuid
        return str(uuid.uuid4())

    def __repr__(self) -> str:
        return (f"UserDataPackage(package_id={self.package_id}, user_id={self.user_id}, "
                f"data_type='{self.data_type}', source='{self.source}', "
                f"timestamp='{self.timestamp}')")


class ConsentLedgerEntry:
    """
    A record detailing the scope and duration of consent for each piece of data or data processing activity.
    In a real system, this might be stored on a private blockchain or an immutable database.
    """
    def __init__(self, user_id: str, data_hash: str, consent_scope: str, consent_description: str, expiration_date: datetime.datetime = None):
        if not all([user_id, data_hash, consent_scope, consent_description]):
            raise ValueError("User ID, data hash, consent scope, and description must be provided.")

        self.consent_id: str = self._generate_consent_id()
        self.user_id: str = user_id
        self.data_hash: str = data_hash # Hash of raw_data (or a reference to it) to ensure integrity and link consent to specific data
        self.consent_scope: str = consent_scope  # e.g., "persona_creation_phase1", "voice_analysis_module_X", "text_summary_feature"
        self.consent_description: str = consent_description # Human-readable description of what is being consented to
        self.timestamp: str = datetime.datetime.now().isoformat()
        self.expiration_date: str = expiration_date.isoformat() if expiration_date else None
        self.revocation_status: bool = False
        self.version: int = 1

    def _generate_consent_id(self) -> str:
        """Generates a unique ID for the consent entry."""
        import uuid
        return str(uuid.uuid4())

    def revoke(self):
        """Marks this consent as revoked."""
        self.revocation_status = True
        self.timestamp = datetime.datetime.now().isoformat() # Update timestamp on modification
        self.version +=1
        print(f"Consent {self.consent_id} for user {self.user_id} regarding '{self.consent_description}' has been revoked.")

    def __repr__(self) -> str:
        return (f"ConsentLedgerEntry(consent_id={self.consent_id}, user_id={self.user_id}, "
                f"scope='{self.consent_scope}', revoked={self.revocation_status}, version={self.version})")

# Example Usage (Conceptual)
if __name__ == '__main__':
    # UserDataPackage Example
    encrypted_sample_data = b"some_encrypted_bytes_data" # Placeholder
    consent_token_example = "consent_abc123"

    try:
        package = UserDataPackage(user_id="user001",
                                  data_type="text",
                                  source="direct_upload",
                                  raw_data_encrypted=encrypted_sample_data,
                                  consent_token=consent_token_example)
        print(package)
    except ValueError as e:
        print(f"Error creating UserDataPackage: {e}")

    # ConsentLedgerEntry Example
    data_hash_example = "hash_of_original_data_xyz" # Placeholder

    try:
        consent_entry = ConsentLedgerEntry(user_id="user001",
                                           data_hash=data_hash_example,
                                           consent_scope="persona_creation_text_analysis",
                                           consent_description="Allow analysis of uploaded text for persona trait extraction.",
                                           expiration_date=datetime.datetime.now() + datetime.timedelta(days=365))
        print(consent_entry)

        # Simulate revoking consent
        # consent_entry.revoke()
        # print(consent_entry)

    except ValueError as e:
        print(f"Error creating ConsentLedgerEntry: {e}")
