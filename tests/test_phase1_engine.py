"""
Eski Usul AI Studio — Faz 1 Test Paketi: Video Engine, Visual Curator & Quality Guard
"""
import unittest
import asyncio
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class TestPhase1Engine(unittest.TestCase):

    def test_01_timeline_builder(self):
        from app.video_engine.timeline_builder import build_timeline_from_scenes
        scenes = [
            {"time": "0-4s", "on_screen_text": "Sahne 1", "visual": "Gemi"},
            {"time": "4-8s", "on_screen_text": "Sahne 2", "visual": "Martı"}
        ]
        timeline = build_timeline_from_scenes("test_script_1", "Test Project", scenes, "voice.mp3", 8.0)
        self.assertEqual(len(timeline.clips), 2)
        self.assertEqual(len(timeline.subtitle_tracks), 2)
        self.assertEqual(len(timeline.audio_tracks), 1)
        self.assertEqual(timeline.target_duration, 8.0)
        
        # JSON serileştirme
        d = timeline.to_dict()
        self.assertEqual(d["aspect_ratio"], "9:16")

    def test_02_visual_curator_scoring(self):
        from app.visual_curator import calculate_candidate_score
        good_cand = {
            "kind": "video",
            "title": "Bosphorus ferry sunset",
            "duration": 5.0,
            "commercial_ok": True,
            "download_url": "https://example.com/video1.mp4"
        }
        score = calculate_candidate_score(good_cand, "bosphorus ferry evening tea", 4.0, set())
        self.assertGreaterEqual(score, 70.0)

        # Tekrar cezası kontrolü
        dup_score = calculate_candidate_score(good_cand, "bosphorus ferry", 4.0, {"https://example.com/video1.mp4"})
        self.assertLess(dup_score, score)

    def test_03_quality_guard_script_and_visual(self):
        from app.quality_guard import audit_script_qa, audit_visual_qa
        
        # İyi senaryo
        script_ok = {"hook": "Bu vapurda çay başka kokar.", "narration": "Akşam telaşı dinerken vapur ilerler."}
        res = audit_script_qa(script_ok)
        self.assertTrue(res.passed)
        self.assertGreaterEqual(res.score, 80)

        # Eksik hook
        script_bad = {"hook": "", "narration": ""}
        res_bad = audit_script_qa(script_bad)
        self.assertFalse(res_bad.passed)

        # Görsel QA
        scenes_ok = [{"asset_stored_name": "v1.mp4"}, {"asset_stored_name": "v2.mp4"}]
        res_v = audit_visual_qa(scenes_ok)
        self.assertTrue(res_v.passed)

    def test_04_render_qa_existing_video(self):
        from app.video_engine.render_validator import validate_video_render
        from app.video_editor import get_ffmpeg_bin
        
        ffmpeg = get_ffmpeg_bin()
        sample_video = ROOT / "data" / "media" / "exports" / "eski_usul_0e189831.mp4"
        if sample_video.exists():
            qa = asyncio.run(validate_video_render(ffmpeg, sample_video))
            self.assertTrue(qa.passed, f"Render QA başarısız: {qa.errors}")
            self.assertTrue(qa.has_video_stream)
            self.assertTrue(qa.has_audio_stream)
            self.assertEqual(qa.width, 1080)
            self.assertEqual(qa.height, 1920)


if __name__ == "__main__":
    unittest.main()
