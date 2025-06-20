# echosystem/phase1/ai_persona_analysis/analysis_data_structures.py
import uuid
from typing import List, Dict, Any, Optional

class RawAnalysisFeatures:
    """
    Stores intermediate features extracted by different AI models before consolidation.
    This structure can be flexible based on the types of analysis performed.
    """
    def __init__(self, user_id: str, data_package_ref: str):
        self.feature_id: str = str(uuid.uuid4())
        self.user_id: str = user_id
        self.data_package_ref: str = data_package_ref # Reference to the original UserDataPackage
        self.features_by_modality: Dict[str, Any] = {} # e.g., {'text': text_features, 'audio': audio_features}
        self.timestamps: Dict[str, str] = {} # To track when features were extracted

    def add_features(self, modality: str, features: Dict[str, Any], timestamp: str):
        """Adds features for a specific modality."""
        self.features_by_modality[modality] = features
        self.timestamps[modality] = timestamp
        print(f"RawAnalysisFeatures: Added {modality} features for {self.user_id}.")

    def get_features(self, modality: str) -> Optional[Dict[str, Any]]:
        """Retrieves features for a specific modality."""
        return self.features_by_modality.get(modality)

    def __repr__(self) -> str:
        return (f"RawAnalysisFeatures(feature_id={self.feature_id}, user_id={self.user_id}, "
                f"modalities={list(self.features_by_modality.keys())})")

class ExtractedTraitCandidate:
    """
    Represents a potential trait identified by AI, pending user review.
    """
    def __init__(self,
                 trait_name: str,
                 evidence_snippets: List[str],
                 confidence_score: float,
                 origin_model: str,
                 trait_category: str, # e.g., Linguistic, Emotional, Philosophical, InteractionStyle
                 user_id: str,
                 data_source_refs: List[str] # List of data_package_ref that contributed to this trait
                 ):
        if not all([trait_name, evidence_snippets, origin_model, trait_category, user_id, data_source_refs]):
            raise ValueError("Core fields for ExtractedTraitCandidate must be provided.")
        if not (0.0 <= confidence_score <= 1.0):
            raise ValueError("Confidence score must be between 0.0 and 1.0.")

        self.trait_id: str = str(uuid.uuid4())
        self.user_id: str = user_id
        self.trait_name: str = trait_name
        self.evidence_snippets: List[str] = evidence_snippets # Direct quotes or references to data segments
        self.confidence_score: float = confidence_score # AI's confidence in this trait
        self.origin_model: str = origin_model # Which AI model/pipeline stage suggested this
        self.trait_category: str = trait_category
        self.data_source_refs: List[str] = data_source_refs
        self.status: str = "candidate" # Becomes 'confirmed', 'rejected', 'modified' after user review
        self.feedback_notes: Optional[str] = None

    def __repr__(self) -> str:
        return (f"ExtractedTraitCandidate(trait_id={self.trait_id}, name='{self.trait_name}', "
                f"category='{self.trait_category}', confidence={self.confidence_score:.2f}, status='{self.status}')")


class PersonaKnowledgeGraph:
    """
    Represents the Persona Knowledge Graph (PKG) for a user.
    This is a conceptual class; actual implementation would use a graph database client.
    """
    def __init__(self, user_id: str, graph_db_client=None):
        self.pkg_id: str = str(uuid.uuid4())
        self.user_id: str = user_id
        self.graph_db_client = graph_db_client # Placeholder for Neo4j, Neptune client etc.
        self.nodes: Dict[str, Any] = {} # Simplified: node_id -> {label: 'User', properties: {name: 'X'}}
        self.edges: List[Dict[str, Any]] = [] # Simplified: {from_node: id, to_node: id, type: 'HAS_TRAIT', properties: {}}
        print(f"PersonaKnowledgeGraph initialized for user {self.user_id}.")
        self._add_user_node()

    def _add_user_node(self):
        """Adds the central user node to the PKG."""
        user_node_id = f"user_{self.user_id}"
        self.nodes[user_node_id] = {"label": "User", "properties": {"user_id": self.user_id}}
        print(f"PKG: Added User node: {user_node_id}")

    def add_trait_candidate(self, trait_candidate: ExtractedTraitCandidate) -> bool:
        """
        Adds an ExtractedTraitCandidate to the PKG.
        In a real graph DB, this would create/merge nodes and relationships.
        """
        if not isinstance(trait_candidate, ExtractedTraitCandidate):
            print("PKG Error: Invalid trait_candidate object.")
            return False

        trait_node_id = f"trait_{trait_candidate.trait_id}"
        self.nodes[trait_node_id] = {
            "label": "TraitCandidate",
            "properties": {
                "name": trait_candidate.trait_name,
                "category": trait_candidate.trait_category,
                "confidence": trait_candidate.confidence_score,
                "origin_model": trait_candidate.origin_model,
                "status": trait_candidate.status
            }
        }
        # Link User to TraitCandidate
        self.edges.append({
            "from_node": f"user_{self.user_id}",
            "to_node": trait_node_id,
            "type": "HAS_CANDIDATE_TRAIT",
            "properties": {"confidence": trait_candidate.confidence_score}
        })
        print(f"PKG: Added TraitCandidate node '{trait_candidate.trait_name}' and linked to user.")

        # Conceptual: Link trait to evidence snippets (could be nodes or properties)
        for i, evidence in enumerate(trait_candidate.evidence_snippets):
            evidence_node_id = f"evidence_{trait_candidate.trait_id}_{i}"
            self.nodes[evidence_node_id] = {
                "label": "Evidence",
                "properties": {"snippet": evidence, "source_refs": trait_candidate.data_source_refs}
            }
            self.edges.append({
                "from_node": trait_node_id,
                "to_node": evidence_node_id,
                "type": "SUPPORTED_BY"
            })
        print(f"PKG: Added {len(trait_candidate.evidence_snippets)} evidence nodes for trait '{trait_candidate.trait_name}'.")
        return True

    def update_trait_status(self, trait_id: str, new_status: str, user_feedback: Optional[str] = None) -> bool:
        """
        Updates the status of a trait in the PKG (e.g., 'confirmed', 'rejected').
        """
        trait_node_id = f"trait_{trait_id}" # Assuming trait_id is the ExtractedTraitCandidate.trait_id
        if trait_node_id in self.nodes and self.nodes[trait_node_id]['label'] in ["TraitCandidate", "ConfirmedTrait"]:
            self.nodes[trait_node_id]['properties']['status'] = new_status
            if new_status == "ConfirmedTrait": # Change label if confirmed
                 self.nodes[trait_node_id]['label'] = "ConfirmedTrait"
            if user_feedback:
                self.nodes[trait_node_id]['properties']['user_feedback'] = user_feedback

            # Update relationship from user if status changes significantly
            for edge in self.edges:
                if edge["to_node"] == trait_node_id and edge["from_node"] == f"user_{self.user_id}":
                    if new_status == "ConfirmedTrait":
                        edge["type"] = "HAS_CONFIRMED_TRAIT"
                    elif new_status == "rejected":
                        edge["type"] = "HAS_REJECTED_TRAIT" # Or remove the edge
                    break
            print(f"PKG: Updated trait {trait_id} to status '{new_status}'.")
            return True
        print(f"PKG Error: Trait {trait_id} not found for status update.")
        return False

    def get_graph_summary(self) -> Dict[str, Any]:
        """Returns a simple summary of the graph."""
        return {
            "user_id": self.user_id,
            "node_count": len(self.nodes),
            "edge_count": len(self.edges),
            "trait_candidates": [n['properties']['name'] for n_id, n in self.nodes.items() if n['label'] == 'TraitCandidate'],
            "confirmed_traits": [n['properties']['name'] for n_id, n in self.nodes.items() if n['label'] == 'ConfirmedTrait']
        }

# Example Usage
if __name__ == '__main__':
    # RawAnalysisFeatures Example
    raw_features = RawAnalysisFeatures(user_id="user001", data_package_ref="pkg_abc123")
    raw_features.add_features("text", {"sentiment": 0.5, "topics": ["AI", "ethics"]}, "2023-10-26T10:00:00Z")
    print(raw_features)

    # ExtractedTraitCandidate Example
    try:
        trait_cand = ExtractedTraitCandidate(
            user_id="user001",
            trait_name="Inquisitive Nature",
            evidence_snippets=["User asked 'Why is the sky blue?'", "User researched 'Quantum Physics basics'"],
            confidence_score=0.85,
            origin_model="TextAnalysisModuleV2",
            trait_category="Intellectual",
            data_source_refs=["pkg_abc123", "pkg_def456"]
        )
        print(trait_cand)
    except ValueError as e:
        print(f"Error creating ExtractedTraitCandidate: {e}")

    # PersonaKnowledgeGraph Example
    pkg = PersonaKnowledgeGraph(user_id="user001") # In real scenario, pass graph_db_client

    if 'trait_cand' in locals(): # Check if trait_cand was created
        pkg.add_trait_candidate(trait_cand)

        # Simulate another trait
        trait_cand2 = ExtractedTraitCandidate(
            user_id="user001",
            trait_name="Cautious Optimism",
            evidence_snippets=["'It might work, but we need to test thoroughly.'"],
            confidence_score=0.70,
            origin_model="SentimentAnalysisModule",
            trait_category="Emotional",
            data_source_refs=["pkg_ghi789"]
        )
        pkg.add_trait_candidate(trait_cand2)

        print("\nPKG Summary Before User Review:")
        print(pkg.get_graph_summary())

        # Simulate user confirming one trait and rejecting another
        pkg.update_trait_status(trait_cand.trait_id, "ConfirmedTrait", "User agrees, finds this very representative.")
        pkg.update_trait_status(trait_cand2.trait_id, "rejected", "User feels this is not accurate.")

        print("\nPKG Summary After User Review:")
        print(pkg.get_graph_summary())

```
