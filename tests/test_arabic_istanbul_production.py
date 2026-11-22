"""
Eski Usul AI Studio — Master Directive Acceptance Test (Section 11)
45 SANİYELİK PROFESYONEL ARAPÇA İSTANBUL TIKTOK VİDEOSU ÜRETİM VE DOĞRULAMA TESTİ
"""
import asyncio
import os
import unittest
from pathlib import Path

from app.tts_service import generate_speech
from app.visual_curator import curate_all_scenes_visuals
from app.video_engine.scene_schema import StudioScene
from app.video_engine.orchestrator import assemble_smart_video, get_ffmpeg_bin
from app.video_engine.render_validator import validate_video_render
from app.quality_guard import perform_full_studio_qa


class TestArabicIstanbulProduction(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        import socket
        try:
            socket.create_connection(("1.1.1.1", 53), timeout=1.5)
            cls.has_internet = True
        except OSError:
            cls.has_internet = False

    async def test_arabic_istanbul_video_generation(self):
        if not self.has_internet:
            self.skipTest("Bu entegrasyon testi gerçek Edge-TTS ve Pexels internet erişimi gerektirir.")

        ffmpeg_bin = get_ffmpeg_bin()
        self.assertTrue(os.path.exists(ffmpeg_bin) or shutil_which("ffmpeg"), "FFmpeg bulunamadı")

        # 1. Arapça Senaryo ve Sahneler (45 Saniye Hedef)
        arabic_hook = "هل تخطط لزيارة إسطنبول الساحرة هذا العام؟ إليك أهم الأماكن التي يجب ألا تفوتها!"
        arabic_narration = (
            "إسطنبول هي المدينة الوحيدة في العالم التي تمتد بين قارتين. "
            "ابدأ رحلتك بزيارة جامع آيا صوفيا التاريخي وتأمل العمارة البيزنطية والعثمانية المذهلة. "
            "ثم توجه إلى مضيق البوسفور واستمتع بجولة بحرية مع كوب من الشاي التركي الأصيل عند الغروب. "
            "ولا تنس زيارة برج غلاطة لإطلالة بانورامية تأسر القلوب على كامل المدينة القديمة. "
            "إسطنبول تنتظرك بذكريات لا تُنسى، شارك هذا الفيديو مع رفيق سفرك القادم!"
        )

        scenes_raw = [
            {
                "time": "0-8s",
                "shot": "Bosphorus aerial drone vertical view",
                "visual": "Istanbul bosphorus aerial view vertical",
                "on_screen_text": "إسطنبول الساحرة تنتظرك 🇹🇷",
                "narration": "هل تخطط لزيارة إسطنبول الساحرة هذا العام؟ إليك أهم الأماكن التي يجب ألا تفوتها!"
            },
            {
                "time": "8-18s",
                "shot": "Hagia Sophia mosque vertical architecture",
                "visual": "Hagia Sophia mosque Istanbul vertical",
                "on_screen_text": "جامع آيا صوفيا التاريخي 🕌",
                "narration": "ابدأ رحلتك بزيارة جامع آيا صوفيا التاريخي وتأمل العمارة المذهلة."
            },
            {
                "time": "18-28s",
                "shot": "Bosphorus sunset ferry turkish tea",
                "visual": "Bosphorus ferry sunset turkish tea",
                "on_screen_text": "سحر البوسفور عند الغروب ☕",
                "narration": "ثم توجه إلى مضيق البوسفور واستمتع بجولة بحرية مع كوب من الشاي التركي."
            },
            {
                "time": "28-37s",
                "shot": "Galata tower Istanbul panoramic view vertical",
                "visual": "Galata tower Istanbul vertical",
                "on_screen_text": "إطلالة ساحرة من برج غلاطة 🗼",
                "narration": "ولا تنس زيارة برج غلاطة لإطلالة بانورامية تأسر القلوب."
            },
            {
                "time": "37-45s",
                "shot": "Istanbul night lights cinematic vertical",
                "visual": "Istanbul city night cinematic vertical",
                "on_screen_text": "شارك الفيديو مع رفيق سفرك! ✈️",
                "narration": "إسطنبول تنتظرك بذكريات لا تُنسى، شارك هذا الفيديو مع رفيق سفرك القادم!"
            }
        ]

        # 2. Pydantic Sahne Şeması Doğrulaması
        studio_scenes = [StudioScene.from_dict(sc, i) for i, sc in enumerate(scenes_raw)]
        self.assertEqual(len(studio_scenes), 5)
        for s in studio_scenes:
            self.assertGreaterEqual(s.estimated_duration, 1.0)
            self.assertTrue(s.narration_text)

        # 3. Arapça Edge-TTS / Yerel Doğal Seslendirme
        voice_fn, voice_rel_path = await generate_speech(arabic_narration, language="ar")
        self.assertTrue(voice_fn.endswith((".mp3", ".wav")))
        root_dir = Path(__file__).resolve().parents[1]
        voice_full_path = root_dir / voice_rel_path
        self.assertTrue(voice_full_path.exists())
        self.assertGreater(voice_full_path.stat().st_size, 1000)

        # 4. Görsel Küratör ile Sahneleri Eşle
        curated = await curate_all_scenes_visuals(scenes_raw, target_duration=45.0)
        self.assertTrue(len(curated) > 0, "Görsel kürasyon en az bir sahne eşlemeli")

        # Sahnelere görsel ata
        for idx, sc in enumerate(scenes_raw):
            matched = next((a for a in curated if a.get("scene_index") == idx), None)
            if not matched and curated:
                matched = curated[idx % len(curated)]
            if matched:
                sc["asset_stored_name"] = matched["stored_name"]
                sc["asset_filename"] = matched["filename"]

        # 5. FFmpeg Akıllı Montaj (Arapça RTL Altyazı + Crossfade + Audio Ducking)
        script_id = "arab_ist_45"
        usable_assets = [{"stored_name": c["stored_name"], "filename": c["filename"]} for c in curated]
        
        montage_res = await assemble_smart_video(
            script_id=script_id,
            scenes=scenes_raw,
            usable_assets=usable_assets,
            voice_filename=voice_fn,
            burn_subtitles=True,
            transition_style="fade",
            enable_ken_burns=True
        )

        self.assertTrue(montage_res.get("ok"), f"Montaj başarısız: {montage_res}")
        rendered_filename = montage_res["filename"]
        out_path = root_dir / "data" / "media" / "exports" / rendered_filename
        self.assertTrue(out_path.exists())

        # 6. Render QA Doğrulaması (Stream, Çözünürlük, Süre)
        qa = await validate_video_render(ffmpeg_bin, out_path)
        self.assertTrue(qa.passed, f"Render QA başarısız: {qa.errors}")
        self.assertEqual(qa.video_codec, "h264")
        self.assertEqual(qa.resolution, "1080x1920")
        self.assertFalse(qa.corruption_detected)
        self.assertGreater(qa.duration_sec, 20.0, "Video süresi beklentiyi karşılamalı")

        # 7. Quality Guard Audit
        script_dict = {
            "hook": arabic_hook,
            "narration": arabic_narration,
            "scenes": scenes_raw,
            "voice_filename": voice_fn
        }
        audit = perform_full_studio_qa(script_dict, voice_file_path=voice_full_path, render_qa_dict=qa.to_dict())
        self.assertTrue(audit.overall_passed)
        self.assertGreaterEqual(audit.total_score, 80)
        print(f"\n[Master Acceptance Test BAŞARILI] {rendered_filename} (Süre: {qa.duration_sec}s, Çözünürlük: {qa.resolution}, Skor: {audit.total_score})")


def shutil_which(cmd):
    import shutil
    return bool(shutil.which(cmd))


if __name__ == "__main__":
    unittest.main()
