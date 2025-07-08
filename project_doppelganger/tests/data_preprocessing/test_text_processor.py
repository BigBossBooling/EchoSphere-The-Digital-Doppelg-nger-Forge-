import unittest
import asyncio
from project_doppelganger.src.data_preprocessing.text_processor import TextProcessor

class TestTextProcessor(unittest.IsolatedAsyncioTestCase):

    async def test_tokenize_returns_list_of_strings(self):
        processor = TextProcessor()
        text = "This is a test sentence."
        result = await processor.tokenize(text)
        self.assertIsInstance(result, list)
        self.assertTrue(all(isinstance(token, str) for token in result))
        self.assertEqual(result, ["this", "is", "a", "test", "sentence."])

    async def test_clean_text_returns_list_of_strings(self):
        processor = TextProcessor()
        tokens = ["this", "is", "a", "test", "sentence", "to", "be", "cleaned"]
        result = await processor.clean_text(tokens)
        self.assertIsInstance(result, list)
        self.assertTrue(all(isinstance(token, str) for token in result))
        # Based on current simple logic: removes "a", "to", "be"
        self.assertEqual(result, ["this", "test", "sentence", "cleaned"])

if __name__ == '__main__':
    unittest.main()
