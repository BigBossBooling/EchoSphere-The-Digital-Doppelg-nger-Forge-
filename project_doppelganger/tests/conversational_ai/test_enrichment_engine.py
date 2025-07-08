import unittest
from unittest.mock import MagicMock, PropertyMock

from project_doppelganger.src.conversational_ai.enrichment_engine import EnrichmentEngine, EnrichedPrompt
from project_doppelganger.src.conversational_ai.ebo import EBOOutput
from project_doppelganger.src.persona_modeling.behavioral_model import (
    BehavioralModel, PersonalityTrait, TraitScore, Emotion, CommunicationStyleAspect, CurrentEmotionalState
)
from project_doppelganger.src.ai_vcpu_core import AIVCPU, AIVCPUConfig, CacheConfig, CacheEntry

class TestEnrichmentEngine(unittest.TestCase):

    def setUp(self):
        # Mock AIVCPU and its cache hierarchy
        self.mock_vcpu = MagicMock(spec=AIVCPU)
        self.mock_vcpu.config = AIVCPUConfig() # Use default config
        # Ensure CSL_ConversationHistory exists for the test, as EnrichmentEngine expects it by default
        if not any(c.name == "CSL_ConversationHistory" for c in self.mock_vcpu.config.context_specific_cache_layers_config):
            self.mock_vcpu.config.context_specific_cache_layers_config.insert(
                0, CacheConfig(name="CSL_ConversationHistory", size_kb=1024, latency_ns=2.0)
            )

        self.mock_vcpu.shared_cache_hierarchy = MagicMock()
        self.mock_vcpu.shared_cache_hierarchy.read_csl = MagicMock(return_value=None)

        # Mock holographic_memory.read() to return a CacheEntry-like object or None
        self.mock_vcpu.shared_cache_hierarchy.holographic_memory = MagicMock()
        self.mock_vcpu.shared_cache_hierarchy.holographic_memory.read = MagicMock(return_value=None)

        self.enricher = EnrichmentEngine(vcpu=self.mock_vcpu)

        # Mock BehavioralModel
        self.mock_bm = MagicMock(spec=BehavioralModel)
        self.mock_bm.persona_id = "TestPersona"
        self.mock_bm.base_traits = {
            PersonalityTrait.OPENNESS: TraitScore(0.8, 0.9),
            PersonalityTrait.EXTRAVERSION: TraitScore(0.7, 0.8),
            PersonalityTrait.FORMALITY: TraitScore(0.3, 0.9) # Informal
        }
        self.mock_bm.current_emotion = CurrentEmotionalState(dominant_emotion=Emotion.HAPPY, intensity=0.7)
        self.mock_bm.communication_style.aspects = {
            CommunicationStyleAspect.TONE: "Enthusiastic",
            CommunicationStyleAspect.PREFERRED_PHRASES: ["Let's go!", "Awesome!"]
        }
        # Mock methods of BehavioralModel
        self.mock_bm.get_trait_value = MagicMock(side_effect=lambda trait: self.mock_bm.base_traits.get(trait, TraitScore(0)).value if trait in self.mock_bm.base_traits else None)
        self.mock_bm.get_communication_aspect = MagicMock(side_effect=lambda aspect: self.mock_bm.communication_style.aspects.get(aspect))


        # Sample EBOOutput
        self.sample_ebo_output = EBOOutput(
            action_request="share_excitement",
            interaction_goal="energize_conversation",
            context_modifiers={
                "emotional_tone_hint": "very_positive",
                "llm_temperature_modifier": 0.2,
                "knowledge_domain_focus": "hobbies"
            },
            matched_rule_id="EXCITEMENT_RULE"
        )
        self.user_input = "That sounds fantastic!"
        self.convo_id = "convo_enrich_test_001"
        self.topic = "upcoming_event"

    def test_enrich_prompt_directive_basic_structure(self):
        enriched = self.enricher.enrich_prompt_directive(
            self.sample_ebo_output, self.mock_bm, self.user_input, self.convo_id, self.topic
        )
        self.assertIsInstance(enriched, EnrichedPrompt)
        self.assertIsInstance(enriched.system_prompt, str)
        self.assertIsInstance(enriched.user_prompt, str)
        self.assertIsInstance(enriched.llm_config_overrides, dict)
        self.assertIsInstance(enriched.metadata, dict)

        self.assertIn(self.mock_bm.persona_id, enriched.system_prompt)
        self.assertIn(self.sample_ebo_output.interaction_goal, enriched.system_prompt)
        self.assertIn(self.sample_ebo_output.action_request, enriched.system_prompt)
        self.assertIn(self.user_input, enriched.user_prompt)
        self.assertEqual(enriched.metadata["persona_id"], self.mock_bm.persona_id)
        self.assertEqual(enriched.metadata["conversation_id"], self.convo_id)

    def test_conversation_history_formatting_and_retrieval(self):
        history_data = [
            {"speaker": "User", "text": "Previous user message."},
            {"speaker": "TestPersona", "text": "Previous persona response."}
        ]
        self.mock_vcpu.shared_cache_hierarchy.read_csl.return_value = history_data

        enriched = self.enricher.enrich_prompt_directive(
            self.sample_ebo_output, self.mock_bm, self.user_input, self.convo_id, self.topic
        )
        self.mock_vcpu.shared_cache_hierarchy.read_csl.assert_called_once_with(
            self.mock_vcpu.config.context_specific_cache_layers_config[0].name, # Default CSL name
            f"history_{self.convo_id}"
        )
        self.assertIn("User: Previous user message.", enriched.user_prompt)
        self.assertIn("TestPersona: Previous persona response.", enriched.user_prompt)

    def test_relevant_facts_retrieval_and_formatting(self):
        facts_data = ["Fact A about event.", "Fact B related to TestPersona."]
        # Mock CacheEntry for facts
        mock_fact_entry = MagicMock(spec=CacheEntry)
        mock_fact_entry.data = facts_data
        self.mock_vcpu.shared_cache_hierarchy.holographic_memory.read.return_value = mock_fact_entry

        enriched = self.enricher.enrich_prompt_directive(
            self.sample_ebo_output, self.mock_bm, self.user_input, self.convo_id, self.topic
        )

        self.mock_vcpu.shared_cache_hierarchy.holographic_memory.read.assert_any_call(
            f"facts_{self.mock_bm.persona_id}_{self.topic.lower().replace(' ','_')}"
        )
        self.assertIn("Relevant information to consider:", enriched.system_prompt)
        self.assertIn("- Fact A about event.", enriched.system_prompt)
        self.assertIn("- Fact B related to TestPersona.", enriched.system_prompt)

    def test_no_facts_or_history(self):
        self.mock_vcpu.shared_cache_hierarchy.read_csl.return_value = None
        self.mock_vcpu.shared_cache_hierarchy.holographic_memory.read.return_value = None

        enriched = self.enricher.enrich_prompt_directive(
            self.sample_ebo_output, self.mock_bm, self.user_input, self.convo_id, self.topic
        )
        self.assertIn("This is the beginning of your conversation.", enriched.user_prompt)
        self.assertIn(f"no specific facts for '{self.topic}' were immediately retrieved", enriched.system_prompt)


    def test_persona_details_in_system_prompt(self):
        enriched = self.enricher.enrich_prompt_directive(
            self.sample_ebo_output, self.mock_bm, self.user_input, self.convo_id, self.topic
        )
        # Based on setUp mock_bm: high openness, high extraversion, informal
        self.assertIn("high openness, high extraversion, informal", enriched.system_prompt) # From _get_persona_trait_summary
        self.assertIn("happy (intensity: 0.70)", enriched.system_prompt) # From _get_persona_emotion_summary
        self.assertIn("tone: Enthusiastic, informal", enriched.system_prompt) # From _get_persona_communication_style_summary
                                                                    # (humor not high enough to trigger "often humorous")

    def test_ebo_context_modifiers_in_system_prompt_and_llm_config(self):
        enriched = self.enricher.enrich_prompt_directive(
            self.sample_ebo_output, self.mock_bm, self.user_input, self.convo_id, self.topic
        )
        self.assertIn("emotional tone that is: very_positive", enriched.system_prompt)
        self.assertIn("Focus your knowledge on: hobbies", enriched.system_prompt)
        self.assertEqual(enriched.llm_config_overrides.get("temperature_modifier"), 0.2)

        # Test with a different modifier
        self.sample_ebo_output.context_modifiers["response_length_hint"] = "brief"
        self.sample_ebo_output.context_modifiers["max_tokens_hint"] = 100

        enriched_modified = self.enricher.enrich_prompt_directive(
            self.sample_ebo_output, self.mock_bm, self.user_input, self.convo_id, self.topic
        )
        self.assertIn("Keep your response brief.", enriched_modified.system_prompt)
        self.assertEqual(enriched_modified.llm_config_overrides.get("max_tokens"), 100)


if __name__ == '__main__':
    unittest.main()
