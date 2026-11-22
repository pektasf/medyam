"""
Eski Usul AI Studio — API Endpoints & Services Integration Test
"""
import unittest
import asyncio
from fastapi.testclient import TestClient
from app.main import app


class TestApiEndpoints(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_01_health_check(self):
        resp = self.client.get("/api/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "ok")
        self.assertTrue(data["ffmpeg"])
        self.assertTrue(data["database"])

    def test_02_dashboard_overview_stats(self):
        resp = self.client.get("/api/dashboard")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("stats", data)
        stats = data["stats"]
        self.assertIn("total_content", stats)
        self.assertIn("in_production", stats)
        self.assertIn("awaiting_review", stats)
        self.assertIn("scheduled_posts", stats)
        self.assertIn("failed_tasks", stats)

    def test_03_media_library(self):
        resp = self.client.get("/api/media")
        self.assertEqual(resp.status_code, 200)
        items = resp.json()
        self.assertIsInstance(items, list)

    def test_04_publishing_calendar_and_schedule(self):
        # 1. Takvimi al
        resp = self.client.get("/api/publishing/calendar")
        self.assertEqual(resp.status_code, 200)
        
        # 2. Kuyruğa ekle
        post_data = {
            "video_filename": "eski_usul_0e189831.mp4",
            "caption": "İstanbul'da bir akşam vakti çay keyfi #eskiusul",
            "scheduled_at": "2026-11-23 19:30",
            "platform": "tiktok"
        }
        res_post = self.client.post("/api/publishing/schedule", json=post_data)
        self.assertEqual(res_post.status_code, 200)
        self.assertTrue(res_post.json()["ok"])

    def test_05_analytics_insights(self):
        resp = self.client.get("/api/analytics/insights")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("optimal_duration_seconds", data)

    def test_06_brand_settings(self):
        resp = self.client.get("/api/brand-settings")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["brand_name"], "Eski Usul")
        self.assertIn("primary_voice_tr", data)
        self.assertIn("primary_voice_ar", data)

    def test_07_script_quality_guard_qa(self):
        # Mevcut senaryoyu sorgula
        resp_d = self.client.get("/api/dashboard")
        scripts = resp_d.json().get("scripts", [])
        if scripts:
            sid = scripts[0]["id"]
            res_qa = self.client.get(f"/api/scripts/{sid}/qa")
            self.assertEqual(res_qa.status_code, 200)
            qa_data = res_qa.json()
            self.assertIn("overall_passed", qa_data)
            self.assertIn("stages", qa_data)
            self.assertIn("script", qa_data["stages"])
            self.assertIn("visual", qa_data["stages"])
            self.assertIn("render", qa_data["stages"])

    def test_08_creatify_hook_variations(self):
        res = self.client.post("/api/ai/generate-hook-variations", json={"topic": "İstanbul vapurunda akşam çayı", "duration": 35})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["ok"])
        self.assertEqual(len(data["variations"]), 3)
        self.assertIn("hook_sentence", data["variations"][0])


if __name__ == "__main__":
    unittest.main()
