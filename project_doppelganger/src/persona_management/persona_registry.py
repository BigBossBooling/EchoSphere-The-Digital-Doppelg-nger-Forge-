import json
import os
import time
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, Optional, List

# Conceptual path for storing persona registry data
REGISTRY_STORAGE_PATH = "data/persona_registry/" # Could be a directory of files or a single DB file

@dataclass
class PersonaMetadata:
    """
    Stores metadata about a single AI persona.
    """
    persona_id: str # Unique identifier for the persona
    human_subject_id: Optional[str] = None # Identifier for the human this persona is based on
    persona_name: Optional[str] = None # Display name for the persona
    description: Optional[str] = None

    creation_timestamp: float = field(default_factory=time.time)
    last_updated_timestamp: float = field(default_factory=time.time)
    version: int = 1

    # Paths or references to key components (conceptual)
    behavioral_model_ref: Optional[str] = None # e.g., path to a serialized BehavioralModel file or DB key
    did_ref: Optional[str] = None # DID string for this persona
    # Add other relevant metadata: e.g., AIVCPU config profile, voice model ID
    voice_model_id_ref: Optional[str] = None
    aivcpu_config_profile_name: Optional[str] = None # Name of a pre-defined AIVCPU config profile

    tags: List[str] = field(default_factory=list) # For categorization or searching

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PersonaMetadata":
        # Basic dataclass field matching. More robust parsing might be needed for older versions.
        # For simplicity, direct field mapping is assumed.
        return cls(**data)


class PersonaRegistry:
    """
    Manages the storage and retrieval of PersonaMetadata.
    Conceptually, this could interact with a database or a file system.
    For this simulation, it will use an in-memory dictionary and conceptual file I/O.
    """
    def __init__(self, storage_path: str = REGISTRY_STORAGE_PATH):
        self.storage_path = storage_path
        self._registry: Dict[str, PersonaMetadata] = {} # In-memory cache/store

        # Conceptually ensure storage path exists
        # if not os.path.exists(self.storage_path):
        #     try:
        #         os.makedirs(self.storage_path)
        #         print(f"PersonaRegistry: Created storage directory at {self.storage_path}")
        #     except OSError as e:
        #         print(f"Error creating PersonaRegistry storage directory {self.storage_path}: {e}")
        # self._load_registry_from_storage() # Conceptual load on init

    def _get_persona_file_path(self, persona_id: str) -> str:
        return os.path.join(self.storage_path, f"persona_{persona_id.replace(':', '_')}.json")

    def _load_registry_from_storage(self):
        """Conceptual: Loads all persona metadata from the storage path."""
        print(f"CONCEPTUAL REGISTRY: Attempting to load personas from {self.storage_path}...")
        # if not os.path.isdir(self.storage_path):
        #     print(f"  Storage path {self.storage_path} is not a directory. No personas loaded.")
        #     return
        # for filename in os.listdir(self.storage_path):
        #     if filename.startswith("persona_") and filename.endswith(".json"):
        #         try:
        #             with open(os.path.join(self.storage_path, filename), 'r') as f:
        #                 data = json.load(f)
        #                 metadata = PersonaMetadata.from_dict(data)
        #                 self._registry[metadata.persona_id] = metadata
        #                 print(f"  Loaded persona '{metadata.persona_id}' from {filename}")
        #         except Exception as e:
        #             print(f"  Error loading persona from {filename}: {e}")
        print("  (Conceptual load complete - in-memory for simulation.)")


    def _save_persona_to_storage(self, metadata: PersonaMetadata):
        """Conceptual: Saves a single persona's metadata to storage."""
        # file_path = self._get_persona_file_path(metadata.persona_id)
        # try:
        #     with open(file_path, 'w') as f:
        #         json.dump(metadata.to_dict(), f, indent=2)
        #     print(f"CONCEPTUAL REGISTRY: Saved persona '{metadata.persona_id}' to {file_path}")
        # except IOError as e:
        #     print(f"  Error saving persona '{metadata.persona_id}' to {file_path}: {e}")
        pass # In-memory simulation doesn't write files

    def register_persona(self, metadata: PersonaMetadata) -> bool:
        """Registers a new persona or updates an existing one if versions match or new is higher."""
        if metadata.persona_id in self._registry:
            existing_meta = self._registry[metadata.persona_id]
            if metadata.version <= existing_meta.version:
                print(f"CONCEPTUAL REGISTRY: Persona '{metadata.persona_id}' version {metadata.version} is not newer than existing version {existing_meta.version}. Not updating.")
                return False # Or handle as an update if content differs but version is same

        metadata.last_updated_timestamp = time.time()
        self._registry[metadata.persona_id] = metadata
        self._save_persona_to_storage(metadata) # Conceptual save
        print(f"CONCEPTUAL REGISTRY: Persona '{metadata.persona_id}' (v{metadata.version}) registered/updated.")
        return True

    def get_persona_metadata(self, persona_id: str) -> Optional[PersonaMetadata]:
        # In a real system with file storage, might try to load from file if not in memory.
        return self._registry.get(persona_id)

    def list_persona_ids(self) -> List[str]:
        return list(self._registry.keys())

    def list_personas(self, tag_filter: Optional[str] = None) -> List[PersonaMetadata]:
        if not tag_filter:
            return list(self.registry.values())

        return [meta for meta in self._registry.values() if tag_filter in meta.tags]

    def remove_persona(self, persona_id: str) -> bool:
        if persona_id in self._registry:
            del self._registry[persona_id]
            # Conceptually delete from storage too
            # file_path = self._get_persona_file_path(persona_id)
            # if os.path.exists(file_path):
            #     try:
            #         os.remove(file_path)
            #         print(f"CONCEPTUAL REGISTRY: Removed persona file {file_path}")
            #     except OSError as e:
            #         print(f"  Error removing persona file {file_path}: {e}")
            print(f"CONCEPTUAL REGISTRY: Persona '{persona_id}' removed from registry.")
            return True
        print(f"CONCEPTUAL REGISTRY: Persona '{persona_id}' not found for removal.")
        return False

# Example Usage:
if __name__ == "__main__":
    registry = PersonaRegistry() # Uses in-memory for this example

    print("--- Persona Registry Demo ---")

    # 1. Create and register Persona Alpha
    meta_alpha = PersonaMetadata(
        persona_id="did:dgdblk:alpha_persona_123",
        human_subject_id="user_001",
        persona_name="Alpha Doppel",
        description="An early prototype persona, focused on helpfulness.",
        behavioral_model_ref="data/models/alpha_model_v1.pkl",
        did_ref="did:dgdblk:alpha_persona_123", # Same as persona_id in this case
        voice_model_id_ref="elevenlabs_voice_alpha",
        aivcpu_config_profile_name="standard_lm_focused",
        tags=["prototype", "helpful", "text_based"]
    )
    registry.register_persona(meta_alpha)

    # 2. Create and register Persona Beta
    meta_beta = PersonaMetadata(
        persona_id="did:dgdblk:beta_persona_456",
        human_subject_id="user_002",
        persona_name="Beta Companion",
        description="A more empathetic and conversational persona.",
        behavioral_model_ref="data/models/beta_model_v2.json",
        did_ref="did:dgdblk:beta_persona_456",
        voice_model_id_ref="coqui_voice_beta",
        aivcpu_config_profile_name="balanced_interaction",
        tags=["empathetic", "conversational"]
    )
    registry.register_persona(meta_beta)

    # 3. List all personas
    print("\nAll registered personas IDs:")
    for pid in registry.list_persona_ids():
        print(f"  - {pid}")
    assert len(registry.list_persona_ids()) == 2

    # 4. Get metadata for a specific persona
    print(f"\nMetadata for '{meta_alpha.persona_id}':")
    retrieved_alpha = registry.get_persona_metadata(meta_alpha.persona_id)
    assert retrieved_alpha is not None
    if retrieved_alpha:
        print(f"  Name: {retrieved_alpha.persona_name}")
        print(f"  Description: {retrieved_alpha.description}")
        print(f"  Tags: {retrieved_alpha.tags}")
        assert retrieved_alpha.persona_name == "Alpha Doppel"

    # 5. Update a persona (e.g., new version or details)
    if retrieved_alpha:
        retrieved_alpha.description = "An early prototype, now with enhanced Q&A capabilities."
        retrieved_alpha.version = 2
        retrieved_alpha.tags.append("q_and_a")
        registry.register_persona(retrieved_alpha) # Re-register to update

        updated_alpha = registry.get_persona_metadata(meta_alpha.persona_id)
        assert updated_alpha is not None
        if updated_alpha:
            print(f"\nUpdated description for Alpha: {updated_alpha.description}")
            assert updated_alpha.version == 2
            assert "q_and_a" in updated_alpha.tags

    # 6. Try to register older version (should be ignored by current logic)
    meta_alpha_v1_again = PersonaMetadata(persona_id=meta_alpha.persona_id, version=1, persona_name="Old Alpha Name")
    register_v1_success = registry.register_persona(meta_alpha_v1_again)
    assert not register_v1_success # Should fail or not update because version 1 <= existing version 2
    still_updated_alpha = registry.get_persona_metadata(meta_alpha.persona_id)
    assert still_updated_alpha is not None and still_updated_alpha.version == 2 # Ensure it wasn't overwritten by older version

    # 7. Remove a persona
    print(f"\nRemoving '{meta_beta.persona_id}'...")
    registry.remove_persona(meta_beta.persona_id)
    assert registry.get_persona_metadata(meta_beta.persona_id) is None
    assert len(registry.list_persona_ids()) == 1

    print("\nPersonaRegistry demo finished.")
