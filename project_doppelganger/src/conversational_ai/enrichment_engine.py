from typing import Dict, Any, List, Optional

from project_doppelganger.src.ai_vcpu_core import AIVCPU # For type hinting, actual vCPU passed in
from project_doppelganger.src.persona_modeling.behavioral_model import BehavioralModel, CommunicationStyleAspect, PersonalityTrait
from .ebo import EBOOutput # Relative import

# Define a structure for what a "prompt" might look like after enrichment.
# This is highly dependent on the target LLM's API.
# For this conceptual engine, we'll build a dictionary of prompt components.
DEFAULT_SYSTEM_PROMPT_TEMPLATE = """\
You are {persona_name}, a digital persona embodying the personality of a specific human.
Your core characteristics are: {trait_summary}.
Your current emotional state is: {emotion_state}.
Your communication style is generally: {communication_style_summary}.
You are currently focused on the goal: "{interaction_goal}".
Your requested action is to: "{action_request}".
"""

DEFAULT_USER_PROMPT_TEMPLATE = """\
{conversation_history_formatted}
Current user input: {user_input_text}
"""

@dataclass
class EnrichedPrompt:
    system_prompt: str
    user_prompt: str # Or could be a list of messages for chat models
    llm_config_overrides: Dict[str, Any] = field(default_factory=dict) # e.g., temperature, max_tokens
    # Additional metadata that might be useful for the LLM adapter or post-processing
    metadata: Dict[str, Any] = field(default_factory=dict)


class EnrichmentEngine:
    """
    EchoSphere Enrichment Engine.
    Takes EBO output and other context to build a precise, actionable directive (prompt) for an LLM.
    """
    def __init__(self, vcpu: AIVCPU):
        self.vcpu = vcpu # Used to access cache hierarchy (L3, Holographic Memory, CSLs)

    def _format_conversation_history(self, history: List[Dict[str, str]], max_turns: int = 5) -> str:
        """Formats recent conversation history."""
        if not history:
            return "This is the beginning of your conversation."

        formatted_history = []
        for turn in history[-max_turns:]: # Get last N turns
            speaker = turn.get("speaker", "Unknown")
            text = turn.get("text", "")
            formatted_history.append(f"{speaker}: {text}")
        return "\n".join(formatted_history)

    def _get_relevant_facts(self, topic: Optional[str], persona_id: str, num_facts: int = 3) -> List[str]:
        """
        Conceptual retrieval of relevant facts from AI-vCPU's Holographic Memory or L3 cache.
        This would involve a search/query mechanism against the cached knowledge.
        """
        facts = []
        if topic:
            # Simulate cache read for topic-related facts
            # Key might be f"facts_{persona_id}_{topic}"
            cached_facts = self.vcpu.shared_cache_hierarchy.holographic_memory.read(f"facts_{persona_id}_{topic.lower().replace(' ','_')}")
            if cached_facts and isinstance(cached_facts.data, list):
                facts.extend(cached_facts.data[:num_facts])

        # Simulate reading some general persona facts
        general_persona_facts_key = f"persona_facts_{persona_id}_general"
        cached_general_facts = self.vcpu.shared_cache_hierarchy.holographic_memory.read(general_persona_facts_key)
        if cached_general_facts and isinstance(cached_general_facts.data, list):
            needed = num_facts - len(facts)
            if needed > 0:
                facts.extend(cached_general_facts.data[:needed])

        # Fallback if no specific facts found
        if not facts:
            facts.append(f"The persona {persona_id} is knowledgeable about many things but no specific facts for '{topic}' were immediately retrieved.")
        return facts

    def _get_persona_trait_summary(self, behavioral_model: BehavioralModel) -> str:
        summary_parts = []
        # Top 2-3 dominant traits
        sorted_traits = sorted(
            [(trait, score.value) for trait, score in behavioral_model.base_traits.items() if score.confidence > 0.5],
            key=lambda item: item[1],
            reverse=True # Assuming higher value = more dominant for this summary
        )
        for trait, value in sorted_traits[:3]:
            level = "high" if value > 0.65 else "moderate" if value > 0.35 else "low"
            summary_parts.append(f"{level} {trait.value.lower()}")

        if not summary_parts: return "generally balanced"
        return ", ".join(summary_parts)

    def _get_persona_communication_style_summary(self, behavioral_model: BehavioralModel) -> str:
        parts = []
        tone = behavioral_model.get_communication_aspect(CommunicationStyleAspect.TONE)
        if tone: parts.append(f"tone: {tone}")

        formality_score = behavioral_model.get_trait_value(PersonalityTrait.FORMALITY)
        if formality_score is not None:
            formality = "formal" if formality_score > 0.6 else "informal" if formality_score < 0.4 else "neutral in formality"
            parts.append(formality)

        humor_score = behavioral_model.get_trait_value(PersonalityTrait.HUMOROUSNESS)
        if humor_score is not None and humor_score > 0.6:
            parts.append("often humorous")

        if not parts: return "adaptive"
        return ", ".join(parts)


    def enrich_prompt_directive(
        self,
        ebo_output: EBOOutput,
        behavioral_model: BehavioralModel,
        user_input_text: str, # Current turn's user input
        conversation_id: str, # To fetch history from CSL
        topic: Optional[str] = None # Current conversation topic
    ) -> EnrichedPrompt:
        """
        Constructs an enriched prompt directive based on EBO output and other context.
        """
        # 1. Fetch Conversation History (from CSL via AI-vCPU)
        # CSL name for conversation history could be standardized, e.g., "CSL_ConversationHistory"
        history_csl_name = self.vcpu.config.context_specific_cache_layers_config[0].name # Assuming first CSL is for convo history
        raw_history = self.vcpu.shared_cache_hierarchy.read_csl(history_csl_name, f"history_{conversation_id}")
        conversation_history_list = raw_history if isinstance(raw_history, list) else []
        formatted_history = self._format_conversation_history(conversation_history_list)

        # 2. Fetch Relevant Facts (from Holographic Memory or L3 via AI-vCPU)
        relevant_facts = self._get_relevant_facts(topic, behavioral_model.persona_id)
        formatted_facts = "\nRelevant information to consider:\n- " + "\n- ".join(relevant_facts) if relevant_facts else ""

        # 3. Get Persona Details from BehavioralModel
        persona_name = behavioral_model.persona_id # Or a more display-friendly name if available
        trait_summary = self._get_persona_trait_summary(behavioral_model)
        emotion_state = f"{behavioral_model.current_emotion.dominant_emotion.value} (intensity: {behavioral_model.current_emotion.intensity:.2f})"
        comm_style_summary = self._get_persona_communication_style_summary(behavioral_model)

        # 4. Construct System Prompt
        system_prompt = DEFAULT_SYSTEM_PROMPT_TEMPLATE.format(
            persona_name=persona_name,
            trait_summary=trait_summary,
            emotion_state=emotion_state,
            communication_style_summary=comm_style_summary,
            interaction_goal=ebo_output.interaction_goal,
            action_request=ebo_output.action_request
        )
        # Add facts to system prompt if available
        if formatted_facts:
            system_prompt += f"\n{formatted_facts}"

        # Add any direct context modifiers from EBO to system prompt
        if ebo_output.context_modifiers.get("emotional_tone_hint"):
            system_prompt += f"\nAdopt an emotional tone that is: {ebo_output.context_modifiers['emotional_tone_hint']}."
        if ebo_output.context_modifiers.get("response_length_hint"):
            system_prompt += f"\nKeep your response {ebo_output.context_modifiers['response_length_hint']}."
        if ebo_output.context_modifiers.get("knowledge_domain_focus"):
             system_prompt += f"\nFocus your knowledge on: {ebo_output.context_modifiers['knowledge_domain_focus']}."


        # 5. Construct User Prompt (or message list for chat models)
        user_prompt = DEFAULT_USER_PROMPT_TEMPLATE.format(
            conversation_history_formatted=formatted_history,
            user_input_text=user_input_text
        )

        # 6. Prepare LLM config overrides from EBO context_modifiers
        llm_configs: Dict[str, Any] = {}
        if "llm_temperature_modifier" in ebo_output.context_modifiers:
            # This is a modifier, not absolute. Assumes a base temperature is known by LLM adapter.
            # Or, the adapter could interpret this. For now, store as is.
            llm_configs["temperature_modifier"] = ebo_output.context_modifiers["llm_temperature_modifier"]
        if "max_tokens_hint" in ebo_output.context_modifiers: # e.g. 50, 200
            llm_configs["max_tokens"] = ebo_output.context_modifiers["max_tokens_hint"]


        return EnrichedPrompt(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            llm_config_overrides=llm_configs,
            metadata={
                "ebo_matched_rule": ebo_output.matched_rule_id,
                "ebo_action_request": ebo_output.action_request,
                "ebo_interaction_goal": ebo_output.interaction_goal,
                "persona_id": behavioral_model.persona_id,
                "conversation_id": conversation_id
            }
        )

# Example Usage (requires mocks or a running AIVCPU and BehavioralModel)
if __name__ == "__main__":
    from project_doppelganger.src.ai_vcpu_core import AIVCPUConfig, CacheConfig # For mocking
    from project_doppelganger.src.persona_modeling.behavioral_model import Emotion, TraitScore
    import asyncio

    # --- Mocking ---
    class MockAIVCPUForEnricher:
        def __init__(self):
            self.config = AIVCPUConfig() # Uses default CSL names
            # Ensure CSL_ConversationHistory exists for the test
            if not any(c.name == "CSL_ConversationHistory" for c in self.config.context_specific_cache_layers_config):
                 self.config.context_specific_cache_layers_config.insert(0, CacheConfig(name="CSL_ConversationHistory", size_kb=1024, latency_ns=2.0))

            self.shared_cache_hierarchy = MagicMock(spec=CacheHierarchy) # from unittest.mock
            self.shared_cache_hierarchy.read_csl = MagicMock(return_value=None) # Default no history
            self.shared_cache_hierarchy.holographic_memory.read = MagicMock(return_value=None) # Default no facts

    # --- End Mocking ---

    # Need to use MagicMock from unittest.mock if running standalone
    from unittest.mock import MagicMock
    mock_vcpu_instance = MockAIVCPUForEnricher()

    enricher = EnrichmentEngine(vcpu=mock_vcpu_instance) # type: ignore

    # Sample EBO Output
    sample_ebo_output = EBOOutput(
        action_request="generate_empathetic_response",
        interaction_goal="build_rapport",
        context_modifiers={"emotional_tone_hint": "warm", "llm_temperature_modifier": -0.1},
        matched_rule_id="EMPATHY_RULE_XYZ"
    )

    # Sample Behavioral Model
    bm = BehavioralModel(persona_id="EnricherTestPersona")
    bm.update_trait(PersonalityTrait.AGREEABLENESS, 0.8, 0.9)
    bm.update_trait(PersonalityTrait.OPENNESS, 0.7, 0.8)
    bm.update_emotion(Emotion.HAPPY, 0.6)
    bm.update_communication_aspect(CommunicationStyleAspect.TONE, "Friendly")
    bm.add_preferred_phrase("That's interesting!")

    user_text = "I'm feeling a bit down today."
    convo_id = "convo123"
    current_topic = "user_wellbeing"

    # Mock cache returns for history and facts
    mock_vcpu_instance.shared_cache_hierarchy.read_csl.return_value = [
        {"speaker": "User", "text": "Hello there!"},
        {"speaker": "Persona", "text": "Hi! How are you?"}
    ]
    fact_cache_entry_mock = MagicMock() # Mocking CacheEntry
    fact_cache_entry_mock.data = ["Fact about wellbeing 1", "Fact about active listening 2"]
    mock_vcpu_instance.shared_cache_hierarchy.holographic_memory.read.return_value = fact_cache_entry_mock


    enriched_prompt = enricher.enrich_prompt_directive(
        sample_ebo_output, bm, user_text, convo_id, current_topic
    )

    print("--- Enriched Prompt ---")
    print("\n[System Prompt]")
    print(enriched_prompt.system_prompt)
    print("\n[User Prompt]")
    print(enriched_prompt.user_prompt)
    print("\n[LLM Config Overrides]")
    print(enriched_prompt.llm_config_overrides)
    print("\n[Metadata]")
    print(enriched_prompt.metadata)

    # Assertions (conceptual, for a real test these would be unittest assertions)
    assert "EnricherTestPersona" in enriched_prompt.system_prompt
    assert "high agreeableness" in enriched_prompt.system_prompt # From trait summary
    assert "happy (intensity: 0.60)" in enriched_prompt.system_prompt # From emotion
    assert "tone: Friendly" in enriched_prompt.system_prompt or "often humorous" in enriched_prompt.system_prompt # From comm style
    assert "build_rapport" in enriched_prompt.system_prompt # From EBO goal
    assert "generate_empathetic_response" in enriched_prompt.system_prompt # From EBO action
    assert "Fact about wellbeing 1" in enriched_prompt.system_prompt # From facts
    assert "User: Hello there!" in enriched_prompt.user_prompt # From history
    assert "Current user input: I'm feeling a bit down today." in enriched_prompt.user_prompt
    assert enriched_prompt.llm_config_overrides.get("temperature_modifier") == -0.1

    # Test with no facts / no history
    mock_vcpu_instance.shared_cache_hierarchy.read_csl.return_value = None
    mock_vcpu_instance.shared_cache_hierarchy.holographic_memory.read.return_value = None

    enriched_prompt_no_extras = enricher.enrich_prompt_directive(
        sample_ebo_output, bm, "New topic.", "convo456", "new_topic_no_facts"
    )
    print("\n--- Enriched Prompt (No History/Facts) ---")
    print("\n[System Prompt]")
    print(enriched_prompt_no_extras.system_prompt)
    assert "no specific facts for 'new_topic_no_facts' were immediately retrieved" in enriched_prompt_no_extras.system_prompt
    print("\n[User Prompt]")
    print(enriched_prompt_no_extras.user_prompt)
    assert "This is the beginning of your conversation." in enriched_prompt_no_extras.user_prompt


    print("\nEnrichmentEngine example finished.")
