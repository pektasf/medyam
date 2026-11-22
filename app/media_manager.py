"""
Eski Usul AI Studio — Media Library & Asset Management Engine (v0.5)
Genişletilmiş asset modeli, FFmpeg otomatik video thumbnail üretimi,
checksum ile tekilleştirme, etiketleme ve medya temizleme.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.video_editor import get_ffmpeg_bin

ROOT = Path(__file__).resolve().parents[1]
ASSETS_DIR = ROOT / "data" / "media" / "assets"
THUMBNAILS_DIR = ROOT / "data" / "media" / "thumbnails"
DB_PATH = ROOT / "data" / "database" / "studio.sqlite3"

ASSETS_DIR.mkdir(parents=True, exist_ok=True)
THUMBNAILS_DIR.mkdir(parents=True, exist_ok=True)


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def compute_file_checksum(file_path: Path) -> str:
    """Dosyanın SHA-256 özetini hesaplar."""
    hasher = hashlib.sha256()
    with file_path.open("rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


async def generate_video_thumbnail(video_path: Path, thumbnail_path: Path, at_second: float = 1.0) -> bool:
    """FFmpeg ile videonun 1. saniyesinden dikey thumbnail (JPG) çıkarır."""
    ffmpeg = get_ffmpeg_bin()
    cmd = [
        ffmpeg, "-y",
        "-ss", f"{at_second:.2f}",
        "-i", str(video_path),
        "-vframes", "1",
        "-vf", "scale=360:640:force_original_aspect_ratio=increase,crop=360:640",
        str(thumbnail_path)
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    await proc.communicate()
    return proc.returncode == 0 and thumbnail_path.exists()


def register_media_asset(
    asset_id: str,
    filename: str,
    stored_name: str,
    asset_type: str = "stock_video",
    kind: str = "video",
    project_id: str | None = None,
    script_id: str | None = None,
    source_url: str = "",
    license_name: str = "Commercial OK",
    commercial_ok: int = 1,
    attribution: str = "",
    notes: str = "",
    duration: float = 0.0,
    width: int = 1080,
    height: int = 1920,
    codec: str = "h264",
    file_size: int = 0,
    thumbnail_path: str = "",
    checksum: str = "",
    tags: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
    db_path: Path = DB_PATH
) -> dict[str, Any]:
    """Genişletilmiş asset kaydını SQLite veritabanına ekler veya günceller."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    tags_json = json.dumps(tags or [], ensure_ascii=False)
    meta_json = json.dumps(metadata or {}, ensure_ascii=False)
    created = now()

    c.execute("""
        INSERT INTO assets (
            id, filename, stored_name, kind, source_url, license_name,
            commercial_ok, attribution, notes, created_at,
            asset_type, project_id, script_id, duration, width, height,
            codec, file_size, thumbnail_path, checksum, language, tags, metadata_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            filename=excluded.filename,
            stored_name=excluded.stored_name,
            asset_type=excluded.asset_type,
            file_size=excluded.file_size,
            thumbnail_path=excluded.thumbnail_path,
            checksum=excluded.checksum,
            tags=excluded.tags,
            metadata_json=excluded.metadata_json
    """, (
        asset_id, filename, stored_name, kind, source_url, license_name,
        commercial_ok, attribution, notes, created,
        asset_type, project_id, script_id, duration, width, height,
        codec, file_size, thumbnail_path, checksum, "tr", tags_json, meta_json
    ))
    conn.commit()
    conn.close()

    return {
        "id": asset_id,
        "filename": filename,
        "stored_name": stored_name,
        "asset_type": asset_type,
        "thumbnail_path": thumbnail_path
    }


def query_assets_library(
    asset_type: str | None = None,
    kind: str | None = None,
    search_query: str | None = None,
    db_path: Path = DB_PATH
) -> list[dict[str, Any]]:
    """Gelişmiş filtreleme ve arama ile medya kütüphanesini sorgular."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    sql = "SELECT * FROM assets WHERE 1=1"
    params = []

    if asset_type:
        sql += " AND asset_type = ?"
        params.append(asset_type)
    if kind:
        sql += " AND kind = ?"
        params.append(kind)
    if search_query:
        sql += " AND (filename LIKE ? OR notes LIKE ? OR attribution LIKE ? OR tags LIKE ?)"
        q = f"%{search_query.strip()}%"
        params.extend([q, q, q, q])

    sql += " ORDER BY created_at DESC"
    rows = c.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]
