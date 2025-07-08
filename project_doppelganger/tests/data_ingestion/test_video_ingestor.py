import unittest
import asyncio
from project_doppelganger.src.data_ingestion.video_ingestor import VideoIngestor

class TestVideoIngestor(unittest.IsolatedAsyncioTestCase):

    async def test_ingest_data_returns_bytes(self):
        ingestor = VideoIngestor()
        source_file = "test_video.mp4"
        result = await ingestor.ingest_data(source_file)
        self.assertIsInstance(result, bytes)
        self.assertEqual(result, b"mock_video_bytes_data_from_" + source_file.encode('utf-8'))

    async def test_process_data_returns_dict(self):
        ingestor = VideoIngestor()
        raw_data = b"mock_raw_video_bytes"
        result = await ingestor.process_data(raw_data)
        self.assertIsInstance(result, dict)
        self.assertIn("duration_ms", result)
        self.assertIn("format", result)
        self.assertIn("frames", result)
        self.assertIn("conceptual_features", result)
        self.assertEqual(result["conceptual_features"], "mock_video_features")

if __name__ == '__main__':
    unittest.main()
