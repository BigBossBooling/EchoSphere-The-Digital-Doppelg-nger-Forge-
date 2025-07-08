import json
import time
import hashlib
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional

from .consent import UserConsent # Relative import from within privacy_framework

# --- Conceptual Blockchain Data Structures ---

@dataclass
class BlockchainTransaction:
    """Represents a conceptual transaction on the EmPower1 Blockchain."""
    transaction_id: str
    timestamp: float = field(default_factory=time.time)
    transaction_type: str = "CONSENT_RECORD" # Could be other types in a real blockchain
    payload: Dict[str, Any] # For consent, this would be the UserConsent object as a dict
    # Conceptual signature of the payload (e.g., by the user or a trusted entity)
    signature: Optional[str] = None
    # Link to previous transaction for chaining (highly simplified)
    previous_transaction_id: Optional[str] = None

    def calculate_hash(self) -> str:
        """Calculates a conceptual hash for the transaction (excluding transaction_id itself for stability if id is random)."""
        # In a real blockchain, this would be a cryptographic hash of serialized content.
        block_string = json.dumps({
            "timestamp": self.timestamp,
            "type": self.transaction_type,
            "payload": self.payload, # Order of keys in dict matters for real hash
            "signature": self.signature,
            "previous_transaction_id": self.previous_transaction_id
        }, sort_keys=True).encode('utf-8')
        return hashlib.sha256(block_string).hexdigest()


# --- Conceptual Consent Chain Manager ---

class ConsentChainManager:
    """
    Conceptual placeholder for managing user consent records on a blockchain (e.g., EmPower1).
    Simulates submitting consent data as transactions and retrieving them.
    Does NOT implement actual blockchain interactions.
    """
    # In-memory list to simulate a very simple "blockchain" ledger for consent records
    _consent_ledger: List[BlockchainTransaction] = []
    _last_transaction_id: Optional[str] = None # To link transactions conceptually

    def __init__(self, blockchain_node_url: Optional[str] = None, api_key: Optional[str] = None):
        self.blockchain_node_url = blockchain_node_url or "http://conceptual.empower1.node/api"
        self.api_key = api_key # For authenticating with the conceptual node
        print(f"Conceptual ConsentChainManager initialized (EmPower1 Node: {self.blockchain_node_url})")

    async def record_consent_on_chain(
        self,
        user_consent: UserConsent,
        user_signature: Optional[str] = None # Conceptual signature of the consent data by the user
        ) -> Optional[str]:
        """
        Conceptually records a UserConsent object onto the blockchain.
        In a real system, this would involve:
        1. Serializing the UserConsent object.
        2. Having the user (or their agent) sign this data.
        3. Constructing a transaction with the signed data.
        4. Submitting the transaction to the blockchain network.
        5. Waiting for confirmation and getting a transaction ID.

        Returns:
            A conceptual transaction ID if successful, None otherwise.
        """
        print(f"CONCEPTUAL CHAIN: Recording consent for User '{user_consent.user_id}', Persona '{user_consent.persona_id}' (Version: {user_consent.version})")

        if not user_signature:
            # For simulation, if no signature provided, create a mock one based on consent data
            # This step would be CRITICAL in a real system and involve user's private keys.
            mock_signable_data = json.dumps(user_consent.to_dict(), sort_keys=True)
            user_signature = f"mock_sig_{hashlib.sha256(mock_signable_data.encode('utf-8')).hexdigest()[:16]}"
            print(f"  (Conceptual: Generated mock signature: {user_signature})")

        tx_payload = user_consent.to_dict()

        # Create a conceptual blockchain transaction
        tx = BlockchainTransaction(
            transaction_id=f"tx_{hashlib.sha256(str(time.time()).encode() + str(tx_payload).encode()).hexdigest()[:16]}",
            payload=tx_payload,
            signature=user_signature,
            previous_transaction_id=self._last_transaction_id # Link to previous for conceptual chain
        )

        # --- Simulate API call to EmPower1 Blockchain Node ---
        # async with httpx.AsyncClient() as client:
        #     try:
        #         # headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        #         # response = await client.post(f"{self.blockchain_node_url}/submit_transaction", json=asdict(tx), headers=headers)
        #         # response.raise_for_status()
        #         # response_data = response.json() # e.g., {"transaction_id": "...", "status": "pending/confirmed"}
        #         # confirmed_tx_id = response_data.get("transaction_id")

        #         # SIMULATED RESPONSE for conceptual demonstration:
        await asyncio.sleep(0.05) # Simulate network and processing time
        confirmed_tx_id = tx.transaction_id # In simulation, tx_id is confirmed immediately
        # --- End Simulate API call ---

        if confirmed_tx_id:
            self._consent_ledger.append(tx) # Add to our mock ledger
            self._last_transaction_id = confirmed_tx_id
            print(f"  SUCCESS (Conceptual Chain): Consent recorded. Transaction ID: {confirmed_tx_id}")
            return confirmed_tx_id
        else:
            print("  FAILURE (Conceptual Chain): Consent recording failed (simulated API error or no tx_id returned).")
            return None

    async def get_consent_history_for_user_persona(
        self,
        user_id: str,
        persona_id: str
        ) -> List[UserConsent]:
        """
        Conceptually retrieves the history of UserConsent objects for a specific user/persona
        by querying the (simulated) blockchain.
        In reality, this would query an indexed blockchain or use specific smart contract calls.
        """
        print(f"CONCEPTUAL CHAIN: Fetching consent history for User '{user_id}', Persona '{persona_id}'")

        history: List[UserConsent] = []
        # Iterate through the mock ledger and filter relevant transactions
        for tx in self._consent_ledger:
            if tx.transaction_type == "CONSENT_RECORD":
                consent_data = tx.payload
                if consent_data.get("user_id") == user_id and consent_data.get("persona_id") == persona_id:
                    try:
                        # Rehydrate the UserConsent object from the payload
                        user_consent_obj = UserConsent.from_dict(consent_data)
                        history.append(user_consent_obj)
                    except Exception as e:
                        print(f"  Warning (Conceptual Chain): Failed to parse UserConsent from transaction {tx.transaction_id}: {e}")

        # Sort by version or timestamp (UserConsent object has these)
        history.sort(key=lambda uc: uc.version)

        print(f"  Found {len(history)} consent versions (conceptually) on-chain for User '{user_id}', Persona '{persona_id}'.")
        return history

    def get_latest_consent_for_user_persona(
        self,
        user_id: str,
        persona_id: str
        ) -> Optional[UserConsent]:
        """Retrieves the latest version of consent from the conceptual chain."""
        history = await self.get_consent_history_for_user_persona(user_id, persona_id)
        return history[-1] if history else None


    def _get_ledger_for_testing(self) -> List[BlockchainTransaction]: # Helper for tests
        return self._consent_ledger

    def _clear_ledger_for_testing(self): # Helper for tests
        self._consent_ledger = []
        self._last_transaction_id = None


# Example Usage:
async def main_consent_chain_demo():
    from project_doppelganger.src.privacy_framework.data_attribute import DataCategory, Purpose # For demo

    manager = ConsentChainManager()

    print("\n--- Consent Chain Manager Demo ---")

    persona_id_demo = "ChainDemoPersona"
    user_id_demo = "chain_user_123"

    # 1. Create initial consent
    consent_v1 = UserConsent(user_id=user_id_demo, persona_id=persona_id_demo)
    consent_v1.grant(DataCategory.COMMUNICATION_CONTENT, Purpose.PERSONA_CREATION, "Initial onboarding consent")
    consent_v1.grant(DataCategory.VOICE_RECORDINGS, Purpose.VOICE_CLONING)

    print("\nRecording Consent v1 (conceptual)...")
    tx_id_v1 = await manager.record_consent_on_chain(consent_v1, user_signature="user_sig_for_v1")
    assert tx_id_v1 is not None

    # 2. Update consent (e.g., user revokes something)
    # Create a new UserConsent object or evolve the existing one.
    # For simulation, let's assume we fetch, modify, then re-record.
    # In a real system, the UserConsent object itself manages its versioning.
    consent_v2 = UserConsent.from_dict(consent_v1.to_dict()) # Create a copy to modify
    consent_v2.revoke(DataCategory.VOICE_RECORDINGS, Purpose.VOICE_CLONING, "User changed mind about voice cloning.")
    # Note: UserConsent.revoke() already increments version and updates timestamp.

    print(f"\nRecording Consent v2 (Persona '{consent_v2.persona_id}', Version {consent_v2.version}) (conceptual)...")
    tx_id_v2 = await manager.record_consent_on_chain(consent_v2, user_signature="user_sig_for_v2")
    assert tx_id_v2 is not None
    assert tx_id_v1 != tx_id_v2 # Transaction IDs should be different

    # 3. Retrieve consent history
    print(f"\nRetrieving consent history for User '{user_id_demo}', Persona '{persona_id_demo}'...")
    history = await manager.get_consent_history_for_user_persona(user_id_demo, persona_id_demo)

    assert len(history) == 2
    if len(history) == 2:
        print(f"  Retrieved {len(history)} versions from conceptual chain.")
        print(f"  Version {history[0].version}: Granted Voice Cloning = {history[0].get_consent_status(DataCategory.VOICE_RECORDINGS, Purpose.VOICE_CLONING)}")
        print(f"  Version {history[1].version}: Granted Voice Cloning = {history[1].get_consent_status(DataCategory.VOICE_RECORDINGS, Purpose.VOICE_CLONING)}")
        assert history[0].version < history[1].version
        assert history[0].get_consent_status(DataCategory.VOICE_RECORDINGS, Purpose.VOICE_CLONING) == "Granted" # ConsentStatus.GRANTED.value
        assert history[1].get_consent_status(DataCategory.VOICE_RECORDINGS, Purpose.VOICE_CLONING) == "Revoked" # ConsentStatus.REVOKED.value

    # 4. Get latest consent
    latest_consent = await manager.get_latest_consent_for_user_persona(user_id_demo, persona_id_demo)
    assert latest_consent is not None
    if latest_consent:
        print(f"\nLatest consent (Version {latest_consent.version}) for User '{user_id_demo}', Persona '{persona_id_demo}':")
        print(f"  Voice Cloning Status: {latest_consent.get_consent_status(DataCategory.VOICE_RECORDINGS, Purpose.VOICE_CLONING)}")
        assert latest_consent.version == consent_v2.version # Should be the last recorded version
        assert latest_consent.get_consent_status(DataCategory.VOICE_RECORDINGS, Purpose.VOICE_CLONING) == "Revoked"

    print("\nConsentChainManager demo finished.")

if __name__ == "__main__":
    import asyncio
    asyncio.run(main_consent_chain_demo())
