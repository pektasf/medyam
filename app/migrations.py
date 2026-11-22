"""
Eski Usul AI Studio — Database Migrations Engine
Veri kaybı olmadan SQLite şemasını güvenle güncelleyen migration motoru.
"""
from __future__ import annotations

import sqlite3
import json
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "database" / "studio.sqlite3"


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def get_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_migration_table(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at TEXT NOT NULL
        )
    """)
    conn.commit()


def get_applied_migrations(conn: sqlite3.Connection) -> set[int]:
    init_migration_table(conn)
    rows = conn.execute("SELECT version FROM schema_migrations").fetchall()
    return {r["version"] for r in rows}


def record_migration(conn: sqlite3.Connection, version: int, name: str) -> None:
    conn.execute(
        "INSERT INTO schema_migrations (version, name, applied_at) VALUES (?, ?, ?)",
        (version, name, now())
    )
    conn.commit()


# ---------------------------------------------------------------------------
# MIGRATION DEFINITIONS
# ---------------------------------------------------------------------------

def migration_001_core_schema_and_asset_expansion(conn: sqlite3.Connection) -> None:
    """Temel tabloları ve genişletilmiş Asset/Script alanlarını ekler."""
    c = conn.cursor()
    
    # 1. Temel tabloların varlığını garanti et
    c.executescript("""
        CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            language TEXT DEFAULT 'tr',
            status TEXT DEFAULT 'active',
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS ideas (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            angle TEXT,
            language TEXT DEFAULT 'tr',
            score INTEGER DEFAULT 0,
            status TEXT DEFAULT 'new',
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS scripts (
            id TEXT PRIMARY KEY,
            project_id TEXT,
            title TEXT,
            language TEXT,
            hook TEXT,
            narration TEXT,
            scenes TEXT,
            score INTEGER DEFAULT 0,
            review TEXT,
            voice_filename TEXT,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS assets (
            id TEXT PRIMARY KEY,
            filename TEXT,
            stored_name TEXT,
            kind TEXT,
            source_url TEXT,
            license_name TEXT,
            commercial_ok INTEGER DEFAULT 0,
            attribution TEXT,
            notes TEXT,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY,
            agent TEXT,
            title TEXT,
            status TEXT,
            detail TEXT,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS metrics (
            id TEXT PRIMARY KEY,
            project_id TEXT,
            views INTEGER DEFAULT 0,
            avg_watch REAL DEFAULT 0,
            saves INTEGER DEFAULT 0,
            shares INTEGER DEFAULT 0,
            followers INTEGER DEFAULT 0,
            notes TEXT,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS workflows (
            id TEXT PRIMARY KEY,
            topic TEXT NOT NULL,
            language TEXT NOT NULL,
            duration INTEGER NOT NULL,
            status TEXT NOT NULL,
            provider TEXT,
            result_json TEXT,
            error TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS agent_executions (
            id TEXT PRIMARY KEY,
            workflow_id TEXT NOT NULL,
            agent_key TEXT NOT NULL,
            agent_name TEXT NOT NULL,
            department TEXT NOT NULL,
            status TEXT NOT NULL,
            output_json TEXT,
            provider TEXT,
            error TEXT,
            started_at TEXT,
            finished_at TEXT,
            FOREIGN KEY(workflow_id) REFERENCES workflows(id)
        );
    """)

    # 2. Assets tablosu kolon genişletmeleri
    existing_asset_cols = {col[1] for col in c.execute("PRAGMA table_info(assets)").fetchall()}
    new_asset_cols = [
        ("asset_type", "TEXT DEFAULT 'stock_video'"),
        ("project_id", "TEXT"),
        ("script_id", "TEXT"),
        ("duration", "REAL DEFAULT 0"),
        ("width", "INTEGER DEFAULT 1080"),
        ("height", "INTEGER DEFAULT 1920"),
        ("codec", "TEXT DEFAULT 'h264'"),
        ("file_size", "INTEGER DEFAULT 0"),
        ("thumbnail_path", "TEXT"),
        ("checksum", "TEXT"),
        ("language", "TEXT DEFAULT 'tr'"),
        ("tags", "TEXT DEFAULT '[]'"),
        ("metadata_json", "TEXT DEFAULT '{}'"),
    ]
    for col_name, col_type in new_asset_cols:
        if col_name not in existing_asset_cols:
            c.execute(f"ALTER TABLE assets ADD COLUMN {col_name} {col_type}")

    # 3. Scripts tablosu kolon genişletmeleri
    existing_script_cols = {col[1] for col in c.execute("PRAGMA table_info(scripts)").fetchall()}
    new_script_cols = [
        ("target_duration", "INTEGER DEFAULT 35"),
        ("platform", "TEXT DEFAULT 'tiktok'"),
        ("aspect_ratio", "TEXT DEFAULT '9:16'"),
        ("tone", "TEXT DEFAULT 'grounded'"),
        ("category", "TEXT DEFAULT 'culture'"),
        ("typography", "TEXT DEFAULT '{}'"),
        ("status", "TEXT DEFAULT 'draft'"),
    ]
    for col_name, col_type in new_script_cols:
        if col_name not in existing_script_cols:
            c.execute(f"ALTER TABLE scripts ADD COLUMN {col_name} {col_type}")

    conn.commit()


def migration_002_publishing_and_social_accounts(conn: sqlite3.Connection) -> None:
    """Sosyal hesaplar, yayın kuyruğu ve takvim tablolarını ekler."""
    c = conn.cursor()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS social_accounts (
            id TEXT PRIMARY KEY,
            platform TEXT NOT NULL,           -- 'tiktok', 'instagram', 'youtube_shorts'
            account_name TEXT NOT NULL,
            account_handle TEXT,
            avatar_url TEXT,
            access_token TEXT,
            refresh_token TEXT,
            token_expires_at TEXT,
            scope TEXT,
            status TEXT DEFAULT 'active',     -- 'active', 'expired', 'disconnected'
            metadata_json TEXT DEFAULT '{}',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS publishing_queue (
            id TEXT PRIMARY KEY,
            project_id TEXT,
            script_id TEXT,
            video_filename TEXT NOT NULL,
            caption TEXT NOT NULL,
            hashtags TEXT DEFAULT '[]',
            platform TEXT DEFAULT 'tiktok',
            account_id TEXT,
            scheduled_at TEXT NOT NULL,
            status TEXT DEFAULT 'scheduled',  -- 'scheduled', 'publishing', 'published', 'failed', 'cancelled'
            api_response TEXT,
            error_msg TEXT,
            retry_count INTEGER DEFAULT 0,
            published_at TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(account_id) REFERENCES social_accounts(id)
        );

        CREATE TABLE IF NOT EXISTS publishing_calendar (
            id TEXT PRIMARY KEY,
            queue_id TEXT NOT NULL,
            date_str TEXT NOT NULL,           -- 'YYYY-MM-DD'
            time_str TEXT NOT NULL,           -- 'HH:MM'
            status TEXT DEFAULT 'planned',
            created_at TEXT NOT NULL,
            FOREIGN KEY(queue_id) REFERENCES publishing_queue(id)
        );
    """)
    conn.commit()


def migration_003_analytics_and_studio_memory(conn: sqlite3.Connection) -> None:
    """Detaylı analitik metrikleri, marka ses ayarları ve stüdyo hafıza tabloları."""
    c = conn.cursor()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS analytics (
            id TEXT PRIMARY KEY,
            project_id TEXT,
            script_id TEXT,
            post_id TEXT,
            platform TEXT DEFAULT 'tiktok',
            views INTEGER DEFAULT 0,
            likes INTEGER DEFAULT 0,
            comments INTEGER DEFAULT 0,
            shares INTEGER DEFAULT 0,
            saves INTEGER DEFAULT 0,
            avg_watch_time REAL DEFAULT 0,
            completion_rate REAL DEFAULT 0,
            follower_growth INTEGER DEFAULT 0,
            notes TEXT,
            recorded_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS brand_settings (
            id TEXT PRIMARY KEY,
            brand_name TEXT DEFAULT 'Eski Usul',
            spirit TEXT DEFAULT 'Hayat, ekrandan ibaret değil.',
            tone TEXT DEFAULT 'curious, observant, warm, grounded',
            primary_voice_tr TEXT DEFAULT 'tr-TR-AhmetNeural',
            primary_voice_en TEXT DEFAULT 'en-US-ChristopherNeural',
            primary_voice_ar TEXT DEFAULT 'ar-SA-HamedNeural',
            forbidden_words TEXT DEFAULT '["carpe diem", "life is short", "put down your phone"]',
            style_rules TEXT DEFAULT '{}',
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS studio_memory (
            id TEXT PRIMARY KEY,
            memory_type TEXT NOT NULL,        -- 'best_hooks', 'high_retention_patterns', 'optimal_times'
            category TEXT DEFAULT 'general',
            insights_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
    """)

    # Varsayılan marka ayarı yoksa ekle
    row = c.execute("SELECT id FROM brand_settings WHERE id = 'default'").fetchone()
    if not row:
        c.execute("""
            INSERT INTO brand_settings (id, brand_name, spirit, tone, primary_voice_tr, primary_voice_en, primary_voice_ar, updated_at)
            VALUES ('default', 'Eski Usul', 'Hayat, ekrandan ibaret değil.', 'curious, observant, warm, grounded', 'tr-TR-AhmetNeural', 'en-US-ChristopherNeural', 'ar-SA-HamedNeural', ?)
        """, (now(),))

    conn.commit()


MIGRATIONS = [
    (1, "core_schema_and_asset_expansion", migration_001_core_schema_and_asset_expansion),
    (2, "publishing_and_social_accounts", migration_002_publishing_and_social_accounts),
    (3, "analytics_and_studio_memory", migration_003_analytics_and_studio_memory),
]


def run_all_migrations(conn: sqlite3.Connection | None = None) -> list[str]:
    """Tüm bekleyen migration'ları çalıştırır ve rapor döner."""
    close_at_end = False
    if conn is None:
        conn = get_connection()
        close_at_end = True

    try:
        applied = get_applied_migrations(conn)
        reports = []
        for version, name, func in MIGRATIONS:
            if version not in applied:
                print(f"[Migration] Uygulanıyor: v{version}_{name}...")
                func(conn)
                record_migration(conn, version, name)
                reports.append(f"Uygulandı: v{version}_{name}")
            else:
                reports.append(f"Zaten mevcut: v{version}_{name}")
        return reports
    finally:
        if close_at_end:
            conn.close()


if __name__ == "__main__":
    results = run_all_migrations()
    for r in results:
        print(r)
