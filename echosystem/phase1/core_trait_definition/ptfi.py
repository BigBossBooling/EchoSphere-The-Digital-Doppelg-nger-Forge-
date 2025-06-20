# echosystem/phase1/core_trait_definition/ptfi.py

# Assuming access to PersonaKnowledgeGraph and ExtractedTraitCandidate
# This might require path adjustments or a more formal package structure for direct execution.
try:
    from echosystem.phase1.ai_persona_analysis.analysis_data_structures import PersonaKnowledgeGraph, ExtractedTraitCandidate
    # We'll also need UserRefinedTrait which will be in trait_refinement_data_structures.py
    # from .trait_refinement_data_structures import UserRefinedTrait
except ImportError:
    print("Warning: PTFI could not import PersonaKnowledgeGraph or ExtractedTraitCandidate. Using dummy classes.")
    class PersonaKnowledgeGraph:
        def __init__(self, user_id, graph_db_client=None): self.user_id = user_id
        def get_trait_candidates(self, user_id): return []
        def update_trait_status(self, trait_id, new_status, user_feedback=None): return True
        def add_user_defined_trait(self, user_id, trait_details): return True
    class ExtractedTraitCandidate: pass
    # class UserRefinedTrait: pass


class PersonaTraitFinalizationInterface:
    """
    Persona Trait Finalization Interface (PTFI): Backend logic for the UI
    where users review, modify, add, or delete traits identified by AI or defined by themselves.
    """

    def __init__(self, pkg_manager: PersonaKnowledgeGraph):
        """
        Initializes the PTFI.

        Args:
            pkg_manager: An instance or client to interact with the PersonaKnowledgeGraph.
                         This allows fetching candidates and pushing updates.
        """
        self.pkg_manager = pkg_manager
        print("PersonaTraitFinalizationInterface initialized.")

    def get_ai_trait_candidates_for_review(self, user_id: str) -> list[ExtractedTraitCandidate]:
        """
        Fetches AI-identified trait candidates for a user to review.
        These are traits with status 'candidate'.
        """
        print(f"PTFI: Fetching AI trait candidates for user {user_id} for review.")
        # In a real system, this would query the pkg_manager for traits with 'candidate' status
        # For this example, let's assume pkg_manager has a method like get_trait_candidates_by_status
        # candidates = self.pkg_manager.get_trait_candidates_by_status(user_id, status="candidate")

        # Mocking the response for now, assuming pkg_manager is the PKG itself for simplicity here
        candidates = [
            node['properties'] for node_id, node in self.pkg_manager.nodes.items()
            if node.get('label') == 'TraitCandidate' and node['properties'].get('status') == 'candidate'
            # and self.pkg_manager.user_id == user_id # This check would be implicit if pkg_manager is user-specific
        ]
        # We need to return actual ExtractedTraitCandidate objects or dicts that look like them
        # The current mock PKG stores properties directly.
        # Let's simulate creating mock ExtractedTraitCandidate-like dicts
        formatted_candidates = []
        for props in candidates:
            formatted_candidates.append({
                "trait_id": [nid for nid, n in self.pkg_manager.nodes.items() if n['properties'] == props][0].replace("trait_", ""), # hacky way to get ID
                "user_id": self.pkg_manager.user_id,
                "trait_name": props.get('name'),
                "evidence_snippets": ["mock evidence 1", "mock evidence 2"], # PKG mock doesn't store this link well yet
                "confidence_score": props.get('confidence'),
                "origin_model": props.get('origin_model'),
                "trait_category": props.get('category'),
                "data_source_refs": ["mock_ref1"],
                "status": props.get('status')
            })
        return formatted_candidates


    def submit_user_refinement(self, user_id: str, trait_id: str, user_decision: str,
                               user_feedback: str = None, modified_details: dict = None) -> bool:
        """
        Processes user's decision on a specific AI-identified trait.

        Args:
            user_id (str): The user making the refinement.
            trait_id (str): The ID of the trait being reviewed.
            user_decision (str): User's action ('confirm', 'reject', 'modify').
            user_feedback (str, optional): User's qualitative feedback or reasoning.
            modified_details (dict, optional): New details if 'modify' action is chosen.
                                               e.g., {"trait_name": "New Name", "user_description": "..."}

        Returns:
            bool: True if the refinement was processed successfully, False otherwise.
        """
        print(f"PTFI: User {user_id} submitted refinement for trait {trait_id}: {user_decision}.")

        # This should align with how PersonaKnowledgeGraph handles status updates
        new_status = ""
        if user_decision == 'confirm':
            new_status = "ConfirmedTrait" # Or 'confirmed' based on PKG's expected values
        elif user_decision == 'reject':
            new_status = "rejected"
        elif user_decision == 'modify':
            new_status = "ConfirmedTrait" # Modified traits are typically confirmed with changes
            # Logic to update trait details in PKG would be here or in pkg_manager
            print(f"PTFI: Modifying trait {trait_id} with details: {modified_details}")
            # This might involve updating properties of the trait node in PKG.
            # self.pkg_manager.update_trait_properties(trait_id, modified_details) # Conceptual
        else:
            print(f"PTFI: Invalid user decision '{user_decision}'.")
            return False

        success = self.pkg_manager.update_trait_status(trait_id, new_status, user_feedback)
        if success:
            print(f"PTFI: Trait {trait_id} status updated to '{new_status}' in PKG.")
        else:
            print(f"PTFI: Failed to update trait {trait_id} status in PKG.")
        return success

    def add_user_defined_trait(self, user_id: str, trait_name: str, trait_description: str, trait_category: str) -> bool:
        """
        Allows a user to define a new trait not identified by AI.

        Args:
            user_id (str): The user defining the trait.
            trait_name (str): Name of the new trait.
            trait_description (str): User's description of the trait.
            trait_category (str): Category of the trait.

        Returns:
            bool: True if the trait was added successfully, False otherwise.
        """
        print(f"PTFI: User {user_id} is adding a new custom trait: '{trait_name}'.")

        # This would create a new trait in the PKG, marked as user-defined and confirmed.
        # The structure should be compatible with ExtractedTraitCandidate but clearly marked as user-added.
        user_defined_trait_details = {
            "trait_name": trait_name,
            "user_description": trait_description, # Specific to user-defined
            "trait_category": trait_category,
            "origin_model": "UserDefined",
            "confidence_score": 1.0, # User is confident
            "status": "ConfirmedTrait", # User-defined traits are auto-confirmed
            "evidence_snippets": [trait_description] # Description itself is evidence
        }

        # The PKG needs a method to add such a trait, potentially creating a UserRefinedTrait structure directly
        # For now, adapting to a conceptual add_user_defined_trait on pkg_manager
        # success = self.pkg_manager.add_user_defined_trait(user_id, user_defined_trait_details)

        # Using a mock ExtractedTraitCandidate to fit into existing PKG add_trait_candidate for this example
        from echosystem.phase1.ai_persona_analysis.analysis_data_structures import ExtractedTraitCandidate
        try {
            temp_candidate_for_pkg = ExtractedTraitCandidate(
                user_id=user_id,
                trait_name=trait_name,
                evidence_snippets=[trait_description],
                confidence_score=1.0,
                origin_model="UserDefined",
                trait_category=trait_category,
                data_source_refs=["user_input"]
            )
            temp_candidate_for_pkg.status = "ConfirmedTrait" # Mark as confirmed
            # Manually set user_description if your ExtractedTraitCandidate can hold it, or PKG handles it
            # temp_candidate_for_pkg.user_description = trait_description

            success = self.pkg_manager.add_trait_candidate(temp_candidate_for_pkg)
            if success:
                 # Immediately update status to confirmed for user-defined traits
                self.pkg_manager.update_trait_status(temp_candidate_for_pkg.trait_id, "ConfirmedTrait", "User-defined trait.")
                print(f"PTFI: User-defined trait '{trait_name}' added to PKG for user {user_id}.")
            else:
                print(f"PTFI: Failed to add user-defined trait '{trait_name}' to PKG.")
            return success

        } except Exception as e:
            print(f"Error creating temporary candidate for user-defined trait: {e}")
            return False


# Example Usage (Conceptual)
if __name__ == '__main__':
    # Mock PersonaKnowledgeGraph setup (from analysis_data_structures.py example)
    from echosystem.phase1.ai_persona_analysis.analysis_data_structures import PersonaKnowledgeGraph, ExtractedTraitCandidate

    user_id_example = "user_review_001"
    mock_pkg = PersonaKnowledgeGraph(user_id=user_id_example)

    # Populate with some candidate traits for testing PTFI
    trait_cand1 = ExtractedTraitCandidate(
        user_id=user_id_example, trait_name="AI: Detailed Oriented",
        evidence_snippets=["Detail A from text", "Detail B"], confidence_score=0.9,
        origin_model="TextModule", trait_category="Cognitive", data_source_refs=["text1"]
    )
    trait_cand2 = ExtractedTraitCandidate(
        user_id=user_id_example, trait_name="AI: Appears Reserved",
        evidence_snippets=["Few words in chat", "Short answers"], confidence_score=0.65,
        origin_model="InteractionModule", trait_category="Interpersonal", data_source_refs=["chat1"]
    )
    mock_pkg.add_trait_candidate(trait_cand1) # Adds to PKG's internal 'nodes' list
    mock_pkg.add_trait_candidate(trait_cand2)

    print("\n--- Initial PKG Summary before PTFI ---")
    print(mock_pkg.get_graph_summary())

    ptfi_instance = PersonaTraitFinalizationInterface(pkg_manager=mock_pkg)

    # 1. Get traits for review
    print("\n--- Getting Traits for User Review ---")
    review_traits = ptfi_instance.get_ai_trait_candidates_for_review(user_id_example)
    print(f"Found {len(review_traits)} traits for review:")
    for i, trait_dict in enumerate(review_traits):
        # trait_dict is a dictionary representation of a trait candidate
        print(f"  {i+1}. ID: {trait_dict['trait_id']}, Name: {trait_dict['trait_name']} (Confidence: {trait_dict['confidence_score']:.2f})")

    # 2. Simulate user confirming one trait
    if review_traits:
        confirmed_trait_id = review_traits[0]['trait_id']
        print(f"\n--- User Confirming Trait ID: {confirmed_trait_id} ---")
        ptfi_instance.submit_user_refinement(user_id_example, confirmed_trait_id, 'confirm', "This is very accurate.")

    # 3. Simulate user rejecting another trait
    if len(review_traits) > 1:
        rejected_trait_id = review_traits[1]['trait_id']
        print(f"\n--- User Rejecting Trait ID: {rejected_trait_id} ---")
        ptfi_instance.submit_user_refinement(user_id_example, rejected_trait_id, 'reject', "I don't think this represents me.")

    # 4. Simulate user adding a custom trait
    print("\n--- User Adding Custom Trait ---")
    ptfi_instance.add_user_defined_trait(user_id_example, "Loves Outdoors", "Enjoys hiking, camping, and nature.", "Lifestyle")

    print("\n--- Final PKG Summary after PTFI interactions ---")
    print(mock_pkg.get_graph_summary())

```
