import unittest
import asyncio
from project_doppelganger.src.data_ingestion.audio_ingestor import AudioIngestor

class TestAudioIngestor(unittest.IsolatedAsyncioTestCase):

    async def test_ingest_data_returns_bytes(self):
        ingestor = AudioIngestor()
        source_file = "test_audio.wav"
        result = await ingestor.ingest_data(source_file)
        self.assertIsInstance(result, bytes)
        self.assertEqual(result, b"mock_audio_bytes_data_from_" + source_file.encode('utf-8'))

    async def test_process_data_returns_dict(self):
        ingestor = AudioIngestor()
        raw_data = b"mock_raw_audio_bytes"
        result = await ingestor.process_data(raw_data)
        self.assertIsInstance(result, dict)
        self.assertIn("duration_ms", result)
        self.assertIn("format", result)
        self.assertIn("features", result)
        self.assertEqual(result["features"], "mock_features")

if __name__ == '__main__':
    unittest.main()
