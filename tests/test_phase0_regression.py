"""
Eski Usul AI Studio — Faz 0 Regresyon Test Paketi
Mevcut çalışan sistemin doğrulanması ve regresyon tespiti.
"""
import unittest
import asyncio
import os
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "database" / "studio.sqlite3"


class TestPhase0Regression(unittest.TestCase):

    def test_01_database_and_migrations(self):
        """Veritabanı bağlantısı ve migration tablolarının doğrulanması."""
        self.assertTrue(DB_PATH.exists(), "Veritabanı dosyası mevcut olmalıdır.")
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        
        tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        expected_tables = [
            "projects", "ideas", "scripts", "assets", "tasks", "metrics",
            "workflows", "agent_executions", "schema_migrations",
            "social_accounts", "publishing_queue", "publishing_calendar",
            "analytics", "brand_settings", "studio_memory"
        ]
        for tbl in expected_tables:
            self.assertIn(tbl, tables, f"Tablo bulunamadı: {tbl}")
            
        # Assets genişletilmiş kolon kontrolü
        asset_cols = [c[1] for c in cur.execute("PRAGMA table_info(assets)").fetchall()]
        self.assertIn("asset_type", asset_cols)
        self.assertIn("duration", asset_cols)
        self.assertIn("width", asset_cols)
        self.assertIn("height", asset_cols)
        
        conn.close()

    def test_02_ffmpeg_and_ffprobe_available(self):
        """FFmpeg ve FFprobe motorlarının sistemde kullanılabilir olması."""
        from app.video_editor import get_ffmpeg_bin, is_ffmpeg_available
        self.assertTrue(is_ffmpeg_available(), "FFmpeg motoru kullanılabilir durumda olmalıdır.")
        bin_path = get_ffmpeg_bin()
        self.assertTrue(bool(bin_path), "FFmpeg binary yolu tespit edilemedi.")

    def test_03_tts_service_voices(self):
        """Edge-TTS ses eşleme haritasının doğrulanması."""
        from app.tts_service import VOICE_MAP
        self.assertIn("tr", VOICE_MAP)
        self.assertIn("ar", VOICE_MAP)
        self.assertIn("en", VOICE_MAP)
        self.assertEqual(VOICE_MAP["tr"], "tr-TR-AhmetNeural")
        self.assertEqual(VOICE_MAP["ar"], "ar-SA-HamedNeural")

    def test_04_stock_service_keyword_mapping(self):
        """Pexels ve Pixabay için Türkçe-İngilizce anahtar kelime eşlemesi."""
        from app.stock_service import TR_EN_KEYWORDS
        self.assertIn("vapur", TR_EN_KEYWORDS)
        self.assertIn("martı", TR_EN_KEYWORDS)
        self.assertIn("çay", TR_EN_KEYWORDS)
        self.assertIn("boğaz", TR_EN_KEYWORDS)

    def test_05_agent_definitions_exist(self):
        """10 uzman ajanın tanımlarının doğrulanması."""
        from app.agent_runtime import AGENT_DEFINITIONS
        self.assertEqual(len(AGENT_DEFINITIONS), 10)
        keys = [a["key"] for a in AGENT_DEFINITIONS]
        self.assertIn("scriptwriter", keys)
        self.assertIn("creative_director", keys)
        self.assertIn("visual_producer", keys)
        self.assertIn("fact_checker", keys)


if __name__ == "__main__":
    unittest.main()
