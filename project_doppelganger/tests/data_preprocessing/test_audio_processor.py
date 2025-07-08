import unittest
import asyncio
from project_doppelganger.src.data_preprocessing.audio_processor import AudioProcessor

class TestAudioProcessor(unittest.IsolatedAsyncioTestCase):

    async def test_extract_features_returns_dict(self):
        processor = AudioProcessor()
        mock_audio_data = b"mock_audio_for_feature_extraction"
        result = await processor.extract_features(mock_audio_data)

        self.assertIsInstance(result, dict)
        self.assertIn("mfccs", result)
        self.assertIsInstance(result["mfccs"], list)
        if result["mfccs"]: # If list is not empty
            self.assertIsInstance(result["mfccs"][0], list)
            if result["mfccs"][0]:
                 self.assertIsInstance(result["mfccs"][0][0], float)

        self.assertIn("spectrogram_shape", result)
        self.assertIsInstance(result["spectrogram_shape"], tuple)
        self.assertEqual(len(result["spectrogram_shape"]), 2)

        self.assertIn("sample_rate", result)
        self.assertIsInstance(result["sample_rate"], int)

if __name__ == '__main__':
    unittest.main()
