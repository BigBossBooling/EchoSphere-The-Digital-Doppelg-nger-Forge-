import unittest
import asyncio
from typing import AsyncGenerator

from project_doppelganger.src.audio_synthesis.tts_engine import TTSEngine, TTSRequest, AudioOutputFormat
from project_doppelganger.src.audio_synthesis.voice_cloner import ClonedVoiceModel

class TestTTSEngineConceptual(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.tts_engine = TTSEngine() # No API key, so it will use simulated responses
        self.dummy_voice_model = ClonedVoiceModel(
            persona_id="TestTTSPersona",
            voice_id="sim_test_voice_001",
            cloning_service="ConceptualElevenLabs" # Match service name for API key check logic in TTSEngine
        )

    async def test_synthesize_speech_conceptual_output(self):
        test_text = "This is a conceptual speech synthesis test."
        request = TTSRequest(
            text_to_speak=test_text,
            voice_model=self.dummy_voice_model,
            output_format=AudioOutputFormat.MP3
        )

        audio_bytes = await self.tts_engine.synthesize_speech(request)

        self.assertIsNotNone(audio_bytes)
        self.assertIsInstance(audio_bytes, bytes)
        self.assertTrue(len(audio_bytes) > 0)

        # Check if the simulated output contains expected conceptual markers
        decoded_output = audio_bytes.decode('utf-8', errors='ignore') # It's bytes, but our sim is utf-8
        self.assertIn(f"<SimulatedAudio format='{AudioOutputFormat.MP3.name}'", decoded_output)
        self.assertIn(f"voice='{self.dummy_voice_model.voice_id}'", decoded_output)
        self.assertIn(test_text[:30], decoded_output) # Check if part of input text is in sim output

    async def test_synthesize_speech_no_api_key_for_elevenlabs_conceptual_fail(self):
        # TTSEngine constructor defaults to no API key.
        # If voice_model.cloning_service matches "ConceptualElevenLabs", it should "fail" (return None).
        # Our dummy_voice_model uses "ConceptualElevenLabs", so this should trigger the API key check.
        # However, the TTSEngine's current conceptual implementation bypasses the actual API call if no key,
        # and directly returns simulated bytes. This test checks that behavior.
        # If it were to strictly require an API key even for simulation, this test would change.

        # Let's create an engine that *would* conceptually fail if it tried a real call
        # For this test, we assume the current TTSEngine will *always* give conceptual output
        # if no API key is present, rather than returning None immediately due to missing key.
        # The `print(" Error: API key ...")` in `synthesize_speech` is informational.

        # Test that it still produces simulated output even if API key is None for "ConceptualElevenLabs"
        engine_no_key = TTSEngine(api_key=None)
        request = TTSRequest(
            text_to_speak="Test with no key.",
            voice_model=self.dummy_voice_model # Uses "ConceptualElevenLabs"
        )
        audio_bytes = await engine_no_key.synthesize_speech(request)
        self.assertIsNotNone(audio_bytes, "Conceptual synthesis should still proceed with simulated output even if API key is None.")
        self.assertIn("<SimulatedAudio", audio_bytes.decode('utf-8', errors='ignore'))


    async def test_stream_speech_conceptual_output(self):
        test_text = "This is a conceptual speech streaming test, with several words."
        request = TTSRequest(
            text_to_speak=test_text,
            voice_model=self.dummy_voice_model,
            output_format=AudioOutputFormat.PCM
        )

        received_chunks = []
        async for chunk in self.tts_engine.stream_speech(request):
            self.assertIsInstance(chunk, bytes)
            self.assertTrue(len(chunk) > 0)
            received_chunks.append(chunk)

        self.assertTrue(len(received_chunks) > 1, "Stream should produce multiple chunks for non-trivial text.")

        full_streamed_bytes = b"".join(received_chunks)
        decoded_output = full_streamed_bytes.decode('utf-8', errors='ignore')

        self.assertIn(f"<SimulatedStream format='{AudioOutputFormat.PCM.name}'", decoded_output)
        self.assertIn(f"voice='{self.dummy_voice_model.voice_id}'", decoded_output)
        self.assertIn(test_text, decoded_output) # Full text should be in the combined stream

    async def test_stream_speech_no_api_key_for_elevenlabs_conceptual_stream_with_simulation(self):
        # Similar to synthesize, current TTSEngine simulates stream even if API key is None.
        engine_no_key = TTSEngine(api_key=None)
        request = TTSRequest(
            text_to_speak="Stream test no key.",
            voice_model=self.dummy_voice_model # Uses "ConceptualElevenLabs"
        )

        received_chunks = []
        async for chunk in engine_no_key.stream_speech(request):
            received_chunks.append(chunk)

        self.assertTrue(len(received_chunks) > 0, "Conceptual stream should still produce simulated chunks even if API key is None.")
        decoded_output = b"".join(received_chunks).decode('utf-8', errors='ignore')
        self.assertIn("<SimulatedStream", decoded_output)
        self.assertNotIn("<Error>API Key Missing</Error>", decoded_output) # Ensure it didn't take the error path for missing key

if __name__ == '__main__':
    unittest.main()
