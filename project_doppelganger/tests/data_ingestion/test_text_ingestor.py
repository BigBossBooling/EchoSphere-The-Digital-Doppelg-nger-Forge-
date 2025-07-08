import unittest
import asyncio
from project_doppelganger.src.data_ingestion.text_ingestor import TextIngestor

class TestTextIngestor(unittest.IsolatedAsyncioTestCase):

    async def test_ingest_data_returns_string(self):
        ingestor = TextIngestor()
        result = await ingestor.ingest_data("test_source.txt")
        self.assertIsInstance(result, str)
        self.assertEqual(result, "Raw text data from test_source.txt")

    async def test_process_data_returns_string(self):
        ingestor = TextIngestor()
        raw_data = "Sample raw data for testing."
        result = await ingestor.process_data(raw_data)
        self.assertIsInstance(result, str)
        self.assertEqual(result, f"Processed: {raw_data}")

if __name__ == '__main__':
    unittest.main()
