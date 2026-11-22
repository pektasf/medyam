import unittest
import asyncio
from app.stock_service import search_pixabay_videos, search_pixabay_images
from app.hf_service import _get_hf_config


class TestPixabayAndHuggingFace(unittest.TestCase):
    def test_hf_config(self):
        cfg = _get_hf_config()
        self.assertIn("llm_model", cfg)
        self.assertIn("image_model", cfg)
        self.assertEqual(cfg["llm_model"], "Qwen/Qwen2.5-72B-Instruct")
        self.assertEqual(cfg["image_model"], "black-forest-labs/FLUX.1-schnell")

    def test_pixabay_video_query_structure(self):
        # Offline contract check
        async def run_dummy():
            # In sandbox mode without network, function returns empty list without crashing
            res = await search_pixabay_videos("istanbul sunset", per_page=2)
            self.assertIsInstance(res, list)
        asyncio.run(run_dummy())

    def test_pixabay_image_query_structure(self):
        # Offline contract check
        async def run_dummy():
            res = await search_pixabay_images("istanbul vapur", per_page=2)
            self.assertIsInstance(res, list)
        asyncio.run(run_dummy())


if __name__ == "__main__":
    unittest.main()
