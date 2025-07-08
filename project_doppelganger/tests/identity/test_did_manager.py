import unittest
from project_doppelganger.src.identity.did_manager import (
    DIDManager,
    DIDDocument,
    VerificationMethod,
    ServiceEndpoint
)

class TestDIDManagerConceptual(unittest.TestCase):

    def setUp(self):
        self.did_method = "dtest"
        self.did_manager = DIDManager(did_method_name=self.did_method)
        # Clear the registry for each test if it's a class variable
        DIDManager._did_registry = {}

    def test_create_persona_did_basic(self):
        persona_id = "persona_alpha"
        did_doc = self.did_manager.create_persona_did(persona_id)

        self.assertIsInstance(did_doc, DIDDocument)
        self.assertTrue(did_doc.id.startswith(f"did:{self.did_method}:"))
        self.assertEqual(did_doc.doppelgangerPersonaId, persona_id)
        self.assertEqual(did_doc.controller, did_doc.id) # Self-controlled by default

        self.assertTrue(len(did_doc.verificationMethod) >= 1)
        vm = did_doc.verificationMethod[0]
        self.assertTrue(vm.id.startswith(did_doc.id + "#"))
        self.assertEqual(vm.controller, did_doc.id)
        self.assertIsNotNone(vm.publicKeyMultibase)

        self.assertTrue(len(did_doc.authentication) >= 1)
        self.assertEqual(did_doc.authentication[0], vm.id)

        self.assertTrue(len(did_doc.service) >= 1)
        service = did_doc.service[0]
        self.assertTrue(service.id.startswith(did_doc.id + "#"))
        self.assertEqual(service.type, "DoppelgangerPersonaService")
        self.assertTrue(persona_id in str(service.serviceEndpoint))

    def test_create_persona_did_with_controller_and_key(self):
        controller_did_str = f"did:{self.did_method}:controller123"
        persona_id = "persona_beta"
        pub_key = "zMyPublicKeyForPersonaBeta"

        did_doc = self.did_manager.create_persona_did(
            persona_id,
            controller_did=controller_did_str,
            initial_public_key_multibase=pub_key
        )

        self.assertEqual(did_doc.controller, controller_did_str)
        self.assertEqual(did_doc.verificationMethod[0].publicKeyMultibase, pub_key)

    def test_resolve_did_found(self):
        persona_id = "persona_gamma"
        created_doc = self.did_manager.create_persona_did(persona_id)

        resolved_doc = self.did_manager.resolve_did(created_doc.id)
        self.assertIsNotNone(resolved_doc)
        self.assertEqual(resolved_doc.id, created_doc.id)
        self.assertEqual(resolved_doc.doppelgangerPersonaId, persona_id)

    def test_resolve_did_not_found(self):
        non_existent_did = f"did:{self.did_method}:does_not_exist_404"
        resolved_doc = self.did_manager.resolve_did(non_existent_did)
        self.assertIsNone(resolved_doc)

    def test_update_did_document_success(self):
        persona_id = "persona_delta"
        did_doc = self.did_manager.create_persona_did(persona_id)
        original_service_count = len(did_doc.service)

        # Modify the document
        new_service_id = f"{did_doc.id}#analytics"
        did_doc.service.append(ServiceEndpoint(
            id=new_service_id,
            type="AnalyticsService",
            serviceEndpoint="https://analytics.example.com/persona_delta"
        ))

        update_success = self.did_manager.update_did_document(did_doc)
        self.assertTrue(update_success)

        reresolved_doc = self.did_manager.resolve_did(did_doc.id)
        self.assertIsNotNone(reresolved_doc)
        if reresolved_doc: # Keep type checker happy
            self.assertEqual(len(reresolved_doc.service), original_service_count + 1)
            self.assertTrue(any(s.id == new_service_id for s in reresolved_doc.service))

    def test_update_did_document_not_found(self):
        non_existent_doc = DIDDocument(id=f"did:{self.did_method}:no_such_doc_for_update")
        update_success = self.did_manager.update_did_document(non_existent_doc)
        self.assertFalse(update_success)

    def test_conceptual_verify_signature_success(self):
        # Create a controller DID Doc
        controller_persona_id = "controller_for_sig_test"
        controller_key_multibase = "zControllerTestPublicKeyForSig"
        controller_doc = self.did_manager.create_persona_did(
            controller_persona_id,
            initial_public_key_multibase=controller_key_multibase
        )
        # The default key created is at #keys-1

        message = b"A message to be signed."
        mock_signature = b"a_valid_signature_for_the_message_and_key" # Conceptual

        is_valid = self.did_manager.verify_signature(
            did_doc_controller=controller_doc.id,
            message=message,
            signature=mock_signature,
            key_id_fragment="keys-1" # Refers to the default key created
        )
        self.assertTrue(is_valid)

    def test_conceptual_verify_signature_controller_not_found(self):
        is_valid = self.did_manager.verify_signature(
            did_doc_controller=f"did:{self.did_method}:non_existent_controller",
            message=b"test", signature=b"sig", key_id_fragment="keys-1"
        )
        self.assertFalse(is_valid)

    def test_conceptual_verify_signature_key_not_found_in_doc(self):
        controller_doc = self.did_manager.create_persona_did("controller_no_such_key")
        is_valid = self.did_manager.verify_signature(
            did_doc_controller=controller_doc.id,
            message=b"test", signature=b"sig", key_id_fragment="non_existent_key_fragment"
        )
        self.assertFalse(is_valid)

    def test_did_document_serialization_deserialization(self):
        persona_id = "persona_json"
        original_doc = self.did_manager.create_persona_did(persona_id, controller_did="did:example:controller")
        original_doc.service.append(ServiceEndpoint(id=f"{original_doc.id}#s2", type="TestService", serviceEndpoint="http://test.com"))

        doc_dict = original_doc.to_dict()
        doc_json = original_doc.to_json() # Test JSON string conversion too

        self.assertIsInstance(doc_json, str)
        loaded_from_json_dict = json.loads(doc_json) # Convert back to dict to compare with from_dict

        rehydrated_doc_from_dict = DIDDocument.from_dict(doc_dict)
        rehydrated_doc_from_json = DIDDocument.from_dict(loaded_from_json_dict)

        self.assertEqual(rehydrated_doc_from_dict.id, original_doc.id)
        self.assertEqual(rehydrated_doc_from_dict.controller, original_doc.controller)
        self.assertEqual(rehydrated_doc_from_dict.doppelgangerPersonaId, persona_id)
        self.assertEqual(len(rehydrated_doc_from_dict.verificationMethod), len(original_doc.verificationMethod))
        self.assertEqual(rehydrated_doc_from_dict.verificationMethod[0].id, original_doc.verificationMethod[0].id)
        self.assertEqual(len(rehydrated_doc_from_dict.service), len(original_doc.service))
        self.assertEqual(rehydrated_doc_from_dict.service[1].type, "TestService") # Check added service

        self.assertEqual(rehydrated_doc_from_json.id, original_doc.id) # Verify consistency from JSON string path


if __name__ == '__main__':
    unittest.main()
