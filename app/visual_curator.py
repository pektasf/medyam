"""
Eski Usul AI Studio — Visual Curator & Intelligence Engine (v0.5)
Çoklu sağlayıcı (Pexels, Pixabay), çoklu aday toplama (5-10 aday),
ölçülebilir sahne uyum puanlaması, tekrar eden görüntü cezalandırması ve alternatif saklama.
"""
from __future__ import annotations

import asyncio
import os
import uuid
import re
from pathlib import Path
from typing import Any
import httpx

from app.stock_service import search_pexels_videos, search_pixabay_videos, TR_EN_KEYWORDS, download_and_save_asset

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "data" / "media" / "assets"
ASSETS.mkdir(parents=True, exist_ok=True)


def calculate_candidate_score(
    candidate: dict[str, Any],
    scene_brief: str,
    target_duration: float,
    used_asset_urls: set[str]
) -> float:
    """
    Aday video için ölçülebilir uyum skoru (0 - 100):
    1. Tekrarlama Kontrolü: Aynı URL daha önce kullanıldıysa -50 puan.
    2. Format Uyumu: Dikey (portrait) veya Pexels HD ise +30 puan.
    3. Konu & Anahtar Kelime Uyumu: Sahne brief'indeki kelimelerin başlık veya etiketlerle eşleşmesi +30 puan.
    4. Süre Uyumu: Sahne süresine yakınlık (en az 3 saniye) +20 puan.
    5. Sağlayıcı Güvenilirlik & Lisans: Ticari onaylı +20 puan.
    """
    score = 0.0
    url = candidate.get("download_url") or candidate.get("page_url", "")

    # 1. Tekrarlama cezası
    if url in used_asset_urls:
        score -= 50.0

    # 2. Format ve kalite
    if candidate.get("kind") == "video":
        score += 20.0
    title_lower = (candidate.get("title") or "").lower()

    # 3. Konu uyumu
    brief_words = [w.lower() for w in re.findall(r"\w+", scene_brief) if len(w) > 2]
    matched_words = sum(1 for w in brief_words if w in title_lower)
    score += min(30.0, matched_words * 10.0)

    # 4. Süre uyumu
    dur = float(candidate.get("duration", 0))
    if dur >= target_duration:
        score += 20.0
    elif dur >= 3.0:
        score += 10.0

    # 5. Ticari lisans doğrulaması
    if candidate.get("commercial_ok"):
        score += 20.0

    return max(0.0, min(100.0, score))


async def gather_scene_candidates(query: str, limit: int = 10) -> list[dict[str, Any]]:
    """Pexels ve Pixabay üzerinde eşzamanlı geniş aday havuzu (5-10 aday) toplar."""
    # Arama terimini optimize et
    clean_q = query.strip()
    q_lower = clean_q.lower()
    for tr, en in TR_EN_KEYWORDS.items():
        if tr in q_lower:
            clean_q = en
            break

    # Pexels ve Pixabay eşzamanlı çağrılır
    p_task = search_pexels_videos(clean_q, per_page=limit)
    px_task = search_pixabay_videos(clean_q, per_page=limit)
    res = await asyncio.gather(p_task, px_task, return_exceptions=True)

    candidates: list[dict[str, Any]] = []
    for r in res:
        if isinstance(r, list):
            candidates.extend(r)

    # Eğer sonuç azsa fallback kategori terimleri ile tamamla
    if len(candidates) < 3:
        fallbacks = await search_pexels_videos("istanbul cinematic aesthetic", per_page=5)
        candidates.extend(fallbacks)

    return candidates


async def curate_best_scene_asset(
    scene_index: int,
    scene_brief: str,
    target_duration: float,
    used_urls: set[str]
) -> dict[str, Any]:
    """
    Her sahne için adayları toplar, puanlar, en iyi olanı indirir,
    kullanıcı için ilk 3 alternatifi metadata olarak saklar.
    """
    candidates = await gather_scene_candidates(scene_brief, limit=8)

    # Her adayı puanla
    scored: list[tuple[float, dict[str, Any]]] = []
    for c in candidates:
        s = calculate_candidate_score(c, scene_brief, target_duration, used_urls)
        scored.append((s, c))

    # Puana göre azalan sırala
    scored.sort(key=lambda x: x[0], reverse=True)

    if not scored:
        raise RuntimeError(f"Sahne {scene_index + 1} için hiçbir stok video adayı bulunamadı.")

    best_score, best_candidate = scored[0]
    used_urls.add(best_candidate.get("download_url") or best_candidate.get("page_url", ""))

    # En iyi adayı yerel diske indir
    saved_asset = await download_and_save_asset(best_candidate)
    saved_asset["scene_index"] = scene_index
    saved_asset["match_score"] = round(best_score, 1)

    # Alternatifleri metadata_json'da sakla (kullanıcı UI'dan tek tıkla değiştirebilir)
    alternatives = []
    for alt_score, alt_cand in scored[1:4]:
        alternatives.append({
            "source": alt_cand.get("source"),
            "title": alt_cand.get("title"),
            "download_url": alt_cand.get("download_url"),
            "page_url": alt_cand.get("page_url"),
            "thumbnail": alt_cand.get("thumbnail"),
            "match_score": round(alt_score, 1)
        })
    saved_asset["alternatives"] = alternatives

    return saved_asset


async def curate_all_scenes_visuals(
    scenes: list[dict[str, Any]],
    target_duration: float = 35.0
) -> list[dict[str, Any]]:
    """Tüm senaryo sahneleri için tekrarsız, puanlanmış otonom görsel kürasyonu."""
    used_urls: set[str] = set()
    curated_assets: list[dict[str, Any]] = []

    per_scene_dur = max(3.0, target_duration / max(1, len(scenes)))

    for idx, sc in enumerate(scenes):
        brief = sc.get("visual") or sc.get("shot") or sc.get("on_screen_text") or "istanbul travel"
        try:
            asset = await curate_best_scene_asset(idx, brief, per_scene_dur, used_urls)
            curated_assets.append(asset)
        except Exception as e:
            print(f"[Visual Curator] Sahne {idx} aday seçimi uyarısı: {e}")

    return curated_assets
