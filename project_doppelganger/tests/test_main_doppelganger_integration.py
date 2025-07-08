import unittest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch

# Import components to be used or mocked
from project_doppelganger.src.main_doppelganger import (
    process_user_turn,
    MINIMIZER_ENGINE_MAIN, # We can use the actual instance or mock its methods
    EBO_MAIN,
    ENRICHMENT_ENGINE_MAIN,
    # LLM_ADAPTER_MAIN, # This will be mocked
    BEHAVIORAL_MODEL_MAIN,
    USER_CONSENT_MAIN,
    AIVCPU_INSTANCE # Needed for Enrichment Engine and history CSL
)
from project_doppelganger.src.conversational_ai.llm_interface import LLMResponse, AbstractLLMAdapter
from project_doppelganger.src.conversational_ai.ebo import EBOOutput
from project_doppelganger.src.conversational_ai.enrichment_engine import EnrichedPrompt


class TestMainDoppelgangerIntegration(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        # Ensure AIVCPU is started for tests that might use it (e.g. Enrichment Engine CSL access)
        # We won't run tasks on it, but it needs to be in a "running" state for some components.
        if not AIVCPU_INSTANCE._is_running:
            await AIVCPU_INSTANCE.start()

        # Reset or re-initialize CSL history for conversation_id if needed, or use unique convo_ids per test
        self.test_convo_id = f"test_integration_convo_{asyncio.get_running_loop().time()}"
        history_csl_name = AIVCPU_INSTANCE.config.context_specific_cache_layers_config[0].name
        AIVCPU_INSTANCE.shared_cache_hierarchy.write_csl(history_csl_name, f"history_{self.test_convo_id}", [])


    async def asyncTearDown(self):
        # Stop AIVCPU if it was started by setup
        if AIVCPU_INSTANCE._is_running:
             await AIVCPU_INSTANCE.stop(graceful=False) # Quick stop for tests

    @patch('project_doppelganger.src.main_doppelganger.MINIMIZER_ENGINE_MAIN.process_data')
    @patch('project_doppelganger.src.main_doppelganger.EBO_MAIN.process')
    @patch('project_doppelganger.src.main_doppelganger.ENRICHMENT_ENGINE_MAIN.enrich_prompt_directive')
    @patch('project_doppelganger.src.main_doppelganger.LLM_ADAPTER_MAIN', new_callable=AsyncMock) # Mock the instance
    async def test_full_pipeline_flow_with_mocks(
        self,
        MockLLMAdapterInstance: AsyncMock,
        mock_enrich_prompt: MagicMock,
        mock_ebo_process: MagicMock,
        mock_minimize_data: MagicMock
    ):
        user_input = "Hello, this is a test input."

        # --- Configure Mocks ---
        # 1. Minimizer mock
        mock_minimize_data.return_value = "minimized: " + user_input # What EBO receives

        # 2. EBO mock
        mock_ebo_output = EBOOutput(
            action_request="mock_action",
            interaction_goal="mock_goal",
            context_modifiers={"tone": "neutral"},
            matched_rule_id="MOCK_EBO_RULE"
        )
        mock_ebo_process.return_value = mock_ebo_output

        # 3. Enrichment Engine mock
        mock_enriched_prompt = EnrichedPrompt(
            system_prompt="Mock System Prompt",
            user_prompt="Mock User Prompt including: " + user_input,
            metadata={"persona_id": BEHAVIORAL_MODEL_MAIN.persona_id}
        )
        mock_enrich_prompt.return_value = mock_enriched_prompt

        # 4. LLM Adapter mock (the instance itself is mocked via @patch)
        mock_llm_response_text = "This is a mocked LLM response."
        mock_llm_response = LLMResponse(text=mock_llm_response_text, success=True)

        # Check if the mocked LLM_ADAPTER_MAIN is spec'd correctly for async methods
        if hasattr(MockLLMAdapterInstance, 'generate_response'):
             MockLLMAdapterInstance.generate_response = AsyncMock(return_value=mock_llm_response)
        if hasattr(MockLLMAdapterInstance, 'stream_response'): # If streaming path is taken
            async def mock_stream_gen(*args, **kwargs):
                yield LLMResponse(text=mock_llm_response_text, success=True, metadata={"is_partial": False, "finish_reason":"stop"})
            MockLLMAdapterInstance.stream_response = mock_stream_gen
            # Ensure the class name is available for the streaming check in process_user_turn
            MockLLMAdapterInstance.__class__.__name__ = "GeminiAdapter" # Or any streaming-capable adapter name


        # --- Call the main processing function ---
        # For this test, we'll use the global BEHAVIORAL_MODEL_MAIN and USER_CONSENT_MAIN
        # as process_user_turn is written to use them.
        final_response = await process_user_turn(
            user_input=user_input,
            conversation_id=self.test_convo_id,
            current_behavioral_model=BEHAVIORAL_MODEL_MAIN,
            current_user_consent=USER_CONSENT_MAIN
        )

        # --- Assertions ---
        # 1. Minimizer was called
        mock_minimize_data.assert_called_once_with(
            raw_data=user_input,
            data_category_hint=unittest.mock.ANY, # Or specific DataCategory
            user_consent=USER_CONSENT_MAIN,
            purpose=unittest.mock.ANY # Or specific Purpose
        )

        # 2. EBO was called with (conceptually) minimized input
        mock_ebo_process.assert_called_once()
        ebo_call_args = mock_ebo_process.call_args[0][0] # The EBOInput dict
        # self.assertEqual(ebo_call_args["user_input_text"], "minimized: " + user_input) # If EBO got minimized text
        # Note: The current main_doppelganger.py's EBOInput doesn't directly take minimized text,
        # but this is where you'd check if the flow was different.

        # 3. Enrichment Engine was called with EBO output and original user input
        mock_enrich_prompt.assert_called_once_with(
            ebo_output=mock_ebo_output,
            behavioral_model=BEHAVIORAL_MODEL_MAIN,
            user_input_text=user_input, # Original user input
            conversation_id=self.test_convo_id,
            topic=unittest.mock.ANY # Or specific topic if set in EBOInput mock
        )

        # 4. LLM Adapter was called with the enriched prompt
        # Check which LLM method was called (stream or generate)
        if MockLLMAdapterInstance.stream_response.called:
            MockLLMAdapterInstance.stream_response.assert_called_once_with(mock_enriched_prompt)
        elif MockLLMAdapterInstance.generate_response.called:
            MockLLMAdapterInstance.generate_response.assert_called_once_with(mock_enriched_prompt)
        else:
            self.fail("Neither LLM generate_response nor stream_response was called.")


        # 5. Final response matches the LLM's mocked response
        self.assertEqual(final_response, mock_llm_response_text)

        # 6. Conversation history CSL should have been updated (conceptual check)
        history_csl_name = AIVCPU_INSTANCE.config.context_specific_cache_layers_config[0].name
        AIVCPU_INSTANCE.shared_cache_hierarchy.write_csl.assert_called_with(
            history_csl_name,
            f"history_{self.test_convo_id}",
            unittest.mock.ANY # Check the list of turns
        )
        # More detailed check on history content:
        history_update_call_args = AIVCPU_INSTANCE.shared_cache_hierarchy.write_csl.call_args[0]
        updated_history_list = history_update_call_args[2] # The list of turns
        self.assertEqual(len(updated_history_list), 2) # User turn + Persona turn
        self.assertEqual(updated_history_list[0]["text"], user_input)
        self.assertEqual(updated_history_list[1]["text"], mock_llm_response_text)


        # 7. BehavioralModel's simulate_neuroplasticity_on_experience was called
        BEHAVIORAL_MODEL_MAIN.simulate_neuroplasticity_on_experience.assert_called()
        # Can add more specific assertions on the arguments if needed


if __name__ == '__main__':
    # unittest.main() # This will run IsolatedAsyncioTestCase correctly
    # For direct run if needed (though unittest.main() is better for async tests)
    async def run_tests():
        suite = unittest.TestSuite()
        suite.addTest(TestMainDoppelgangerIntegration("test_full_pipeline_flow_with_mocks"))
        runner = unittest.TextTestRunner()
        runner.run(suite)

    asyncio.run(run_tests())
