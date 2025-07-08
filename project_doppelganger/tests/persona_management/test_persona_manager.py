import unittest
from unittest.mock import MagicMock, PropertyMock, patch

from project_doppelganger.src.persona_management.persona_manager import PersonaManager
from project_doppelganger.src.persona_management.persona_registry import PersonaRegistry, PersonaMetadata
from project_doppelganger.src.persona_modeling.behavioral_model import BehavioralModel, PersonalityTrait, TraitScore
from project_doppelganger.src.ai_vcpu_core import AIVCPU, AIVCPUConfig

class TestPersonaManager(unittest.TestCase):

    def setUp(self):
        self.mock_registry = MagicMock(spec=PersonaRegistry)
        self.mock_vcpu = MagicMock(spec=AIVCPU) # Not heavily used by manager itself, but passed

        self.manager = PersonaManager(registry=self.mock_registry, vcpu_instance=self.mock_vcpu)

        # Clear active models for each test
        self.manager._active_behavioral_models = {}

        # Mock the conceptual file I/O for BehavioralModel saving/loading
        # These patches will apply to all tests in this class
        self.patcher_save_bm = patch.object(PersonaManager, '_save_behavioral_model', return_value=True)
        self.patcher_load_bm = patch.object(PersonaManager, '_load_behavioral_model', return_value=None) # Default to not found

        self.mock_save_bm = self.patcher_save_bm.start()
        self.mock_load_bm = self.patcher_load_bm.start()

    def tearDown(self):
        self.patcher_save_bm.stop()
        self.patcher_load_bm.stop()


    def test_create_persona_success(self):
        persona_id = "p_new_001"
        persona_name = "New Persona One"

        self.mock_registry.get_persona_metadata.return_value = None # Not existing
        self.mock_registry.register_persona.return_value = True # Registration success

        initial_bm = BehavioralModel(persona_id=persona_id)
        initial_bm.update_trait(PersonalityTrait.OPENNESS, 0.6)

        metadata = self.manager.create_persona(
            persona_id=persona_id,
            persona_name=persona_name,
            initial_behavioral_model=initial_bm
        )

        self.assertIsNotNone(metadata)
        self.assertEqual(metadata.persona_id, persona_id)
        self.assertEqual(metadata.persona_name, persona_name)

        self.mock_registry.get_persona_metadata.assert_called_once_with(persona_id)
        self.mock_save_bm.assert_called_once_with(initial_bm) # Check if initial model was "saved"
        self.mock_registry.register_persona.assert_called_once()

        # Check if it's in active models
        self.assertIn(persona_id, self.manager._active_behavioral_models)
        self.assertEqual(self.manager._active_behavioral_models[persona_id], initial_bm)

    def test_create_persona_already_exists_in_registry(self):
        persona_id = "p_exists_002"
        self.mock_registry.get_persona_metadata.return_value = PersonaMetadata(persona_id=persona_id) # Already exists

        metadata = self.manager.create_persona(persona_id=persona_id, persona_name="Existing Persona")

        self.assertIsNone(metadata)
        self.mock_registry.get_persona_metadata.assert_called_once_with(persona_id)
        self.mock_save_bm.assert_not_called() # Should not attempt to save if creation fails early
        self.mock_registry.register_persona.assert_not_called()

    def test_create_persona_registry_registration_fails(self):
        persona_id = "p_reg_fail_003"
        self.mock_registry.get_persona_metadata.return_value = None # Not existing
        self.mock_registry.register_persona.return_value = False # Simulate registration failure

        metadata = self.manager.create_persona(persona_id=persona_id, persona_name="Reg Fail Persona")

        self.assertIsNone(metadata)
        self.mock_save_bm.assert_called_once() # Save is attempted before registration
        self.mock_registry.register_persona.assert_called_once()


    def test_get_active_persona_instance_already_active(self):
        persona_id = "p_active_004"
        active_bm = BehavioralModel(persona_id=persona_id)
        self.manager._active_behavioral_models[persona_id] = active_bm

        retrieved_bm = self.manager.get_active_persona_instance(persona_id)

        self.assertEqual(retrieved_bm, active_bm)
        self.mock_load_bm.assert_not_called() # Should not try to load if already active

    def test_get_active_persona_instance_load_success(self):
        persona_id = "p_load_005"
        loaded_bm = BehavioralModel(persona_id=persona_id, version=2)
        self.mock_load_bm.return_value = loaded_bm # Simulate successful load

        retrieved_bm = self.manager.get_active_persona_instance(persona_id)

        self.assertEqual(retrieved_bm, loaded_bm)
        self.mock_load_bm.assert_called_once_with(persona_id)
        self.assertIn(persona_id, self.manager._active_behavioral_models) # Should be cached now
        self.assertEqual(self.manager._active_behavioral_models[persona_id], loaded_bm)

    def test_get_active_persona_instance_load_fail(self):
        persona_id = "p_load_fail_006"
        self.mock_load_bm.return_value = None # Simulate load failure

        retrieved_bm = self.manager.get_active_persona_instance(persona_id)

        self.assertIsNone(retrieved_bm)
        self.mock_load_bm.assert_called_once_with(persona_id)
        self.assertNotIn(persona_id, self.manager._active_behavioral_models)

    def test_update_persona_behavioral_model_success(self):
        persona_id = "p_update_007"
        original_bm = BehavioralModel(persona_id=persona_id, version=1)
        self.manager._active_behavioral_models[persona_id] = original_bm # Make it active

        # Simulate metadata exists
        mock_metadata = PersonaMetadata(persona_id=persona_id, behavioral_model_ref="old_path_v1", version=1)
        self.mock_registry.get_persona_metadata.return_value = mock_metadata

        updated_bm = BehavioralModel(persona_id=persona_id, version=2) # New version
        updated_bm.update_trait(PersonalityTrait.AGREEABLENESS, 0.9)

        success = self.manager.update_persona_behavioral_model(persona_id, updated_bm)

        self.assertTrue(success)
        self.mock_save_bm.assert_called_once_with(updated_bm)
        self.mock_registry.register_persona.assert_called_once() # To update metadata ref and version

        # Check if metadata was updated (conceptually)
        updated_metadata_arg = self.mock_registry.register_persona.call_args[0][0]
        self.assertTrue(updated_metadata_arg.behavioral_model_ref.endswith(f"_v{updated_bm.version}.json"))
        self.assertEqual(updated_metadata_arg.version, updated_bm.version)

        self.assertEqual(self.manager._active_behavioral_models[persona_id], updated_bm)


    def test_update_persona_behavioral_model_persona_not_in_registry(self):
        persona_id = "p_update_no_reg_008"
        self.mock_registry.get_persona_metadata.return_value = None # Not in registry

        updated_bm = BehavioralModel(persona_id=persona_id)
        success = self.manager.update_persona_behavioral_model(persona_id, updated_bm)

        self.assertFalse(success)
        self.mock_save_bm.assert_not_called()

    def test_update_persona_behavioral_model_id_mismatch(self):
        persona_id_registry = "p_update_match_009"
        persona_id_model = "p_update_MISMATCH_009"
        self.mock_registry.get_persona_metadata.return_value = PersonaMetadata(persona_id=persona_id_registry)

        mismatched_bm = BehavioralModel(persona_id=persona_id_model)
        success = self.manager.update_persona_behavioral_model(persona_id_registry, mismatched_bm)
        self.assertFalse(success)


    def test_get_aivcpu_config_for_persona(self):
        persona_id = "p_cpu_conf_010"
        profile_name = "test_profile_for_cpu"

        # Mock metadata with a specific profile name
        mock_metadata = PersonaMetadata(persona_id=persona_id, aivcpu_config_profile_name=profile_name)
        self.mock_registry.get_persona_metadata.return_value = mock_metadata

        # Add a custom profile to the manager for testing
        test_cpu_config = AIVCPUConfig(num_general_cores=8)
        self.manager._aivcpu_config_profiles[profile_name] = test_cpu_config

        retrieved_config = self.manager.get_aivcpu_config_for_persona(persona_id)
        self.assertEqual(retrieved_config, test_cpu_config)

    def test_get_aivcpu_config_profile_not_found_uses_default(self):
        persona_id = "p_cpu_conf_011"
        profile_name_bad = "non_existent_profile"
        mock_metadata = PersonaMetadata(persona_id=persona_id, aivcpu_config_profile_name=profile_name_bad)
        self.mock_registry.get_persona_metadata.return_value = mock_metadata

        default_config = self.manager._aivcpu_config_profiles["default"]
        retrieved_config = self.manager.get_aivcpu_config_for_persona(persona_id)
        self.assertEqual(retrieved_config, default_config)

    def test_get_aivcpu_config_no_profile_in_metadata_uses_default(self):
        persona_id = "p_cpu_conf_012"
        mock_metadata = PersonaMetadata(persona_id=persona_id, aivcpu_config_profile_name=None) # No profile set
        self.mock_registry.get_persona_metadata.return_value = mock_metadata

        default_config = self.manager._aivcpu_config_profiles["default"]
        retrieved_config = self.manager.get_aivcpu_config_for_persona(persona_id)
        self.assertEqual(retrieved_config, default_config)


    def test_unload_persona(self):
        persona_id = "p_unload_013"
        active_bm = BehavioralModel(persona_id=persona_id)
        self.manager._active_behavioral_models[persona_id] = active_bm

        self.manager.unload_persona(persona_id)
        self.assertNotIn(persona_id, self.manager._active_behavioral_models)
        # self.mock_save_bm.assert_called_once_with(active_bm) # If save_on_unload was implemented


if __name__ == '__main__':
    unittest.main()
