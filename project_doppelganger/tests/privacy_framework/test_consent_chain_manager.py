import unittest
import asyncio
from typing import List

from project_doppelganger.src.privacy_framework.consent_chain_manager import ConsentChainManager, BlockchainTransaction
from project_doppelganger.src.privacy_framework.consent import UserConsent, ConsentStatus
from project_doppelganger.src.privacy_framework.data_attribute import DataCategory, Purpose

class TestConsentChainManagerConceptual(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.manager = ConsentChainManager()
        # Clear the ledger for each test to ensure independence
        self.manager._clear_ledger_for_testing()

        self.user_id = "test_user_chain"
        self.persona_id = "test_persona_chain"

    async def test_record_consent_on_chain_success(self):
        consent_v1 = UserConsent(user_id=self.user_id, persona_id=self.persona_id)
        consent_v1.grant(DataCategory.COMMUNICATION_CONTENT, Purpose.PERSONA_CREATION)

        tx_id = await self.manager.record_consent_on_chain(consent_v1, "sig_v1")
        self.assertIsNotNone(tx_id)
        self.assertTrue(tx_id.startswith("tx_"))

        ledger: List[BlockchainTransaction] = self.manager._get_ledger_for_testing()
        self.assertEqual(len(ledger), 1)
        self.assertEqual(ledger[0].transaction_id, tx_id)
        self.assertEqual(ledger[0].payload["user_id"], self.user_id)
        self.assertEqual(ledger[0].payload["version"], consent_v1.version) # Should be 2 after grant
        self.assertEqual(ledger[0].signature, "sig_v1")
        self.assertIsNone(ledger[0].previous_transaction_id) # First transaction

    async def test_record_multiple_consents_chaining(self):
        consent_v1 = UserConsent(user_id=self.user_id, persona_id=self.persona_id)
        consent_v1.grant(DataCategory.WRITTEN_DOCUMENTS, Purpose.PERSONA_CREATION) # v2

        tx_id1 = await self.manager.record_consent_on_chain(consent_v1, "sig1")
        self.assertIsNotNone(tx_id1)

        consent_v2 = UserConsent.from_dict(consent_v1.to_dict()) # Copy
        consent_v2.grant(DataCategory.SOCIAL_MEDIA_POSTS, Purpose.PERSONA_CREATION) # v3 (relative to consent_v1's state)
                                                                              # UserConsent manages its own version.

        tx_id2 = await self.manager.record_consent_on_chain(consent_v2, "sig2")
        self.assertIsNotNone(tx_id2)
        self.assertNotEqual(tx_id1, tx_id2)

        ledger = self.manager._get_ledger_for_testing()
        self.assertEqual(len(ledger), 2)
        self.assertEqual(ledger[1].previous_transaction_id, tx_id1)
        self.assertEqual(ledger[1].payload["version"], consent_v2.version)


    async def test_get_consent_history_for_user_persona(self):
        # Record for target user/persona
        consent1_target = UserConsent(user_id=self.user_id, persona_id=self.persona_id)
        consent1_target.grant(DataCategory.USAGE_METADATA, Purpose.ANALYTICS_AND_IMPROVEMENT) # v2
        await self.manager.record_consent_on_chain(consent1_target)

        consent2_target = UserConsent.from_dict(consent1_target.to_dict())
        consent2_target.deny(DataCategory.USAGE_METADATA, Purpose.ANALYTICS_AND_IMPROVEMENT) # v3
        await self.manager.record_consent_on_chain(consent2_target)

        # Record for a different user/persona (should be ignored)
        other_consent = UserConsent(user_id="other_user", persona_id="other_persona")
        other_consent.grant(DataCategory.OTHER, Purpose.OTHER_SPECIFIED)
        await self.manager.record_consent_on_chain(other_consent)

        history = await self.manager.get_consent_history_for_user_persona(self.user_id, self.persona_id)
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0].version, consent1_target.version) # Sorted by version
        self.assertEqual(history[1].version, consent2_target.version)

        self.assertEqual(history[0].get_consent_status(DataCategory.USAGE_METADATA, Purpose.ANALYTICS_AND_IMPROVEMENT), ConsentStatus.GRANTED.value)
        self.assertEqual(history[1].get_consent_status(DataCategory.USAGE_METADATA, Purpose.ANALYTICS_AND_IMPROVEMENT), ConsentStatus.DENIED.value)

    async def test_get_consent_history_no_records_found(self):
        history = await self.manager.get_consent_history_for_user_persona("non_existent_user", "non_existent_persona")
        self.assertEqual(len(history), 0)

    async def test_get_latest_consent_for_user_persona(self):
        consent_v1 = UserConsent(user_id=self.user_id, persona_id=self.persona_id)
        consent_v1.grant(DataCategory.VOICE_RECORDINGS, Purpose.VOICE_CLONING) # v2
        await self.manager.record_consent_on_chain(consent_v1)

        time.sleep(0.01) # Ensure timestamps are different for versioning if UserConsent relied on it solely

        consent_v2 = UserConsent.from_dict(consent_v1.to_dict())
        consent_v2.revoke(DataCategory.VOICE_RECORDINGS, Purpose.VOICE_CLONING) # v3
        await self.manager.record_consent_on_chain(consent_v2)

        latest = await self.manager.get_latest_consent_for_user_persona(self.user_id, self.persona_id)
        self.assertIsNotNone(latest)
        if latest: # For type checker
            self.assertEqual(latest.version, consent_v2.version)
            self.assertEqual(latest.get_consent_status(DataCategory.VOICE_RECORDINGS, Purpose.VOICE_CLONING), ConsentStatus.REVOKED.value)

    async def test_get_latest_consent_no_records(self):
        latest = await self.manager.get_latest_consent_for_user_persona("no_user", "no_persona")
        self.assertIsNone(latest)

    async def test_conceptual_immutability_retrieval(self):
        # Immutability is simulated by always appending and rehydrating from stored payload.
        # If we retrieve a consent, modify it, and try to get it again without re-recording,
        # we should get the original version from the "ledger".

        consent_initial = UserConsent(user_id=self.user_id, persona_id=self.persona_id)
        consent_initial.grant(DataCategory.SYSTEM_INTERACTIONS, Purpose.SECURITY_AND_MONITORING) # v2
        await self.manager.record_consent_on_chain(consent_initial)

        retrieved_consent1 = await self.manager.get_latest_consent_for_user_persona(self.user_id, self.persona_id)
        self.assertIsNotNone(retrieved_consent1)
        if not retrieved_consent1: self.fail("retrieved_consent1 is None") # Guard

        # "Accidentally" modify the retrieved object locally
        retrieved_consent1.grant(DataCategory.ANONYMIZED_DATA, Purpose.RESEARCH_CONSENTED) # Now v3 locally

        # Retrieve again from manager - should still be the v2 from the "chain"
        retrieved_consent2 = await self.manager.get_latest_consent_for_user_persona(self.user_id, self.persona_id)
        self.assertIsNotNone(retrieved_consent2)
        if not retrieved_consent2: self.fail("retrieved_consent2 is None") # Guard

        self.assertEqual(retrieved_consent2.version, consent_initial.version) # Should be original version
        self.assertIsNone(retrieved_consent2.get_consent_status(DataCategory.ANONYMIZED_DATA, Purpose.RESEARCH_CONSENTED))


if __name__ == '__main__':
    unittest.main()
