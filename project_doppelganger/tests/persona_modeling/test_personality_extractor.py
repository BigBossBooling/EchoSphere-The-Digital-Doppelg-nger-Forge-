import unittest
import asyncio
from unittest.mock import MagicMock, AsyncMock

from project_doppelganger.src.persona_modeling.personality_extractor import PersonalityExtractor
from project_doppelganger.src.persona_modeling.behavioral_model import PersonalityTrait, TraitScore, CommunicationStyleAspect
from project_doppelganger.src.ai_vcpu_core import TaskRequest, TaskResult, TaskStatus, CoreType

# Helper to run async tests if not using unittest.IsolatedAsyncioTestCase (though it's preferred)
def async_test(coro):
    def wrapper(*args, **kwargs):
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(coro(*args, **kwargs))
        finally:
            loop.close()
            asyncio.set_event_loop(None) # Restore default event loop policy
    return wrapper


class TestPersonalityExtractor(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.mock_vcpu = AsyncMock(spec=AIVCPU) # Use AsyncMock for async methods
        self.extractor = PersonalityExtractor(vcpu=self.mock_vcpu)
        self.persona_id = "test_pe_persona"
        self.sample_text = "This is some sample text for analysis."

    async def test_extract_traits_from_text_async_success(self):
        mock_task_result_data = {
            "traits": {
                "OPENNESS": {"value": 0.7, "confidence": 0.8},
                "CONSCIENTIOUSNESS": {"value": 0.6, "confidence": 0.75}
            }
        }
        mock_result = TaskResult(
            task_id="mock_task_1",
            request=MagicMock(spec=TaskRequest),
            status=TaskStatus.COMPLETED,
            result_data=mock_task_result_data
        )
        self.mock_vcpu.submit_task = AsyncMock(return_value="mock_task_1")
        self.mock_vcpu.get_task_result = AsyncMock(return_value=mock_result)

        traits = await self.extractor.extract_traits_from_text_async(self.persona_id, self.sample_text)

        self.mock_vcpu.submit_task.assert_called_once()
        submitted_task_req = self.mock_vcpu.submit_task.call_args[0][0]
        self.assertEqual(submitted_task_req.instruction, "analyze_text_for_traits")
        self.assertEqual(submitted_task_req.required_core_type, CoreType.LANGUAGE_MODELER)

        self.mock_vcpu.get_task_result.assert_called_once_with("mock_task_1", wait_timeout_sec=5.0)

        self.assertIn(PersonalityTrait.OPENNESS, traits)
        self.assertAlmostEqual(traits[PersonalityTrait.OPENNESS].value, 0.7)
        self.assertAlmostEqual(traits[PersonalityTrait.OPENNESS].confidence, 0.8)
        self.assertIn(PersonalityTrait.CONSCIENTIOUSNESS, traits)
        self.assertAlmostEqual(traits[PersonalityTrait.CONSCIENTIOUSNESS].value, 0.6)

    async def test_extract_traits_from_text_async_task_failed(self):
        mock_result = TaskResult(
            task_id="mock_task_fail",
            request=MagicMock(spec=TaskRequest),
            status=TaskStatus.FAILED,
            error_message="Core meltdown"
        )
        self.mock_vcpu.submit_task = AsyncMock(return_value="mock_task_fail")
        self.mock_vcpu.get_task_result = AsyncMock(return_value=mock_result)

        traits = await self.extractor.extract_traits_from_text_async(self.persona_id, self.sample_text)
        self.assertEqual(traits, {}) # Should return empty dict on failure

    async def test_extract_traits_from_text_async_timeout_or_no_result(self):
        self.mock_vcpu.submit_task = AsyncMock(return_value="mock_task_timeout")
        self.mock_vcpu.get_task_result = AsyncMock(return_value=None) # Simulate timeout

        traits = await self.extractor.extract_traits_from_text_async(self.persona_id, self.sample_text)
        self.assertEqual(traits, {})

    async def test_extract_traits_from_text_async_malformed_result(self):
        mock_task_result_data = {"traits": {"INVALID_TRAIT_NAME": {"value": 0.5}}}
        mock_result = TaskResult("mock_task_malformed", MagicMock(), TaskStatus.COMPLETED, mock_task_result_data)
        self.mock_vcpu.submit_task = AsyncMock(return_value="mock_task_malformed")
        self.mock_vcpu.get_task_result = AsyncMock(return_value=mock_result)

        traits = await self.extractor.extract_traits_from_text_async(self.persona_id, self.sample_text)
        self.assertEqual(traits, {}) # Invalid trait name should be skipped

    async def test_extract_communication_style_from_text_async_success(self):
        mock_style_data = {
            "style": {
                "TONE": "Formal",
                "LEXICAL_DIVERSITY": 0.8,
                "PREFERRED_PHRASES": ["Affirmative.", "Understood."]
            }
        }
        mock_result = TaskResult("mock_style_task", MagicMock(), TaskStatus.COMPLETED, mock_style_data)
        self.mock_vcpu.submit_task = AsyncMock(return_value="mock_style_task")
        self.mock_vcpu.get_task_result = AsyncMock(return_value=mock_result)

        style = await self.extractor.extract_communication_style_from_text_async(self.persona_id, self.sample_text)

        self.mock_vcpu.submit_task.assert_called_once()
        submitted_task_req = self.mock_vcpu.submit_task.call_args[0][0]
        self.assertEqual(submitted_task_req.instruction, "analyze_text_for_communication_style")

        self.assertIn(CommunicationStyleAspect.TONE, style)
        self.assertEqual(style[CommunicationStyleAspect.TONE], "Formal")
        self.assertIn(CommunicationStyleAspect.LEXICAL_DIVERSITY, style)
        self.assertAlmostEqual(style[CommunicationStyleAspect.LEXICAL_DIVERSITY], 0.8)
        self.assertIn(CommunicationStyleAspect.PREFERRED_PHRASES, style)
        self.assertIn("Affirmative.", style[CommunicationStyleAspect.PREFERRED_PHRASES])

    async def test_extract_key_phrases_and_sentiment_async_success(self):
        mock_analysis_data = {
            "entities": ["Python", "AI", "testing"],
            "sentiment": {"label": "neutral", "score": 0.55},
            "key_phrases": ["unit testing", "AI development"]
        }
        mock_result = TaskResult("mock_analysis_task", MagicMock(), TaskStatus.COMPLETED, mock_analysis_data)
        self.mock_vcpu.submit_task = AsyncMock(return_value="mock_analysis_task")
        self.mock_vcpu.get_task_result = AsyncMock(return_value=mock_result)

        analysis = await self.extractor.extract_key_phrases_and_sentiment_async(self.persona_id, self.sample_text)

        self.mock_vcpu.submit_task.assert_called_once()
        submitted_task_req = self.mock_vcpu.submit_task.call_args[0][0]
        self.assertEqual(submitted_task_req.instruction, "extract_entities_and_sentiment")

        self.assertEqual(analysis.get("entities"), ["Python", "AI", "testing"])
        self.assertEqual(analysis.get("sentiment", {}).get("label"), "neutral")
        self.assertAlmostEqual(analysis.get("sentiment", {}).get("score"), 0.55)

    async def test_empty_text_input_returns_empty(self):
        traits = await self.extractor.extract_traits_from_text_async(self.persona_id, "  ")
        self.assertEqual(traits, {})
        self.mock_vcpu.submit_task.assert_not_called()

        style = await self.extractor.extract_communication_style_from_text_async(self.persona_id, "\n\t")
        self.assertEqual(style, {})
        self.mock_vcpu.submit_task.assert_not_called() # Should still be 0 calls in total for this test case

        analysis = await self.extractor.extract_key_phrases_and_sentiment_async(self.persona_id, "")
        self.assertEqual(analysis, {})
        self.mock_vcpu.submit_task.assert_not_called() # Still 0

if __name__ == '__main__':
    unittest.main()
