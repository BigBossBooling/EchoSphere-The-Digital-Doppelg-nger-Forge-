import unittest
import time
from project_doppelganger.src.persona_management.persona_registry import PersonaRegistry, PersonaMetadata

class TestPersonaRegistry(unittest.TestCase):

    def setUp(self):
        self.registry = PersonaRegistry(storage_path="data/test_persona_registry/") # Use a test-specific path
        # Clear the internal registry for each test to ensure isolation
        self.registry._registry = {}
        # Note: Conceptual file I/O is mocked/skipped in PersonaRegistry for simulation,
        # so we don't need to worry about actual file cleanup here.

    def test_register_new_persona(self):
        meta = PersonaMetadata(persona_id="p1", persona_name="Persona One")
        success = self.registry.register_persona(meta)
        self.assertTrue(success)
        self.assertIn("p1", self.registry._registry)
        self.assertEqual(self.registry.get_persona_metadata("p1"), meta)

    def test_register_existing_persona_newer_version(self):
        meta_v1 = PersonaMetadata(persona_id="p1", persona_name="Persona One", version=1, description="Version 1")
        self.registry.register_persona(meta_v1)

        meta_v2 = PersonaMetadata(persona_id="p1", persona_name="Persona One Updated", version=2, description="Version 2")
        meta_v2.last_updated_timestamp = meta_v1.last_updated_timestamp + 10 # Ensure it's later
        success = self.registry.register_persona(meta_v2)

        self.assertTrue(success)
        retrieved = self.registry.get_persona_metadata("p1")
        self.assertIsNotNone(retrieved)
        if retrieved: # For type checker
            self.assertEqual(retrieved.version, 2)
            self.assertEqual(retrieved.description, "Version 2")
            self.assertEqual(retrieved.persona_name, "Persona One Updated")

    def test_register_existing_persona_older_or_same_version(self):
        meta_v2 = PersonaMetadata(persona_id="p1", persona_name="Persona One v2", version=2)
        self.registry.register_persona(meta_v2)

        # Try registering same version
        meta_v2_again = PersonaMetadata(persona_id="p1", persona_name="Persona One v2 Attempt 2", version=2)
        success_same_v = self.registry.register_persona(meta_v2_again)
        # Current logic: if version is not newer (<=), it doesn't update.
        self.assertFalse(success_same_v, "Registering same version should not cause an update by default.")
        retrieved_same = self.registry.get_persona_metadata("p1")
        self.assertEqual(retrieved_same.persona_name if retrieved_same else "", "Persona One v2")


        # Try registering older version
        meta_v1 = PersonaMetadata(persona_id="p1", persona_name="Persona One v1", version=1)
        success_older_v = self.registry.register_persona(meta_v1)
        self.assertFalse(success_older_v)
        retrieved_older = self.registry.get_persona_metadata("p1")
        self.assertEqual(retrieved_older.version if retrieved_older else 0, 2) # Should still be v2
        self.assertEqual(retrieved_older.persona_name if retrieved_older else "", "Persona One v2")


    def test_get_persona_metadata_found(self):
        meta = PersonaMetadata(persona_id="p_get", persona_name="GetMe")
        self.registry.register_persona(meta)
        retrieved = self.registry.get_persona_metadata("p_get")
        self.assertEqual(retrieved, meta)

    def test_get_persona_metadata_not_found(self):
        retrieved = self.registry.get_persona_metadata("p_not_exist")
        self.assertIsNone(retrieved)

    def test_list_persona_ids(self):
        self.registry.register_persona(PersonaMetadata(persona_id="p_list1"))
        self.registry.register_persona(PersonaMetadata(persona_id="p_list2"))
        ids = self.registry.list_persona_ids()
        self.assertIn("p_list1", ids)
        self.assertIn("p_list2", ids)
        self.assertEqual(len(ids), 2)

    def test_list_personas_no_filter(self):
        m1 = PersonaMetadata(persona_id="p_list_all1", tags=["test"])
        m2 = PersonaMetadata(persona_id="p_list_all2", tags=["another"])
        self.registry.register_persona(m1)
        self.registry.register_persona(m2)

        all_personas = self.registry.list_personas()
        self.assertEqual(len(all_personas), 2)
        self.assertIn(m1, all_personas)
        self.assertIn(m2, all_personas)

    def test_list_personas_with_tag_filter(self):
        m1 = PersonaMetadata(persona_id="p_tag1", tags=["alpha", "test"])
        m2 = PersonaMetadata(persona_id="p_tag2", tags=["beta", "sample"])
        m3 = PersonaMetadata(persona_id="p_tag3", tags=["alpha", "dev"])
        self.registry.register_persona(m1)
        self.registry.register_persona(m2)
        self.registry.register_persona(m3)

        alpha_personas = self.registry.list_personas(tag_filter="alpha")
        self.assertEqual(len(alpha_personas), 2)
        self.assertIn(m1, alpha_personas)
        self.assertIn(m3, alpha_personas)
        self.assertNotIn(m2, alpha_personas)

        beta_personas = self.registry.list_personas(tag_filter="beta")
        self.assertEqual(len(beta_personas), 1)
        self.assertIn(m2, beta_personas)

        non_existent_tag_personas = self.registry.list_personas(tag_filter="gamma")
        self.assertEqual(len(non_existent_tag_personas), 0)


    def test_remove_persona_found(self):
        meta = PersonaMetadata(persona_id="p_remove")
        self.registry.register_persona(meta)
        self.assertIsNotNone(self.registry.get_persona_metadata("p_remove"))

        success = self.registry.remove_persona("p_remove")
        self.assertTrue(success)
        self.assertIsNone(self.registry.get_persona_metadata("p_remove"))
        self.assertNotIn("p_remove", self.registry.list_persona_ids())

    def test_remove_persona_not_found(self):
        success = self.registry.remove_persona("p_remove_not_exist")
        self.assertFalse(success)

    def test_timestamps_on_register(self):
        current_time = time.time()
        time.sleep(0.01) # ensure time progresses slightly
        meta = PersonaMetadata(persona_id="p_time")

        # Check creation_timestamp is set on PersonaMetadata init
        self.assertTrue(meta.creation_timestamp >= current_time)
        self.assertTrue(meta.last_updated_timestamp >= current_time)
        initial_creation_ts = meta.creation_timestamp
        initial_updated_ts = meta.last_updated_timestamp

        time.sleep(0.01)
        self.registry.register_persona(meta)

        retrieved = self.registry.get_persona_metadata("p_time")
        self.assertIsNotNone(retrieved)
        if retrieved:
            # Creation timestamp should remain from initial object creation
            self.assertAlmostEqual(retrieved.creation_timestamp, initial_creation_ts, places=5)
            # Last_updated_timestamp should be set/updated by register_persona
            self.assertTrue(retrieved.last_updated_timestamp > initial_updated_ts)
            self.assertTrue(retrieved.last_updated_timestamp > initial_creation_ts)


if __name__ == '__main__':
    unittest.main()
