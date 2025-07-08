import asyncio
import os # For GEMINI_API_KEY

# Core Doppelganger components
from project_doppelganger.src.privacy_framework.minimizer_engine import MinimizerEngine
from project_doppelganger.src.privacy_framework.consent import UserConsent, ConsentStatus # For creating sample consent
from project_doppelganger.src.privacy_framework.policy import PrivacyPolicy # For Minimizer
from project_doppelganger.src.privacy_framework.data_attribute import DataCategory, Purpose # For consent

from project_doppelganger.src.persona_modeling.behavioral_model import BehavioralModel, PersonalityTrait, TraitScore, Emotion
from project_doppelganger.src.persona_modeling.personality_extractor import PersonalityExtractor
# PersonalityExtractor needs AIVCPU, but for main loop, we might use a pre-built BehavioralModel

from project_doppelganger.src.ai_vcpu_core import AIVCPU, AIVCPUConfig
from project_doppelganger.src.conversational_ai.ebo import EBO, example_rules as ebo_example_rules
from project_doppelganger.src.conversational_ai.enrichment_engine import EnrichmentEngine
from project_doppelganger.src.conversational_ai.llm_interface import AbstractLLMAdapter, LLMResponse
from project_doppelganger.src.conversational_ai.gemini_adapter import GeminiAdapter
# from project_doppelganger.src.conversational_ai.openai_adapter import OpenAIAdapter # If implemented

# --- Global Variables / Configuration (Simplified for CLI app) ---
# In a real app, these would be managed more robustly (e.g., config files, dependency injection)

# 1. AI-vCPU (shared instance)
# Using a simpler config for the main loop example to reduce console output from vCPU init
vcpu_config_main = AIVCPUConfig(num_general_cores=1, default_language_modeler_cores=1,
                                default_vision_interpreter_cores=0, default_fusion_cores=0, default_memory_cores=0)
AIVCPU_INSTANCE = AIVCPU(config=vcpu_config_main)

# 2. Behavioral Model for the persona
# For this demo, we'll create a default one. In a real system, it would be loaded or built.
PERSONA_ID_MAIN = "Doppel основной" # "Doppel Prime" in Russian for fun
BEHAVIORAL_MODEL_MAIN = BehavioralModel(persona_id=PERSONA_ID_MAIN, adaptability_level=0.3)
# Initialize with some default traits for interesting interactions
BEHAVIORAL_MODEL_MAIN.update_trait(PersonalityTrait.OPENNESS, 0.7, 0.9)
BEHAVIORAL_MODEL_MAIN.update_trait(PersonalityTrait.EXTRAVERSION, 0.6, 0.8)
BEHAVIORAL_MODEL_MAIN.update_trait(PersonalityTrait.AGREEABLENESS, 0.75, 0.85)
BEHAVIORAL_MODEL_MAIN.update_trait(PersonalityTrait.HUMOROUSNESS, 0.6, 0.7)
BEHAVIORAL_MODEL_MAIN.update_trait(PersonalityTrait.FORMALITY, 0.4, 0.9) # Moderately informal
BEHAVIORAL_MODEL_MAIN.update_emotion(Emotion.NEUTRAL, 0.8) # Start neutral but alert

# 3. Privacy Framework components
# For simplicity, allow most things for persona creation/interaction in this demo consent
USER_CONSENT_MAIN = UserConsent(user_id="cli_user", persona_id=PERSONA_ID_MAIN)
USER_CONSENT_MAIN.grant(DataCategory.COMMUNICATION_CONTENT, Purpose.PERSONA_ADAPTATION)
USER_CONSENT_MAIN.grant(DataCategory.COMMUNICATION_CONTENT, Purpose.INTERACTION_PERSONALIZATION)
USER_CONSENT_MAIN.grant(DataCategory.PERSONAL_IDENTIFIABLE_INFORMATION, Purpose.INTERACTION_PERSONALIZATION) # Allow PII for personalization context
# Deny PII for Persona Creation explicitly (Minimizer should catch this if data is for that purpose)
USER_CONSENT_MAIN.deny(DataCategory.PERSONAL_IDENTIFIABLE_INFORMATION, Purpose.PERSONA_CREATION)

# Basic policy for minimizer (conceptual, MinimizerEngine uses it lightly for now)
PRIVACY_POLICY_MAIN = PrivacyPolicy("PPolicy_MainDemo", "1.0")
MINIMIZER_ENGINE_MAIN = MinimizerEngine(policy=PRIVACY_POLICY_MAIN)

# 4. Conversational AI components
EBO_MAIN = EBO(rules=ebo_example_rules()) # Use the example rules from ebo.py
ENRICHMENT_ENGINE_MAIN = EnrichmentEngine(vcpu=AIVCPU_INSTANCE)

# 5. LLM Adapter (Choose one)
# Attempt to use Gemini by default, can be overridden by environment or config later
LLM_ADAPTER_MAIN: AbstractLLMAdapter = GeminiAdapter(api_key=os.getenv("GEMINI_API_KEY"))
# llm_adapter = OpenAIAdapter(api_key=os.getenv("OPENAI_API_KEY")) # If you had an OpenAI adapter

# --- Core Interaction Loop Function ---

async def process_user_turn(
    user_input: str,
    conversation_id: str,
    current_behavioral_model: BehavioralModel,
    current_user_consent: UserConsent
    ) -> Optional[str]:
    """
    Orchestrates the processing of a single user turn.
    """
    print(f"\n[User]: {user_input}")

    # 1. Minimizer Engine: Process raw input for PII and apply consent/policy
    # For interaction personalization, we might allow PII to pass through if consented for context,
    # but it should be stripped before sending to a generic LLM if not needed or consented for LLM processing.
    # The MinimizerEngine's process_data is conceptual. Here, we'll assume it prepares data for EBO.
    # Let's say the purpose for this stage is "INTERACTION_PERSONALIZATION"
    minimized_input_text = MINIMIZER_ENGINE_MAIN.process_data(
        raw_data=user_input,
        data_category_hint=DataCategory.COMMUNICATION_CONTENT, # User input is comms content
        user_consent=current_user_consent,
        purpose=Purpose.INTERACTION_PERSONALIZATION # Purpose for this processing step
    )
    # In a real scenario, minimizer would also return structured PII info if needed by EBO/Enricher under consent.
    # For now, minimized_input_text is what EBO sees.
    print(f"  [Minimizer -> EBO Input Text]: {minimized_input_text}")

    # 2. EBO: Determine behavioral directive
    # Simplified EBO input for this CLI demo
    # TODO: Real sentiment analysis, topic extraction would happen here or before Minimizer
    ebo_input_data = {
        "user_sentiment": {"neutral": 0.8, "positive": 0.2} if "happy" not in user_input.lower() else {"positive":0.8, "neutral":0.2}, # Mock sentiment
        "conversation_topic": "general_chat", # Mock topic
        "persona_current_emotion": current_behavioral_model.current_emotion,
        "persona_traits": current_behavioral_model.base_traits,
        "is_new_conversation": not AIVCPU_INSTANCE.shared_cache_hierarchy.read_csl(AIVCPU_INSTANCE.config.context_specific_cache_layers_config[0].name, f"history_{conversation_id}"), # Check if history exists
        "user_direct_request_type": "statement" if "?" not in user_input else "question" # Simple check
    }
    ebo_directive = EBO_MAIN.process(ebo_input_data) # type: ignore # because ebo_input_data is a dict not EBOInput
    print(f"  [EBO Directive]: ID={ebo_directive.matched_rule_id}, Action={ebo_directive.action_request}, Goal={ebo_directive.interaction_goal}")
    print(f"     Modifiers: {ebo_directive.context_modifiers}")


    # 3. Enrichment Engine: Build LLM prompt
    # User input to enricher should be the original for LLM context,
    # but system prompt generated by enricher can reflect minimized understanding if needed.
    enriched_prompt = ENRICHMENT_ENGINE_MAIN.enrich_prompt_directive(
        ebo_output=ebo_directive,
        behavioral_model=current_behavioral_model,
        user_input_text=user_input, # Pass original user input for LLM context
        conversation_id=conversation_id,
        topic=ebo_input_data["conversation_topic"]
    )
    # For debugging:
    # print(f"  [Enriched System Prompt]: {enriched_prompt.system_prompt[:200]}...")
    # print(f"  [Enriched User Prompt]: {enriched_prompt.user_prompt[:200]}...")


    # 4. LLM Adapter: Get response from LLM
    print(f"  [LLM Adapter]: Sending to {LLM_ADAPTER_MAIN.__class__.__name__}...")
    llm_response: LLMResponse
    # For streaming demo:
    if isinstance(LLM_ADAPTER_MAIN, GeminiAdapter): # Or any adapter that supports streaming well
        full_llm_text = ""
        print(f"  [{current_behavioral_model.persona_id} (Streaming)]: ", end="", flush=True)
        async for stream_chunk in LLM_ADAPTER_MAIN.stream_response(enriched_prompt):
            if stream_chunk.success and stream_chunk.text:
                print(stream_chunk.text, end="", flush=True)
                full_llm_text += stream_chunk.text
            elif not stream_chunk.success:
                print(f"\nLLM Stream Error: {stream_chunk.error}")
                return f"[LLM Stream Error: {stream_chunk.error}]" # End turn on error
            if not stream_chunk.metadata.get('is_partial'): # End of stream
                break
        print() # Newline after streaming
        llm_response = LLMResponse(text=full_llm_text.strip(), metadata={"streamed": True})

    else: # Non-streaming path
        llm_response = await LLM_ADAPTER_MAIN.generate_response(enriched_prompt)
        if llm_response.success:
            print(f"  [{current_behavioral_model.persona_id}]: {llm_response.text}")
        else:
            print(f"  [LLM Error]: {llm_response.error}")
            return f"[LLM Error: {llm_response.error}]" # End turn on error

    if not llm_response.text and llm_response.success: # Empty response but no error
        final_response_text = "[Persona chose not to respond or response was empty]"
        print(f"  [{current_behavioral_model.persona_id}]: {final_response_text}")
    else:
        final_response_text = llm_response.text

    # 5. Post-processing / Learning (Conceptual)
    # - Update conversation history in AIVCPU CSL
    history_csl_name = AIVCPU_INSTANCE.config.context_specific_cache_layers_config[0].name
    current_history = AIVCPU_INSTANCE.shared_cache_hierarchy.read_csl(history_csl_name, f"history_{conversation_id}")
    if not current_history: current_history = []
    current_history.append({"speaker": "User", "text": user_input})
    current_history.append({"speaker": current_behavioral_model.persona_id, "text": final_response_text})
    AIVCPU_INSTANCE.shared_cache_hierarchy.write_csl(history_csl_name, f"history_{conversation_id}", current_history[-10:]) # Keep last 10 turns

    # - Conceptual: Behavioral model adaptation (Neuroplasticity)
    # This would involve analyzing the interaction (user feedback, goal achievement)
    # and potentially submitting tasks to PersonalityExtractor or other AIVCPU cores.
    # For demo, a simple simulated update based on interaction.
    current_behavioral_model.simulate_neuroplasticity_on_experience(
        experience_type="conversation_turn",
        data={"user_input_type": ebo_input_data["user_direct_request_type"],
              "persona_action": ebo_directive.action_request,
              "llm_response_length": len(final_response_text)}
    )
    # Example: if user input was short and persona response was long, maybe adjust verbosity slightly.
    if len(user_input) < 20 and len(final_response_text) > 150 and \
       current_behavioral_model.get_trait_value(PersonalityTrait.VERBOSITY) is not None: # type: ignore
        current_verbosity = current_behavioral_model.get_trait_value(PersonalityTrait.VERBOSITY) or 0.5
        current_behavioral_model.update_trait(PersonalityTrait.VERBOSITY, current_verbosity - 0.05) # Become slightly less verbose
        print(f"    (System: Persona verbosity adjusted slightly due to response length difference.)")


    return final_response_text


async def main_loop():
    print("--- Project Doppelganger: Core Interaction Loop (CLI Demo) ---")
    print(f"Interacting with Persona: {PERSONA_ID_MAIN}")
    print("Type 'quit' or 'exit' to end.")

    # Start AI-vCPU (it manages its own scheduler loop in the background)
    await AIVCPU_INSTANCE.start()

    conversation_id = f"cli_convo_{int(time.time())}"
    turn_count = 0

    while True:
        try:
            user_text = await asyncio.to_thread(input, "You: ") # Run input in a separate thread to not block asyncio loop
        except RuntimeError: # Fallback for environments where to_thread might not work as expected with input()
            user_text = input("You: ")


        if user_text.lower() in ["quit", "exit"]:
            break
        if not user_text.strip():
            continue

        turn_count += 1
        print(f"--- Turn {turn_count} ({conversation_id}) ---")

        persona_response = await process_user_turn(
            user_input=user_text,
            conversation_id=conversation_id,
            current_behavioral_model=BEHAVIORAL_MODEL_MAIN,
            current_user_consent=USER_CONSENT_MAIN
        )

        # (Persona response already printed within process_user_turn for streaming)
        if persona_response and "[LLM Error:" in persona_response:
            print("An LLM error occurred. Try again or check API key/config.")
        elif persona_response and "[LLM Stream Error:" in persona_response:
             print("An LLM stream error occurred. Try again or check API key/config.")


    print("\n--- End of Conversation ---")
    # Stop AI-vCPU
    await AIVCPU_INSTANCE.stop()
    print("Doppelganger session closed.")


if __name__ == "__main__":
    # This is an asyncio application.
    try:
        asyncio.run(main_loop())
    except KeyboardInterrupt:
        print("\nExiting due to user interruption...")
        # Perform any necessary cleanup if AIVCPU was running and didn't stop gracefully
        if AIVCPU_INSTANCE and AIVCPU_INSTANCE._is_running:
            print("Attempting to stop AIVCPU...")
            asyncio.run(AIVCPU_INSTANCE.stop(graceful=False))
    finally:
        print("Application shutdown complete.")
