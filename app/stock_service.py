"""
Eski Usul AI Studio — Stock Media Service (Gelişmiş Otonom Sürüm)
Pexels & Pixabay API Entegrasyonu + Yapay Zeka Destekli Otonom Görsel Kürasyonu
"""
from __future__ import annotations

import os
import uuid
import asyncio
import httpx
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "data" / "media" / "assets"
ASSETS.mkdir(parents=True, exist_ok=True)


def _get_api_keys() -> tuple[str, str]:
    from app.agent_runtime import _read_env
    env = _read_env()
    pexels_key = os.getenv("PEXELS_API_KEY") or env.get("PEXELS_API_KEY", "")
    pixabay_key = os.getenv("PIXABAY_API_KEY") or env.get("PIXABAY_API_KEY", "")
    return pexels_key, pixabay_key


async def search_pexels_videos(query: str, per_page: int = 5) -> list[dict[str, Any]]:
    pexels_key, _ = _get_api_keys()
    if not pexels_key:
        return []
    
    url = "https://api.pexels.com/videos/search"
    params = {"query": query.strip(), "per_page": per_page, "orientation": "portrait"}
    headers = {"Authorization": pexels_key}
    results = []
    
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url, params=params, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                for v in data.get("videos", []):
                    files = v.get("video_files", [])
                    best_file = None
                    for f in files:
                        if f.get("width", 0) <= 1080 and f.get("quality") in ["hd", "sd"]:
                            best_file = f.get("link")
                            break
                    if not best_file and files:
                        best_file = files[0].get("link")
                    
                    if best_file:
                        results.append({
                            "source": "Pexels",
                            "kind": "video",
                            "title": f"Pexels Video {v.get('id')}",
                            "download_url": best_file,
                            "page_url": v.get("url", ""),
                            "author": v.get("user", {}).get("name", "Pexels Creator"),
                            "license": "Pexels License (Commercial OK)",
                            "commercial_ok": True,
                            "thumbnail": v.get("image", ""),
                            "duration": v.get("duration", 0)
                        })
    except Exception as exc:
        print(f"Pexels search error: {exc}")
    return results


async def search_pixabay_videos(query: str, per_page: int = 5) -> list[dict[str, Any]]:
    _, pixabay_key = _get_api_keys()
    if not pixabay_key:
        return []
    
    url = "https://pixabay.com/api/videos/"
    params = {
        "key": pixabay_key,
        "q": query.strip(),
        "per_page": per_page,
        "video_type": "film",
        "safesearch": "true"
    }
    results = []
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url, params=params)
            if resp.status_code == 200:
                data = resp.json()
                for hit in data.get("hits", []):
                    videos = hit.get("videos", {})
                    v_info = videos.get("medium") or videos.get("small") or videos.get("large")
                    if v_info and v_info.get("url"):
                        results.append({
                            "source": "Pixabay",
                            "kind": "video",
                            "title": f"Pixabay Video {hit.get('id')}",
                            "download_url": v_info.get("url"),
                            "page_url": hit.get("pageURL", ""),
                            "author": hit.get("user", "Pixabay Creator"),
                            "license": "Pixabay Content License (Commercial OK)",
                            "commercial_ok": True,
                            "thumbnail": hit.get("videos", {}).get("tiny", {}).get("url", ""),
                            "duration": hit.get("duration", 0)
                        })
    except Exception as exc:
        print(f"Pixabay video search error: {exc}")
    return results


async def search_pixabay_images(query: str, per_page: int = 5) -> list[dict[str, Any]]:
    _, pixabay_key = _get_api_keys()
    if not pixabay_key:
        return []

    url = "https://pixabay.com/api/"
    params = {
        "key": pixabay_key,
        "q": query.strip(),
        "per_page": per_page,
        "image_type": "photo",
        "orientation": "vertical",
        "safesearch": "true"
    }
    results = []
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url, params=params)
            if resp.status_code == 200:
                data = resp.json()
                for hit in data.get("hits", []):
                    img_url = hit.get("largeImageURL") or hit.get("webformatURL")
                    if img_url:
                        results.append({
                            "source": "Pixabay",
                            "kind": "image",
                            "title": f"Pixabay Fotoğraf {hit.get('id')}",
                            "download_url": img_url,
                            "page_url": hit.get("pageURL", ""),
                            "author": hit.get("user", "Pixabay Creator"),
                            "license": "Pixabay Content License (Commercial OK)",
                            "commercial_ok": True,
                            "thumbnail": hit.get("previewURL", img_url),
                            "duration": 0
                        })
    except Exception as exc:
        print(f"Pixabay image search error: {exc}")
    return results


async def search_stock_media(query: str, limit: int = 8) -> list[dict[str, Any]]:
    """Pexels ve Pixabay üzerinde eşzamanlı video ve dikey görsel arama yapar."""
    half = max(2, limit // 2)
    pexels_task = search_pexels_videos(query, per_page=half)
    pixabay_vid_task = search_pixabay_videos(query, per_page=half)
    pixabay_img_task = search_pixabay_images(query, per_page=max(2, half // 2))

    res = await asyncio.gather(pexels_task, pixabay_vid_task, pixabay_img_task, return_exceptions=True)
    combined = []
    for r in res:
        if isinstance(r, list):
            combined.extend(r)
    return combined[:limit]


async def download_and_save_asset(item: dict[str, Any]) -> dict[str, Any]:
    """Seçilen stok medyayı indirir ve yerel arşive kaydeder."""
    download_url = item["download_url"]
    aid = str(uuid.uuid4())
    ext = ".mp4" if item["kind"] == "video" else ".jpg"
    stored_name = f"{aid}{ext}"
    dest_path = ASSETS / stored_name
    
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.get(download_url)
        resp.raise_for_status()
        dest_path.write_bytes(resp.content)
        
    return {
        "id": aid,
        "filename": f"{item['source'].lower()}_{aid[:8]}{ext}",
        "stored_name": stored_name,
        "kind": item["kind"],
        "source_url": item["page_url"],
        "license_name": item["license"],
        "commercial_ok": 1 if item["commercial_ok"] else 0,
        "attribution": f"{item.get('author', 'Creator')} on {item['source']}",
        "notes": f"Otomatik kürasyon: {item.get('title', '')}"
    }


TR_EN_KEYWORDS = {
    "vapur": "ferry bosphorus",
    "boğaz": "bosphorus istanbul",
    "martı": "seagulls flying",
    "çay": "tea cup table",
    "istanbul": "istanbul city",
    "galata": "galata tower",
    "karaköy": "karakoy istanbul",
    "deniz": "sea water calm",
    "gün batımı": "sunset golden hour",
    "iskele": "ferry dock",
    "sokak": "cozy street",
    "kahve": "coffee cup table",
    "şehir": "city aerial cinematic"
}


async def auto_curate_scene_assets(visual_plan: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Yapay Zeka Görsel Küratörü:
    Her sahne için en uygun dikey stok videoları Pexels üzerinden bulur,
    otomatik indirir ve arşive kaydeder.
    """
    downloaded_assets = []
    for idx, vp in enumerate(visual_plan):
        # Arama terimini al (önce İngilizce, yoksa Türkçe veya sahne görsel tanımı)
        query = ""
        stock_spec = vp.get("stock_search", {})
        if isinstance(stock_spec, dict):
            query = stock_spec.get("query_en") or stock_spec.get("query_tr") or ""
        if not query:
            query = vp.get("visual") or vp.get("shot") or vp.get("query_en") or vp.get("query_tr") or "Istanbul peaceful"
        
        candidates = await search_stock_media(query, limit=3)
        if not candidates:
            # Akıllı anahtar kelime eşleşmesi dene
            q_lower = query.lower()
            alt_query = None
            for tr_word, en_word in TR_EN_KEYWORDS.items():
                if tr_word in q_lower:
                    alt_query = en_word
                    break
            if alt_query:
                candidates = await search_stock_media(alt_query, limit=3)

        if not candidates and " " in query:
            # İlk iki kelimeyle dene
            words = [w for w in query.split() if len(w) > 3]
            if words:
                candidates = await search_stock_media(" ".join(words[:2]), limit=3)

        if not candidates:
            # Genel yüksek estetikli dikey video yedeği
            fallback_terms = ["istanbul travel cinematic", "sea calm water", "sunset golden hour", "city street portrait"]
            candidates = await search_stock_media(fallback_terms[idx % len(fallback_terms)], limit=3)

        if candidates:
            best_candidate = candidates[0]
            try:
                saved = await download_and_save_asset(best_candidate)
                saved["scene_index"] = idx
                saved["scene_time"] = vp.get("scene_time", "")
                downloaded_assets.append(saved)
            except Exception as e:
                print(f"Sahne {idx} için otomatik indirme hatası: {e}")
                
    return downloaded_assets
