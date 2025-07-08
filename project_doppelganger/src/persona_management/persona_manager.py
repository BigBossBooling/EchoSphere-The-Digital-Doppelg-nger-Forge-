import json
import os
from typing import Dict, Any, Optional, List

from .persona_registry import PersonaRegistry, PersonaMetadata
from project_doppelganger.src.persona_modeling.behavioral_model import BehavioralModel
from project_doppelganger.src.ai_vcpu_core import AIVCPU, AIVCPUConfig # For type hinting and config loading

# Conceptual path for storing serialized BehavioralModel objects
BEHAVIORAL_MODELS_STORAGE_PATH = "data/behavioral_models/"

class PersonaManager:
    """
    Manages multiple AI personas, including their metadata, behavioral models,
    and configurations for AI-vCPU interaction.
    """
    def __init__(self, registry: PersonaRegistry, vcpu_instance: AIVCPU,
                 models_storage_path: str = BEHAVIORAL_MODELS_STORAGE_PATH):
        self.registry = registry
        self.vcpu = vcpu_instance # Shared AIVCPU instance
        self.models_storage_path = models_storage_path

        # In-memory cache for active/loaded BehavioralModels
        self._active_behavioral_models: Dict[str, BehavioralModel] = {}

        # Conceptual: Pre-defined AIVCPU configuration profiles
        self._aivcpu_config_profiles: Dict[str, AIVCPUConfig] = {
            "default": AIVCPUConfig(), # Default from ai_vcpu_core
            "lm_focused_interactive": AIVCPUConfig(num_general_cores=1, default_language_modeler_cores=2, default_fusion_cores=0, default_memory_cores=1),
            "balanced_empathetic": AIVCPUConfig(num_general_cores=2, default_language_modeler_cores=1, default_fusion_cores=1, default_memory_cores=1, specialized_core_configs=[]), # let defaults fill
        }

        # Conceptually ensure storage path exists
        # if not os.path.exists(self.models_storage_path):
        #     try:
        #         os.makedirs(self.models_storage_path)
        #         print(f"PersonaManager: Created behavioral models storage at {self.models_storage_path}")
        #     except OSError as e:
        #         print(f"Error creating PersonaManager models storage directory {self.models_storage_path}: {e}")

    def _get_bm_file_path(self, persona_id: str, version: Optional[int] = None) -> str:
        # Sanitize persona_id for filename (e.g., replace colons)
        safe_persona_id = persona_id.replace(":", "_")
        filename = f"bm_{safe_persona_id}"
        if version is not None:
            filename += f"_v{version}"
        filename += ".json"
        return os.path.join(self.models_storage_path, filename)

    def _save_behavioral_model(self, model: BehavioralModel) -> bool:
        """Conceptually saves a BehavioralModel to storage."""
        # For simulation, we're not actually writing files.
        # file_path = self._get_bm_file_path(model.persona_id, model.version)
        # try:
        #     data_to_save = asdict(model) # BehavioralModel needs to be convertible to dict
        #     with open(file_path, 'w') as f:
        #         json.dump(data_to_save, f, indent=2)
        #     print(f"CONCEPTUAL MANAGER: BehavioralModel for '{model.persona_id}' v{model.version} saved.")
        #     return True
        # except IOError as e:
        #     print(f"  Error saving BehavioralModel for '{model.persona_id}': {e}")
        #     return False
        print(f"CONCEPTUAL MANAGER: BehavioralModel for '{model.persona_id}' v{model.version} 'saved' (in-memory simulation).")
        return True # Simulate success

    def _load_behavioral_model(self, persona_id: str, version: Optional[int] = None) -> Optional[BehavioralModel]:
        """
        Conceptually loads a BehavioralModel from storage.
        If version is None, tries to load the version specified in PersonaMetadata or latest.
        """
        # For simulation, we won't actually load from files.
        # If it's in active_behavioral_models and version matches (or version is None), return it.
        # This simulates a cache and avoids "re-loading" what's already active.
        if persona_id in self._active_behavioral_models:
            cached_model = self._active_behavioral_models[persona_id]
            if version is None or cached_model.version == version:
                print(f"CONCEPTUAL MANAGER: Returning active BehavioralModel for '{persona_id}' v{cached_model.version}.")
                return cached_model

        # metadata = self.registry.get_persona_metadata(persona_id)
        # if not metadata or not metadata.behavioral_model_ref: # behavioral_model_ref might be the filename or key
        #     print(f"  No metadata or model reference for persona '{persona_id}'. Cannot load model.")
        #     return None
        #
        # file_path_to_load = metadata.behavioral_model_ref # Assuming ref is the path or can be resolved to it
        # if version is not None and "_v" not in file_path_to_load: # If ref is generic and version is specific
        #    file_path_to_load = self._get_bm_file_path(persona_id, version)

        # try:
        #     with open(file_path_to_load, 'r') as f:
        #         data = json.load(f)
        #         # BehavioralModel needs a from_dict classmethod
        #         model = BehavioralModel.from_dict(data) # This needs to be implemented in BehavioralModel
        #         print(f"CONCEPTUAL MANAGER: BehavioralModel for '{model.persona_id}' v{model.version} loaded from {file_path_to_load}.")
        #         return model
        # except FileNotFoundError:
        #     print(f"  BehavioralModel file not found at {file_path_to_load} for persona '{persona_id}'.")
        # except Exception as e:
        #     print(f"  Error loading BehavioralModel for '{persona_id}' from {file_path_to_load}: {e}")

        print(f"CONCEPTUAL MANAGER: No BehavioralModel found in storage for '{persona_id}' (v{version if version else 'any'}). Simulating fresh.")
        return None # Simulate not found if not in active cache for this conceptual test

    def create_persona(
        self,
        persona_id: str,
        persona_name: Optional[str] = None,
        human_subject_id: Optional[str] = None,
        description: Optional[str] = None,
        initial_behavioral_model: Optional[BehavioralModel] = None,
        aivcpu_profile_name: Optional[str] = "default",
        tags: Optional[List[str]] = None
        ) -> Optional[PersonaMetadata]:
        """
        Creates a new persona: registers metadata, initializes and saves behavioral model.
        """
        print(f"CONCEPTUAL MANAGER: Creating persona '{persona_id}' ({persona_name})...")
        if self.registry.get_persona_metadata(persona_id):
            print(f"  Error: Persona ID '{persona_id}' already exists in registry.")
            return None

        bm = initial_behavioral_model if initial_behavioral_model else BehavioralModel(persona_id=persona_id)
        if not self._save_behavioral_model(bm): # Save initial model (conceptual)
            print(f"  Error: Could not save initial behavioral model for '{persona_id}'.")
            return None # Should not happen in pure simulation

        metadata = PersonaMetadata(
            persona_id=persona_id,
            human_subject_id=human_subject_id,
            persona_name=persona_name or persona_id,
            description=description,
            behavioral_model_ref=self._get_bm_file_path(persona_id, bm.version), # Store ref to conceptual file
            aivcpu_config_profile_name=aivcpu_profile_name,
            tags=tags or []
        )

        if self.registry.register_persona(metadata):
            self._active_behavioral_models[persona_id] = bm # Cache it
            print(f"  Persona '{persona_id}' created successfully.")
            return metadata
        else:
            print(f"  Error: Failed to register metadata for '{persona_id}'.")
            # Conceptually, might need to clean up saved behavioral model if registration fails.
            return None

    def get_active_persona_instance(self, persona_id: str) -> Optional[BehavioralModel]:
        """
        Gets an active (loaded) BehavioralModel for a persona.
        If not active, attempts to load it from conceptual storage.
        """
        if persona_id in self._active_behavioral_models:
            return self._active_behavioral_models[persona_id]

        # Try to load if not active
        model = self._load_behavioral_model(persona_id)
        if model:
            self._active_behavioral_models[persona_id] = model
            return model

        print(f"  Persona '{persona_id}' not found or behavioral model could not be loaded.")
        return None

    def update_persona_behavioral_model(self, persona_id: str, updated_model: BehavioralModel) -> bool:
        """Updates the behavioral model for an existing persona and saves it."""
        metadata = self.registry.get_persona_metadata(persona_id)
        if not metadata:
            print(f"  Error: Persona '{persona_id}' not found in registry for model update.")
            return False
        if persona_id != updated_model.persona_id:
             print(f"  Error: Mismatched persona ID in model update ('{updated_model.persona_id}' vs registry '{persona_id}').")
             return False

        if self._save_behavioral_model(updated_model):
            metadata.behavioral_model_ref = self._get_bm_file_path(persona_id, updated_model.version)
            metadata.version = updated_model.version # Sync metadata version with model if appropriate
            metadata.last_updated_timestamp = time.time()
            self.registry.register_persona(metadata) # Re-register to update ref and timestamp
            self._active_behavioral_models[persona_id] = updated_model # Update active cache
            print(f"  Behavioral model for '{persona_id}' updated to v{updated_model.version}.")
            return True
        return False

    def get_aivcpu_config_for_persona(self, persona_id: str) -> Optional[AIVCPUConfig]:
        """
        Gets the AIVCPU configuration profile associated with a persona.
        The AIVCPU itself is shared, but this config could be used to
        dynamically adjust its behavior or resource allocation for this persona's tasks.
        """
        metadata = self.registry.get_persona_metadata(persona_id)
        if metadata and metadata.aivcpu_config_profile_name:
            profile = self._aivcpu_config_profiles.get(metadata.aivcpu_config_profile_name)
            if profile:
                return profile
            else:
                print(f"  Warning: AIVCPU profile '{metadata.aivcpu_config_profile_name}' not found for persona '{persona_id}'. Using default.")
        return self._aivcpu_config_profiles.get("default")


    def unload_persona(self, persona_id: str):
        """Removes persona's behavioral model from active memory (conceptual)."""
        if persona_id in self._active_behavioral_models:
            # Potentially save any final changes before unloading if model is dirty
            # self._save_behavioral_model(self._active_behavioral_models[persona_id])
            del self._active_behavioral_models[persona_id]
            print(f"CONCEPTUAL MANAGER: Persona '{persona_id}' unloaded from active memory.")


# Example Usage:
if __name__ == "__main__":
    from project_doppelganger.src.persona_modeling.behavioral_model import PersonalityTrait, TraitScore # For demo

    # Setup
    mock_registry = PersonaRegistry() # In-memory for demo

    # Mock AIVCPU for manager init (not heavily used in this conceptual manager's direct ops)
    mock_vcpu = MagicMock(spec=AIVCPU)
    mock_vcpu.config = AIVCPUConfig() # Give it a config for CSL name access if ever needed

    manager = PersonaManager(registry=mock_registry, vcpu_instance=mock_vcpu)

    print("--- Persona Manager Demo ---")

    # 1. Create Persona "Charlie"
    print("\nCreating Persona 'Charlie'...")
    charlie_bm = BehavioralModel(persona_id="charlie001")
    charlie_bm.update_trait(PersonalityTrait.CONSCIENTIOUSNESS, 0.8, 0.9)
    charlie_meta = manager.create_persona(
        persona_id="charlie001",
        persona_name="Charlie Concierge",
        description="A highly organized and efficient persona.",
        initial_behavioral_model=charlie_bm,
        aivcpu_profile_name="lm_focused_interactive",
        tags=["efficient", "concierge"]
    )
    assert charlie_meta is not None
    if charlie_meta:
        print(f"Charlie's AIVCPU profile: {charlie_meta.aivcpu_config_profile_name}")

    # 2. Create Persona "Dana"
    print("\nCreating Persona 'Dana'...")
    dana_meta = manager.create_persona(
        persona_id="dana002",
        persona_name="Dana Dialogue",
        description="An empathetic and talkative persona.",
        aivcpu_profile_name="balanced_empathetic",
        tags=["empathetic", "chatty"]
    ) # Uses default BM initially
    assert dana_meta is not None

    # 3. Get active persona instance for Charlie
    print("\nGetting active instance for Charlie...")
    active_charlie_bm = manager.get_active_persona_instance("charlie001")
    assert active_charlie_bm is not None
    if active_charlie_bm:
        print(f"Charlie's (active) Conscientiousness: {active_charlie_bm.get_trait_value(PersonalityTrait.CONSCIENTIOUSNESS)}")
        assert active_charlie_bm.get_trait_value(PersonalityTrait.CONSCIENTIOUSNESS) == 0.8

    # 4. Simulate loading Dana (not active yet, so should be "loaded")
    print("\nGetting instance for Dana (first time, conceptual load)...")
    active_dana_bm = manager.get_active_persona_instance("dana002")
    assert active_dana_bm is not None # A new default BM should have been created if not loaded
    if active_dana_bm :
         print(f"Dana's (loaded) persona ID: {active_dana_bm.persona_id}")
         # Update Dana's model
         active_dana_bm.update_trait(PersonalityTrait.EXTRAVERSION, 0.85, 0.9)
         manager.update_persona_behavioral_model("dana002", active_dana_bm)

    # 5. Re-get Dana to ensure update is reflected
    print("\nRe-getting instance for Dana (should be active and updated)...")
    re_active_dana_bm = manager.get_active_persona_instance("dana002")
    assert re_active_dana_bm is not None
    if re_active_dana_bm:
        print(f"Dana's (updated) Extraversion: {re_active_dana_bm.get_trait_value(PersonalityTrait.EXTRAVERSION)}")
        assert re_active_dana_bm.get_trait_value(PersonalityTrait.EXTRAVERSION) == 0.85
        assert re_active_dana_bm.version > 1 # Check version incremented

    # 6. Get AIVCPU config for personas
    charlie_vcpu_conf = manager.get_aivcpu_config_for_persona("charlie001")
    dana_vcpu_conf = manager.get_aivcpu_config_for_persona("dana002")
    default_vcpu_conf = manager.get_aivcpu_config_for_persona("non_existent_persona_id_for_default_config")

    assert charlie_vcpu_conf is not None and charlie_vcpu_conf.default_language_modeler_cores == 2 # lm_focused_interactive
    assert dana_vcpu_conf is not None and dana_vcpu_conf.num_general_cores == 2 # balanced_empathetic
    assert default_vcpu_conf is not None and default_vcpu_conf.num_general_cores == manager._aivcpu_config_profiles["default"].num_general_cores

    print(f"\nCharlie's AIVCPU config: GeneralCores={charlie_vcpu_conf.num_general_cores}, LMCores={charlie_vcpu_conf.default_language_modeler_cores}")
    print(f"Dana's AIVCPU config: GeneralCores={dana_vcpu_conf.num_general_cores}, LMCores={dana_vcpu_conf.default_language_model_er_cores}")


    # 7. Unload a persona
    manager.unload_persona("charlie001")
    assert "charlie001" not in manager._active_behavioral_models
    # Trying to get it again would trigger a conceptual "load"
    reloaded_charlie_bm = manager.get_active_persona_instance("charlie001")
    assert reloaded_charlie_bm is not None # Should simulate loading again
    # In this conceptual model, the reloaded one will be a fresh default because file I/O is skipped.
    # A real test would mock file reads/writes.

    print("\nPersonaManager demo finished.")

# Need MagicMock for the __main__ block if run directly
if __name__ == "__main__":
    from unittest.mock import MagicMock
    # (The rest of the __main__ block from above)
    from project_doppelganger.src.persona_modeling.behavioral_model import PersonalityTrait, TraitScore
    mock_registry = PersonaRegistry()
    mock_vcpu = MagicMock(spec=AIVCPU)
    mock_vcpu.config = AIVCPUConfig()
    manager = PersonaManager(registry=mock_registry, vcpu_instance=mock_vcpu)
    print("--- Persona Manager Demo ---")
    charlie_bm = BehavioralModel(persona_id="charlie001")
    charlie_bm.update_trait(PersonalityTrait.CONSCIENTIOUSNESS, 0.8, 0.9)
    charlie_meta = manager.create_persona("charlie001", "Charlie Concierge", initial_behavioral_model=charlie_bm, aivcpu_profile_name="lm_focused_interactive")
    assert charlie_meta is not None
    dana_meta = manager.create_persona("dana002", "Dana Dialogue", aivcpu_profile_name="balanced_empathetic")
    assert dana_meta is not None
    active_charlie_bm = manager.get_active_persona_instance("charlie001")
    assert active_charlie_bm is not None and active_charlie_bm.get_trait_value(PersonalityTrait.CONSCIENTIOUSNESS) == 0.8
    active_dana_bm = manager.get_active_persona_instance("dana002")
    assert active_dana_bm is not None
    active_dana_bm.update_trait(PersonalityTrait.EXTRAVERSION, 0.85, 0.9)
    manager.update_persona_behavioral_model("dana002", active_dana_bm)
    re_active_dana_bm = manager.get_active_persona_instance("dana002")
    assert re_active_dana_bm is not None and re_active_dana_bm.get_trait_value(PersonalityTrait.EXTRAVERSION) == 0.85
    charlie_vcpu_conf = manager.get_aivcpu_config_for_persona("charlie001")
    assert charlie_vcpu_conf is not None and charlie_vcpu_conf.default_language_modeler_cores == 2
    manager.unload_persona("charlie001")
    print("\nPersonaManager demo finished (with direct run).")
