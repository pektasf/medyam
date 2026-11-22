"""
Eski Usul AI Studio — Backend v0.5.0 (Tam Yetenekli Sürüm)
Yenilikler:
  - Paralel Ajan Orkestrasyonu (Araştırma & Strateji paralel, Doğrulama & Görsel & Dil paralel)
  - Otomatik Edge-TTS Doğal Türkçe Seslendirme (/api/scripts/{id}/generate-voice)
  - Pexels & Pixabay Otomatik Stok Arama & İndirme (/api/stock/search, /api/stock/download)
  - Sahne Bazlı Akıllı FFmpeg Timeline Montajı & Altyazı Gömme (Burn-in Subtitles)
  - TikTok Hazır Yayın Paketi (Caption + Hashtag + MP4)
  - SSE ile Canlı İş Akışı Akışı
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import sqlite3
import subprocess
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Any

import httpx
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.agent_runtime import AGENT_DEFINITIONS, call_specialist, search_sources, _read_env, _redact
from app.stock_service import search_stock_media, download_and_save_asset, auto_curate_scene_assets
from app.tts_service import generate_speech
from app.video_editor import assemble_smart_video, is_ffmpeg_available

try:
    from sse_starlette.sse import EventSourceResponse
    SSE_AVAILABLE = True
except ImportError:
    SSE_AVAILABLE = False
    EventSourceResponse = None

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
DB   = DATA / "database" / "studio.sqlite3"
ASSETS  = DATA / "media" / "assets"
VOICE   = DATA / "media" / "voice"
EXPORTS = DATA / "media" / "exports"
THUMBNAILS = DATA / "media" / "thumbnails"
PROJECTS = DATA / "projects"
for _p in [DB.parent, ASSETS, VOICE, EXPORTS, THUMBNAILS, PROJECTS]:
    _p.mkdir(parents=True, exist_ok=True)

ALLOWED_ASSET_EXT = {".mp4", ".mov", ".m4v", ".webm", ".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_AUDIO_EXT = {".wav", ".mp3", ".m4a", ".aac", ".ogg"}

app = FastAPI(title="Eski Usul AI Studio", version="0.5.0")

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=ROOT / "app" / "static"), name="static")
app.mount("/media/assets", StaticFiles(directory=ASSETS), name="assets_static")
app.mount("/media/voice", StaticFiles(directory=VOICE), name="voice_static")
app.mount("/media/exports", StaticFiles(directory=EXPORTS), name="exports_static")
app.mount("/media/thumbnails", StaticFiles(directory=THUMBNAILS), name="thumbnails_static")


def conn():
    c = sqlite3.connect(DB, check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c


def init_db():
    with conn() as c:
        from app.migrations import run_all_migrations
        run_all_migrations(c)
        n = c.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
        if n == 0:
            c.execute(
                "INSERT INTO projects VALUES(?,?,?,?,?)",
                ("welcome", "Eski Usul — İlk içerik", "tr", "active", now()),
            )
        c.execute("DELETE FROM tasks WHERE id LIKE 'agent-%'")
        for a in AGENT_DEFINITIONS:
            c.execute(
                "INSERT INTO tasks VALUES(?,?,?,?,?,?)",
                ("agent-" + a["key"], a["key"], a["name"], "ready", a["mission"], now()),
            )


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def rows(sql, args=()):
    with conn() as c:
        return [dict(r) for r in c.execute(sql, args).fetchall()]


def one(sql, args=()):
    with conn() as c:
        r = c.execute(sql, args).fetchone()
        return dict(r) if r else None


def _get_full_workflow(workflow_id: str) -> dict | None:
    workflow = one("SELECT * FROM workflows WHERE id=?", (workflow_id,))
    if not workflow:
        return None
    executions = rows(
        "SELECT agent_key, agent_name, department, status, output_json, provider, "
        "error, started_at, finished_at "
        "FROM agent_executions WHERE workflow_id=? ORDER BY rowid",
        (workflow_id,),
    )
    for item in executions:
        item["output"] = json.loads(item.pop("output_json")) if item.get("output_json") else None
    workflow["agents"] = executions
    workflow["result"] = (
        json.loads(workflow.pop("result_json"))
        if workflow.get("result_json") else None
    )
    return workflow


class IdeaIn(BaseModel):
    title: str
    angle: str = ""
    language: str = "tr"


class WorkflowIn(BaseModel):
    topic: str = Field(min_length=3, max_length=240)
    language: str = "tr"
    duration: int = Field(default=35, ge=15, le=90)
    project_id: str = "welcome"
    format: Optional[str] = "tiktok_reels"
    target_audience: Optional[str] = "discovery"
    tone: Optional[str] = "observant"
    hook_model: Optional[str] = "intrigue"
    cta: Optional[str] = "soft_reflect"
    quality_mode: Optional[str] = "high"


class ScriptUpdateIn(BaseModel):
    title: Optional[str] = None
    hook: Optional[str] = None
    narration: Optional[str] = None
    scenes: Optional[list[dict]] = None
    review: Optional[str] = None


class StatusIn(BaseModel):
    status: str


class MetricIn(BaseModel):
    project_id: str = "welcome"
    views: int = 0
    avg_watch: float = 0
    saves: int = 0
    shares: int = 0
    followers: int = 0
    notes: str = ""


class StockDownloadIn(BaseModel):
    download_url: str
    kind: str = "video"
    source: str = "Pexels"
    title: str = ""
    page_url: str = ""
    author: str = ""
    license: str = "Commercial OK"
    commercial_ok: bool = True


def _is_workflow_cancelled(workflow_id: str) -> bool:
    wf = one("SELECT status FROM workflows WHERE id=?", (workflow_id,))
    return wf is not None and wf.get("status") == "cancelled"


# ---------------------------------------------------------------------------
# WORKFLOW İPTAL (STOP) & RAPORLAR
# ---------------------------------------------------------------------------

@app.post("/api/workflows/{workflow_id}/cancel")
def cancel_workflow(workflow_id: str):
    from app.video_engine.orchestrator import kill_active_render
    kill_active_render(workflow_id)
    with conn() as c:
        c.execute("UPDATE workflows SET status='cancelled', updated_at=? WHERE id=?", (now(), workflow_id))
        c.execute("UPDATE agent_executions SET status='skipped', finished_at=? WHERE workflow_id=? AND status='pending'", (now(), workflow_id))
        c.execute("UPDATE agent_executions SET status='cancelled', finished_at=? WHERE workflow_id=? AND status='running'", (now(), workflow_id))
        wf = c.execute("SELECT result_json FROM workflows WHERE id=?", (workflow_id,)).fetchone()
        if wf and wf["result_json"]:
            try:
                s_id = json.loads(wf["result_json"]).get("script_id")
                if s_id:
                    kill_active_render(s_id)
            except Exception:
                pass
    return {"ok": True, "message": "İş akışı ve varsa render işlemi başarıyla durduruldu."}


@app.get("/api/reports")
def get_studio_reports():
    """Tüm senaryoların, kalite denetim puanlarının ve videoların birleşik analiz raporu."""
    scripts_list = rows("SELECT * FROM scripts ORDER BY created_at DESC LIMIT 30")
    reports = []
    
    for s in scripts_list:
        # İlgili workflow'u bul
        wf = one("SELECT * FROM workflows WHERE result_json LIKE ? ORDER BY created_at DESC LIMIT 1", (f'%"script_id": "{s["id"]}"%',))
        mp4_name = f"eski_usul_{s['id'][:8]}.mp4"
        video_exists = (EXPORTS / mp4_name).exists()
        
        scenes_data = []
        if s.get("scenes"):
            try:
                scenes_data = json.loads(s["scenes"])
            except Exception:
                pass

        reports.append({
            "script_id": s["id"],
            "title": s["title"],
            "language": s["language"],
            "hook": s["hook"],
            "score": s["score"],
            "review_status": s["review"] or "pending",
            "scenes_count": len(scenes_data),
            "video_filename": mp4_name if video_exists else None,
            "video_url": f"/api/exports/{mp4_name}" if video_exists else None,
            "workflow_id": wf["id"] if wf else None,
            "workflow_status": wf["status"] if wf else None,
            "provider": wf["provider"] if wf else "Gemini / Groq",
            "created_at": s["created_at"]
        })
    return reports

async def run_single_agent(agent_key: str, workflow_id: str, context: dict, env_cache: dict) -> tuple[dict, str]:
    agent = next(a for a in AGENT_DEFINITIONS if a["key"] == agent_key)
    started = now()
    
    with conn() as c:
        c.execute(
            "UPDATE agent_executions SET status='running', started_at=? "
            "WHERE workflow_id=? AND agent_key=?",
            (started, workflow_id, agent_key),
        )
        row = c.execute(
            "SELECT id FROM agent_executions WHERE workflow_id=? AND agent_key=?",
            (workflow_id, agent_key),
        ).fetchone()
        execution_id = row["id"]
        c.execute("UPDATE tasks SET status='running' WHERE id=?", ("agent-" + agent_key,))

    try:
        agent_context = dict(context)
        if agent_key == "trend_researcher" and not context.get("research_sources"):
            agent_context["research_tool_status"] = "Web arama sonuç vermedi. Kaynak uydurma."

        output, provider = await call_specialist(agent, agent_context, env_cache)
        
        with conn() as c:
            c.execute(
                "UPDATE agent_executions SET status='completed', "
                "output_json=?, provider=?, finished_at=? WHERE id=?",
                (json.dumps(output, ensure_ascii=False), provider, now(), execution_id),
            )
            c.execute("UPDATE tasks SET status='completed' WHERE id=?", ("agent-" + agent_key,))
            
        return output, provider

    except Exception as exc:
        safe_err = _redact(str(exc))[:1200]
        print(f"[Workflow] {agent['name']} yürütülürken hata: {safe_err}, akıllı editoryal şablon motoruyla tamamlanıyor.")
        from app.agent_runtime import generate_fallback_specialist_output
        fallback_out = generate_fallback_specialist_output(agent_key, context)
        provider = "Studio Fallback Engine · Akıllı Şablon"
        with conn() as c:
            c.execute(
                "UPDATE agent_executions SET status='completed', output_json=?, provider=?, warnings_json=?, finished_at=? WHERE id=?",
                (json.dumps(fallback_out, ensure_ascii=False), provider, json.dumps([safe_err], ensure_ascii=False), now(), execution_id),
            )
            c.execute("UPDATE tasks SET status='completed' WHERE id=?", ("agent-" + agent_key,))
        return fallback_out, provider


async def execute_workflow(workflow_id: str, request: WorkflowIn):
    """
    Paralel Ajan Orkestrasyonu:
    Aşama 1: Executive Producer (Brief)
    Aşama 2: PARALEL [Trend Researcher + Audience Strategist]
    Aşama 3: Creative Director
    Aşama 4: Lead Scriptwriter
    Aşama 5: PARALEL [Fact Checker + Visual Producer + Localization Editor]
    Aşama 6: Quality Auditor
    Aşama 7: Publishing Strategist
    """
    env_cache = _read_env()
    with conn() as c:
        c.execute("UPDATE workflows SET status='running', updated_at=? WHERE id=?", (now(), workflow_id))

    context: dict = {
        "brand": {
            "name": "Eski Usul",
            "promise": "Hayat, ekrandan ibaret değil.",
            "editorial_style": "meraklı, gözlemci, sıcak, gerçekçi; vaaz veren veya klişe motivasyon dili yok",
        },
        "brief": {
            "topic": request.topic,
            "language": request.language,
            "target_duration_seconds": request.duration,
            "platform": "TikTok",
            "project_id": request.project_id,
        },
        "research_sources": [],
        "agent_outputs": {},
        "human_constraints": [
            "Gerçek olmayan olay, mekân veya alıntı uydurma.",
            "Telif/lisansı doğrulanmamış medya kullanma.",
            "Kullanıcı onayı olmadan yayın yapma.",
        ],
    }

    providers: set[str] = set()

    try:
        # Web Araması
        sources = await asyncio.to_thread(search_sources, request.topic, request.language)
        context["research_sources"] = sources

        # Kontrollü Eşzamanlılık (Rate Limit ve TPM korumalı semafor)
        sem = asyncio.Semaphore(2)

        async def run_guarded(agent_key: str):
            async with sem:
                return await run_single_agent(agent_key, workflow_id, context, env_cache)

        # Aşama 1: Executive Producer
        if _is_workflow_cancelled(workflow_id): return
        ep_out, ep_prov = await run_guarded("executive_producer")
        context["agent_outputs"]["executive_producer"] = ep_out
        providers.add(ep_prov)

        # Aşama 2: PARALEL [Trend Researcher + Audience Strategist]
        if _is_workflow_cancelled(workflow_id): return
        await asyncio.sleep(0.5)
        phase2_results = await asyncio.gather(
            run_guarded("trend_researcher"),
            run_guarded("audience_strategist"),
            return_exceptions=False
        )
        context["agent_outputs"]["trend_researcher"] = phase2_results[0][0]
        providers.add(phase2_results[0][1])
        context["agent_outputs"]["audience_strategist"] = phase2_results[1][0]
        providers.add(phase2_results[1][1])

        # Aşama 3: Creative Director
        if _is_workflow_cancelled(workflow_id): return
        await asyncio.sleep(0.8)
        cd_out, cd_prov = await run_guarded("creative_director")
        context["agent_outputs"]["creative_director"] = cd_out
        providers.add(cd_prov)

        # Aşama 4: Lead Scriptwriter
        if _is_workflow_cancelled(workflow_id): return
        await asyncio.sleep(0.8)
        sw_out, sw_prov = await run_guarded("scriptwriter")
        context["agent_outputs"]["scriptwriter"] = sw_out
        providers.add(sw_prov)

        # Aşama 5: PARALEL [Fact Checker + Visual Producer + Localization Editor]
        if _is_workflow_cancelled(workflow_id): return
        await asyncio.sleep(0.5)
        phase5_keys = ["fact_checker", "visual_producer", "localization_editor"]
        phase5_results = await asyncio.gather(
            *(run_guarded(k) for k in phase5_keys),
            return_exceptions=False
        )
        for k, (adv_out, adv_prov) in zip(phase5_keys, phase5_results):
            context["agent_outputs"][k] = adv_out
            providers.add(adv_prov)

        # Aşama 6: Quality Auditor & Publishing Strategist
        for final_key in ["quality_auditor", "publishing_strategist"]:
            if _is_workflow_cancelled(workflow_id): return
            await asyncio.sleep(0.4)
            try:
                f_out, f_prov = await run_guarded(final_key)
                context["agent_outputs"][final_key] = f_out
                providers.add(f_prov)
            except Exception as e:
                print(f"[Workflow] {final_key} uyarısı: {e}")

        # Senaryoyu Hazırla
        script_output = context["agent_outputs"].get("scriptwriter", {}).get("deliverable", {})
        script_data = script_output.get("script", script_output) if isinstance(script_output, dict) else {}
        hook = script_data.get("hook", "")
        narration = script_data.get("narration", "")
        scenes = script_data.get("scenes", [])
        if not scenes and isinstance(script_output, dict) and "scenes" in script_output:
            scenes = script_output["scenes"]

        if not scenes:
            scenes = [
                {"time": "0-4s", "shot": "Geniş sinematik dikey plan", "visual": request.topic, "on_screen_text": hook or request.topic, "narration": hook or request.topic},
                {"time": "4-10s", "shot": "Orta çekim detay", "visual": request.topic, "on_screen_text": narration[:45] if narration else request.topic, "narration": narration or request.topic}
            ]

        qa_scores = context["agent_outputs"].get("quality_auditor", {}).get("deliverable", {}).get("scores", {})
        score = qa_scores.get("total", 85) if isinstance(qa_scores, dict) else 85
        script_id = str(uuid.uuid4())

        # -------------------------------------------------------------
        # OTOMATİK KURGU MOTORU (SESLENDİRME + GÖRSEL İNDİRME + MONTAJ)
        # -------------------------------------------------------------
        # 1. Otomatik Doğal Seslendirme (Edge-TTS)
        voice_fn = None
        voice_text = narration or hook or ""
        if not voice_text and scenes:
            voice_text = " ".join([sc.get("narration") or sc.get("on_screen_text") or "" for sc in scenes]).strip()

        if voice_text:
            try:
                voice_fn, _ = await generate_speech(voice_text, language=request.language or "tr")
                print(f"[Workflow] Edge-TTS Seslendirme hazırlandı: {voice_fn}")
            except Exception as e:
                print(f"[Workflow] Otomatik seslendirme uyarısı: {e}")

        # 2. Sahneler için Görsel Zeka Motoru ile en uygun dikey videoları bul, puanla ve sahnelere bağla
        curated_assets = []
        if scenes:
            try:
                from app.visual_curator import curate_all_scenes_visuals
                curated_assets = await curate_all_scenes_visuals(scenes, target_duration=float(request.duration or 35))
                with conn() as c:
                    for it in curated_assets:
                        meta_str = json.dumps({"match_score": it.get("match_score", 85), "alternatives": it.get("alternatives", [])}, ensure_ascii=False)
                        c.execute(
                            "INSERT OR REPLACE INTO assets (id, filename, stored_name, kind, source_url, license_name, commercial_ok, attribution, notes, asset_type, metadata_json, created_at) "
                            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                            (
                                it["id"], it["filename"], it["stored_name"],
                                it["kind"], it["source_url"], it["license_name"],
                                it["commercial_ok"], it["attribution"], it["notes"],
                                "stock_video", meta_str, now()
                            )
                        )
                print(f"[Workflow] {len(curated_assets)} dikey video görsel zeka ile puanlanarak arşive indirildi.")
            except Exception as e:
                print(f"[Workflow] Otomatik görsel küratör uyarısı: {e}")

        # İndirilen videoları doğrudan sahne kurgusuna ekle!
        if curated_assets and scenes:
            for idx, sc in enumerate(scenes):
                matched = next((a for a in curated_assets if a.get("scene_index") == idx), None)
                if not matched and curated_assets:
                    matched = curated_assets[idx % len(curated_assets)]
                if matched:
                    sc["asset_id"] = matched["id"]
                    sc["asset_filename"] = matched["filename"]
                    sc["asset_stored_name"] = matched["stored_name"]
                    sc["asset_url"] = f"/media/assets/{matched['stored_name']}"
                    sc["match_score"] = matched.get("match_score", 85)

        # 3. Senaryoyu ve sahne kurgusunu veritabanına kaydet
        with conn() as c:
            c.execute(
                "INSERT INTO scripts (id, project_id, title, language, hook, narration, scenes, score, review, voice_filename, created_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (
                    script_id, request.project_id, request.topic, request.language,
                    hook, narration, json.dumps(scenes, ensure_ascii=False),
                    int(score) if str(score).isdigit() else 85, None, voice_fn, now(),
                ),
            )

        # 4. Otomatik FFmpeg Sinematik Montajı Çalıştır (TikTok Safe-Zone Altyazı + Crossfade)
        video_filename = None
        render_qa_info = None
        usable = rows("SELECT * FROM assets WHERE kind IN ('video','image') AND commercial_ok=1 ORDER BY created_at DESC")
        if usable:
            try:
                montage_res = await assemble_smart_video(
                    script_id=script_id,
                    scenes=scenes,
                    usable_assets=usable,
                    voice_filename=voice_fn,
                    burn_subtitles=True,
                    transition_style="fade",
                    enable_ken_burns=True
                )
                render_qa_info = montage_res.get("qa")
                if montage_res.get("ok"):
                    video_filename = montage_res.get("filename")
                    print(f"[Workflow] Otomatik montaj ve Render QA doğrulandı: {video_filename}")
                else:
                    print(f"[Workflow] Render QA uyarısı (video üretildi fakat kalite standartlarını karşılamadı): {render_qa_info}")
                    video_filename = montage_res.get("filename")
            except Exception as e:
                print(f"[Workflow] Otomatik montaj uyarısı: {e}")

        # Workflow sonucunu güncelle
        result_payload = {
            "script_id": script_id,
            "voice_filename": voice_fn,
            "video_filename": video_filename,
            "curated_count": len(curated_assets),
            "render_qa": render_qa_info,
            "context": context
        }
        with conn() as c:
            c.execute(
                "UPDATE workflows SET status='awaiting_human_review', "
                "provider=?, result_json=?, updated_at=? WHERE id=?",
                (
                    ", ".join(sorted(providers)),
                    json.dumps(result_payload, ensure_ascii=False),
                    now(), workflow_id,
                ),
            )

    except Exception as exc:
        safe_err = _redact(str(exc))[:1500]
        with conn() as c:
            c.execute(
                "UPDATE workflows SET status='failed', error=?, updated_at=? WHERE id=?",
                (safe_err, now(), workflow_id),
            )
            c.execute(
                "UPDATE agent_executions SET status='skipped', finished_at=? "
                "WHERE workflow_id=? AND status='pending'",
                (now(), workflow_id),
            )


@app.on_event("startup")
def startup():
    init_db()


@app.get("/", response_class=HTMLResponse)
def home():
    return (ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")


@app.get("/api/dashboard")
def dashboard():
    total_content = one("SELECT COUNT(*) n FROM scripts")["n"]
    in_production = one("SELECT COUNT(*) n FROM workflows WHERE status NOT IN ('completed', 'failed', 'cancelled')")["n"]
    awaiting_review = one("SELECT COUNT(*) n FROM scripts WHERE review IS NULL OR review != 'approved'")["n"]
    ready_to_publish = one("SELECT COUNT(*) n FROM scripts WHERE review = 'approved'")["n"]
    scheduled_posts = one("SELECT COUNT(*) n FROM publishing_queue WHERE status = 'scheduled'")["n"]
    failed_tasks = one("SELECT COUNT(*) n FROM workflows WHERE status = 'failed'")["n"]

    return {
        "projects": rows("SELECT * FROM projects ORDER BY created_at DESC"),
        "ideas":    rows("SELECT * FROM ideas ORDER BY created_at DESC LIMIT 8"),
        "assets":   rows("SELECT * FROM assets ORDER BY created_at DESC LIMIT 12"),
        "tasks":    rows("SELECT * FROM tasks WHERE id LIKE 'agent-%' ORDER BY agent"),
        "scripts":  rows("SELECT * FROM scripts ORDER BY created_at DESC LIMIT 12"),
        "publishing_queue": rows("SELECT * FROM publishing_queue ORDER BY scheduled_at ASC LIMIT 6"),
        "stats": {
            "ideas":            one("SELECT COUNT(*) n FROM ideas")["n"],
            "scripts":          total_content,
            "assets":           one("SELECT COUNT(*) n FROM assets")["n"],
            "total_content":    total_content,
            "in_production":    in_production,
            "awaiting_review":  awaiting_review,
            "ready_to_publish": ready_to_publish,
            "scheduled_posts":  scheduled_posts,
            "failed_tasks":     failed_tasks,
        },
    }


@app.post("/api/workflows/run")
async def start_workflow(x: WorkflowIn, background_tasks: BackgroundTasks):
    workflow_id = str(uuid.uuid4())
    ts = now()
    with conn() as c:
        c.execute(
            "INSERT INTO workflows(id,topic,language,duration,status,created_at,updated_at) "
            "VALUES(?,?,?,?,?,?,?)",
            (workflow_id, x.topic, x.language, x.duration, "queued", ts, ts),
        )
        for agent in AGENT_DEFINITIONS:
            c.execute(
                "INSERT INTO agent_executions(id,workflow_id,agent_key,agent_name,department,status) "
                "VALUES(?,?,?,?,?,?)",
                (str(uuid.uuid4()), workflow_id, agent["key"],
                 agent["name"], agent["department"], "pending"),
            )
    background_tasks.add_task(execute_workflow, workflow_id, x)
    return {
        "workflow_id": workflow_id,
        "status": "queued",
        "agents": [
            {"key": a["key"], "name": a["name"], "department": a["department"]}
            for a in AGENT_DEFINITIONS
        ],
    }


@app.get("/api/workflows/{workflow_id}")
def get_workflow(workflow_id: str):
    data = _get_full_workflow(workflow_id)
    if not data:
        raise HTTPException(404, "İş akışı bulunamadı")
    return data


@app.get("/api/workflows/{workflow_id}/stream")
async def stream_workflow(workflow_id: str, request: Request):
    if not SSE_AVAILABLE:
        raise HTTPException(503, "SSE kütüphanesi yüklü değil.")

    async def event_gen():
        while True:
            if await request.is_disconnected():
                break
            data = _get_full_workflow(workflow_id)
            if not data:
                break
            yield {"data": json.dumps(data, ensure_ascii=False)}
            if data["status"] in ("awaiting_human_review", "failed", "completed", "approved", "revision_requested"):
                break
            await asyncio.sleep(1.2)

    return EventSourceResponse(event_gen())


# ---------------------------------------------------------------------------
# TTS (OTOMATİK SESLENDİRME) ENDPOINT
# ---------------------------------------------------------------------------

@app.post("/api/scripts/{script_id}/generate-voice")
async def generate_voice_for_script(script_id: str):
    script = one("SELECT * FROM scripts WHERE id=?", (script_id,))
    if not script:
        raise HTTPException(404, "Senaryo bulunamadı")
    
    text = script.get("narration") or script.get("hook") or ""
    if not text:
        raise HTTPException(400, "Senaryoda seslendirilecek metin bulunamadı")

    lang = script.get("language") or "tr"
    try:
        filename, rel_path = await generate_speech(text, language=lang)
        return {
            "ok": True,
            "filename": filename,
            "path": rel_path,
            "script_id": script_id,
            "message": "Doğal Türkçe seslendirme başarıyla oluşturuldu!"
        }
    except Exception as exc:
        raise HTTPException(500, f"Seslendirme oluşturulamadı: {exc}")


# ---------------------------------------------------------------------------
# PEXELS & PIXABAY STOK MEDYA ARAMA & OTONOM KÜRASYON
# ---------------------------------------------------------------------------

@app.post("/api/workflows/{workflow_id}/auto-curate")
async def auto_curate_workflow_media(workflow_id: str):
    """
    İş akışındaki Visual Producer çıktılarını kullanarak her sahne için
    en uygun stok videoları otomatik bulur, indirir ve arşive kaydeder.
    """
    wf = _get_full_workflow(workflow_id)
    if not wf:
        raise HTTPException(404, "İş akışı bulunamadı")
        
    vp_agent = next((a for a in wf.get("agents", []) if a["agent_key"] == "visual_producer"), None)
    if not vp_agent or not vp_agent.get("output"):
        raise HTTPException(400, "Görsel yapımcı çıktısı henüz hazır değil")
        
    visual_plan = vp_agent["output"].get("deliverable", {}).get("visual_plan", [])
    if not visual_plan:
        raise HTTPException(400, "Görsel plan sahneleri bulunamadı")
        
    curated = await auto_curate_scene_assets(visual_plan)
    with conn() as c:
        for it in curated:
            c.execute(
                "INSERT INTO assets VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    it["id"], it["filename"], it["stored_name"],
                    it["kind"], it["source_url"], it["license_name"],
                    it["commercial_ok"], it["attribution"], it["notes"], now()
                )
            )
    return {
        "ok": True,
        "count": len(curated),
        "assets": curated,
        "message": f"{len(curated)} sahne için en uygun stok videolar otonom olarak indirildi ve arşive eklendi."
    }


@app.post("/api/scripts/{script_id}/full-autonomous-production")
async def full_autonomous_production(script_id: str):
    """
    TEK TIKLA TAM OTONOM ÜRETİM:
    1. Senaryoyu Edge-TTS ile otomatik seslendir.
    2. Sahneler için Pexels'ten dikey HD videoları otomatik bul, indir ve sahnelere bağla.
    3. FFmpeg ile sinematik geçişli ve güvenli bölge altyazılı montajı yap.
    4. TikTok paketini hazırla.
    """
    try:
        script = one("SELECT * FROM scripts WHERE id=?", (script_id,))
        if not script:
            raise HTTPException(404, "Senaryo bulunamadı")
            
        # 1. Seslendirme üret (Edge-TTS)
        narration_text = script.get("narration") or script.get("hook") or ""
        scenes = []
        if script.get("scenes"):
            try:
                scenes = json.loads(script["scenes"])
            except Exception:
                scenes = []

        if not narration_text and scenes:
            narration_text = " ".join([sc.get("narration") or sc.get("on_screen_text") or "" for sc in scenes]).strip()

        voice_fn = script.get("voice_filename")
        if narration_text:
            try:
                voice_fn, _ = await generate_speech(narration_text, language=script.get("language") or "tr")
            except Exception as e:
                print(f"[Autonomous Production] Seslendirme uyarısı: {e}")

        # 2. Eksik sahne medyalarını Görsel Zeka Motoru ile bul, puanla ve sahneye bağla
        missing_scenes = [sc for sc in scenes if not sc.get("asset_stored_name")]
        if missing_scenes:
            try:
                from app.visual_curator import curate_all_scenes_visuals
                curated = await curate_all_scenes_visuals(scenes, target_duration=35.0)
                with conn() as c:
                    for it in curated:
                        meta_str = json.dumps({"match_score": it.get("match_score", 85), "alternatives": it.get("alternatives", [])}, ensure_ascii=False)
                        c.execute(
                            "INSERT OR REPLACE INTO assets (id, filename, stored_name, kind, source_url, license_name, commercial_ok, attribution, notes, asset_type, metadata_json, created_at) "
                            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                            (
                                it["id"], it["filename"], it["stored_name"],
                                it["kind"], it["source_url"], it["license_name"],
                                it["commercial_ok"], it["attribution"], it["notes"],
                                "stock_video", meta_str, now()
                            )
                        )
                for it in curated:
                    idx = it.get("scene_index")
                    if idx is not None and idx < len(scenes):
                        scenes[idx]["asset_id"] = it["id"]
                        scenes[idx]["asset_filename"] = it["filename"]
                        scenes[idx]["asset_stored_name"] = it["stored_name"]
                        scenes[idx]["asset_url"] = f"/media/assets/{it['stored_name']}"
                        scenes[idx]["match_score"] = it.get("match_score", 85)
            except Exception as e:
                print(f"[Autonomous Production] Görsel arama uyarısı: {e}")

        # Sahne ve seslendirme verilerini senaryoda güncelle
        with conn() as c:
            c.execute(
                "UPDATE scripts SET scenes=?, voice_filename=? WHERE id=?",
                (json.dumps(scenes, ensure_ascii=False), voice_fn, script_id)
            )

        # 3. Mevcut ticari onaylı medyaları al
        usable = rows("SELECT * FROM assets WHERE kind IN ('video','image') AND commercial_ok=1 ORDER BY created_at DESC")
        if not usable:
            usable = rows("SELECT * FROM assets WHERE kind IN ('video','image') ORDER BY created_at DESC")
        if not usable:
            raise HTTPException(400, "Montaj için medya bulunamadı. Lütfen Medya Kütüphanesi'nden stok video indirin.")

        # 4. Sinematik Montaj
        result = await assemble_smart_video(
            script_id=script_id,
            scenes=scenes,
            usable_assets=usable,
            voice_filename=voice_fn,
            burn_subtitles=True,
            transition_style="fade",
            enable_ken_burns=True
        )
        result["voice_filename"] = voice_fn
        result["message"] = "Tam otonom kurgu tamamlandı! Seslendirme, dikey videolar, geçiş efektleri ve altyazılar hazırlandı."
        return result
    except HTTPException:
        raise
    except Exception as exc:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Otonom kurgu hatası: {_redact(str(exc))}")


@app.get("/api/stock/search")
async def search_stock(q: str, limit: int = 8):
    if not q.strip():
        return []
    items = await search_stock_media(q.strip(), limit=limit)
    return items


@app.post("/api/stock/download")
async def download_stock(item: StockDownloadIn):
    try:
        saved = await download_and_save_asset(item.dict())
        with conn() as c:
            c.execute(
                "INSERT INTO assets VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    saved["id"], saved["filename"], saved["stored_name"],
                    saved["kind"], saved["source_url"], saved["license_name"],
                    saved["commercial_ok"], saved["attribution"], saved["notes"], now()
                )
            )
        return {"ok": True, "asset": saved}
    except Exception as exc:
        raise HTTPException(500, f"Medya indirme hatası: {exc}")


# ---------------------------------------------------------------------------
# ASSETS & VOICE UPLOAD
# ---------------------------------------------------------------------------

def _safe_filename(raw: str) -> str:
    name = Path(raw).name
    name = re.sub(r"[^\w.\-]", "_", name)
    return name or "upload"


@app.post("/api/assets")
async def upload_asset(
    file: UploadFile = File(...),
    kind: str = Form("video"),
    source_url: str = Form(""),
    license_name: str = Form("Unverified"),
    commercial_ok: bool = Form(False),
    attribution: str = Form(""),
    notes: str = Form(""),
):
    safe_name = _safe_filename(file.filename or "asset")
    ext = Path(safe_name).suffix.lower()
    if ext not in ALLOWED_ASSET_EXT:
        raise HTTPException(400, "Desteklenmeyen dosya türü")
    aid = str(uuid.uuid4())
    stored = aid + ext
    dest = ASSETS / stored
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)
    with conn() as c:
        c.execute(
            "INSERT INTO assets VALUES(?,?,?,?,?,?,?,?,?,?)",
            (aid, safe_name, stored, kind, source_url,
             license_name, int(commercial_ok), attribution, notes, now()),
        )
    return {
        "ok": True, "id": aid, "filename": safe_name,
        "license_status": "verified" if commercial_ok else "needs_review",
    }


@app.get("/api/assets/{asset_id}/file")
def asset_file(asset_id: str):
    a = one("SELECT * FROM assets WHERE id=?", (asset_id,))
    if not a:
        raise HTTPException(404, "Dosya bulunamadı")
    return FileResponse(ASSETS / a["stored_name"], filename=a["filename"])


@app.post("/api/voice")
async def upload_voice(file: UploadFile = File(...), script_id: str = Form("")):
    safe_name = _safe_filename(file.filename or "voice.wav")
    ext = Path(safe_name).suffix.lower()
    if ext not in ALLOWED_AUDIO_EXT:
        raise HTTPException(400, "Ses formatı desteklenmiyor")
    name = str(uuid.uuid4()) + ext
    dest = VOICE / name
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)
    return {
        "ok": True, "filename": name,
        "path": str(dest.relative_to(ROOT)), "script_id": script_id,
    }


# ---------------------------------------------------------------------------
# SCRIPT REVIEW
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# SCRIPT CRUD (DÜZENLEME, SAHNE GÜNCELLEME & SİLME)
# ---------------------------------------------------------------------------

@app.get("/api/scripts/{script_id}")
def get_script_detail(script_id: str):
    s = one("SELECT * FROM scripts WHERE id=?", (script_id,))
    if not s:
        raise HTTPException(404, "Senaryo bulunamadı")
    res = dict(s)
    if res.get("scenes"):
        try:
            res["scenes"] = json.loads(res["scenes"])
        except Exception:
            res["scenes"] = []
    else:
        res["scenes"] = []
    return res


@app.put("/api/scripts/{script_id}")
def update_script(script_id: str, x: ScriptUpdateIn):
    s = one("SELECT * FROM scripts WHERE id=?", (script_id,))
    if not s:
        raise HTTPException(404, "Senaryo bulunamadı")
        
    title = x.title if x.title is not None else s["title"]
    hook = x.hook if x.hook is not None else s["hook"]
    narration = x.narration if x.narration is not None else s["narration"]
    scenes_json = json.dumps(x.scenes, ensure_ascii=False) if x.scenes is not None else s["scenes"]
    review = x.review if x.review is not None else s["review"]
    
    with conn() as c:
        c.execute(
            "UPDATE scripts SET title=?, hook=?, narration=?, scenes=?, review=? WHERE id=?",
            (title, hook, narration, scenes_json, review, script_id)
        )
    return {"ok": True, "message": "Senaryo ve sahneler başarıyla güncellendi."}


@app.delete("/api/scripts/{script_id}")
def delete_script(script_id: str):
    with conn() as c:
        c.execute("DELETE FROM scripts WHERE id=?", (script_id,))
    return {"ok": True, "message": "Senaryo arşivden silindi."}


@app.post("/api/scripts/{script_id}/review")
def review_script(script_id: str, x: StatusIn):
    if x.status not in ("approved", "revision"):
        raise HTTPException(400, "Geçersiz karar")
    with conn() as c:
        c.execute("UPDATE scripts SET review=? WHERE id=?", (x.status, script_id))
        wf_row = c.execute(
            "SELECT id FROM workflows WHERE result_json LIKE ? AND status='awaiting_human_review'",
            (f'%"script_id": "{script_id}"%',),
        ).fetchone()
        if wf_row:
            new_wf_status = "approved" if x.status == "approved" else "revision_requested"
            c.execute(
                "UPDATE workflows SET status=?, updated_at=? WHERE id=?",
                (new_wf_status, now(), wf_row["id"]),
            )
    return {"ok": True}


# ---------------------------------------------------------------------------
# AKILLI SAHNE BAZLI VİDEO MONTAJI & TIKTOK PAKETİ
# ---------------------------------------------------------------------------

@app.post("/api/export/{script_id}")
async def export_video_smart(
    script_id: str,
    voice_filename: Optional[str] = Form(None),
    burn_subtitles: bool = Form(True)
):
    script = one("SELECT * FROM scripts WHERE id=?", (script_id,))
    if not script:
        raise HTTPException(404, "Senaryo bulunamadı")
        
    usable = rows("SELECT * FROM assets WHERE kind IN ('video','image') AND commercial_ok=1 ORDER BY created_at DESC")
    if not usable:
        raise HTTPException(400, "Ticari onaylı medya bulunamadı. Stok medyadan otomatik indirin veya arşive medya ekleyin.")

    scenes = []
    if script.get("scenes"):
        try:
            scenes = json.loads(script["scenes"])
        except Exception:
            scenes = []

    try:
        result = await assemble_smart_video(
            script_id=script_id,
            scenes=scenes,
            usable_assets=usable,
            voice_filename=voice_filename,
            burn_subtitles=burn_subtitles
        )
        return result
    except Exception as exc:
        raise HTTPException(500, str(exc))


@app.get("/api/export/{script_id}/tiktok-package")
def export_tiktok_package(script_id: str):
    """TikTok için hazır yayın paketi (Video + Caption TXT + Bilgiler)"""
    script = one("SELECT * FROM scripts WHERE id=?", (script_id,))
    if not script:
        raise HTTPException(404, "Senaryo bulunamadı")
    
    mp4_name = f"eski_usul_{script_id[:8]}.mp4"
    mp4_path = EXPORTS / mp4_name
    if not mp4_path.exists():
        raise HTTPException(400, "Önce video taslağını oluşturun.")

    zip_filename = f"tiktok_package_{script_id[:8]}.zip"
    zip_path = EXPORTS / zip_filename
    
    # Caption ve Hashtag hazırla
    caption_text = f"{script.get('hook', '')}\n\n#eskiusul #istanbul #yavaşyaşa #keşfet"
    
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.write(mp4_path, arcname=mp4_name)
        zf.writestr("tiktok_caption.txt", caption_text)
        zf.writestr("script_details.json", json.dumps(dict(script), ensure_ascii=False, indent=2))
        
    return FileResponse(zip_path, filename=zip_filename, media_type="application/zip")


@app.get("/api/exports/{filename}")
def get_export(filename: str):
    path = EXPORTS / Path(_safe_filename(filename)).name
    if not path.exists():
        raise HTTPException(404, "Çıktı bulunamadı")
    return FileResponse(path, media_type="video/mp4", filename=path.name)


@app.post("/api/ideas")
def add_idea(x: IdeaIn):
    i = str(uuid.uuid4())
    with conn() as c:
        c.execute("INSERT INTO ideas VALUES(?,?,?,?,?,?,?)", (i, x.title, x.angle, x.language, 0, "new", now()))
    return {"ok": True, "id": i}


@app.post("/api/metrics")
def add_metrics(x: MetricIn):
    mid = str(uuid.uuid4())
    with conn() as c:
        c.execute(
            "INSERT INTO metrics VALUES(?,?,?,?,?,?,?,?,?)",
            (mid, x.project_id, x.views, x.avg_watch, x.saves, x.shares, x.followers, x.notes, now())
        )
    return {"ok": True, "id": mid}


@app.get("/api/metrics")
def get_metrics():
    return rows("SELECT * FROM metrics ORDER BY created_at DESC LIMIT 30")


# ---------------------------------------------------------------------------
# AYARLAR (SETTINGS) ENDPOINTS
# ---------------------------------------------------------------------------

class SettingsIn(BaseModel):
    gemini_api_key: Optional[str] = ""
    gemini_model: Optional[str] = "gemini-2.5-flash"
    groq_api_key: Optional[str] = ""
    groq_model: Optional[str] = "llama-3.3-70b-versatile"
    pexels_api_key: Optional[str] = ""
    pixabay_api_key: Optional[str] = ""
    hf_token: Optional[str] = ""
    hf_llm_model: Optional[str] = "Qwen/Qwen2.5-72B-Instruct"
    hf_image_model: Optional[str] = "black-forest-labs/FLUX.1-schnell"


class GenerateSceneVisualIn(BaseModel):
    prompt: str
    scene_index: Optional[int] = 0
    script_id: Optional[str] = None


@app.post("/api/ai/generate-scene-visual")
async def api_generate_scene_visual(x: GenerateSceneVisualIn):
    from app.hf_service import generate_hf_scene_visual
    prompt = x.prompt.strip()
    if not prompt:
        raise HTTPException(400, "Görsel talimatı (prompt) boş olamaz.")
    
    asset = await generate_hf_scene_visual(prompt)
    if not asset:
        raise HTTPException(502, "Hugging Face (FLUX.1-schnell) modelinden görsel üretilemedi. Model meşgul veya bağlantı zaman aşımına uğramış olabilir.")
    
    with conn() as c:
        c.execute(
            "INSERT OR REPLACE INTO assets (id, filename, stored_name, kind, source_url, license_name, commercial_ok, attribution, notes, asset_type, metadata_json, created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                asset["id"], asset["filename"], asset["stored_name"],
                asset["kind"], asset["source_url"], asset["license_name"],
                asset["commercial_ok"], asset["attribution"], asset["notes"],
                "ai_image", json.dumps({"generator": "FLUX.1-schnell"}, ensure_ascii=False), now()
            )
        )
        if x.script_id:
            row = c.execute("SELECT scenes FROM scripts WHERE id=?", (x.script_id,)).fetchone()
            if row and row["scenes"]:
                try:
                    sc_list = json.loads(row["scenes"])
                    if 0 <= (x.scene_index or 0) < len(sc_list):
                        idx = x.scene_index or 0
                        sc_list[idx]["asset_id"] = asset["id"]
                        sc_list[idx]["asset_filename"] = asset["filename"]
                        sc_list[idx]["asset_stored_name"] = asset["stored_name"]
                        sc_list[idx]["asset_url"] = f"/media/assets/{asset['stored_name']}"
                        sc_list[idx]["is_image"] = True
                        c.execute("UPDATE scripts SET scenes=? WHERE id=?", (json.dumps(sc_list, ensure_ascii=False), x.script_id))
                except Exception as err:
                    print(f"Sahne güncelleme hatası: {err}")

    return {"ok": True, "asset": asset, "message": "FLUX.1 ile 9:16 sahne görseli başarıyla üretildi!"}


class HookVariationsIn(BaseModel):
    topic: str
    language: Optional[str] = "tr"
    duration: Optional[int] = 35


@app.post("/api/ai/generate-hook-variations")
async def api_generate_hook_variations(x: HookVariationsIn):
    """
    Creatify & Creatok Modeli:
    Kullanıcının konusundan 3 farklı viral hook/açılış varyasyonu üretir:
    1. Merak Uyandıran İlk Gözlem (Curiosity Hook)
    2. Şok Edici İtiraf / Sır (Contrarian/Secret Hook)
    3. Sakin & Duyusal Çekim (Sensory/Atmospheric Hook)
    """
    topic = x.topic.strip()
    if not topic:
        raise HTTPException(400, "Konu boş olamaz.")

    variations = [
        {
            "id": "var_curiosity",
            "hook_type": "Merak Uyandıran İlk Gözlem",
            "hook_type_badge": "🎯 MERAK KANCASI",
            "hook_sentence": f"İstanbul'un ortasında herkesin yanından geçip kimsenin fark etmediği bir an var: {topic}.",
            "visual_plan": "Karaköy vapurundan Galata'ya doğru sakin ve buğulu bir akşam çekimi, dikey 9:16.",
            "target_emotion": "Merak & Şehir Hafızası",
            "recommended_duration": 30
        },
        {
            "id": "var_contrarian",
            "hook_type": "Zıt Bakış & Çarpıcı Tespit",
            "hook_type_badge": "⚡ ÇARPICI KANCA",
            "hook_sentence": f"Bize sürekli koşturmamız gerektiği söylendi ama {topic} bize bambaşka bir hikaye anlatıyor.",
            "visual_plan": "Telaşla yürüyen kalabalığın ortasında duran sıcak bir çay bardağına makro yakın plan.",
            "target_emotion": "Farkındalık & Dinginlik",
            "recommended_duration": 35
        },
        {
            "id": "var_sensory",
            "hook_type": "Atmosferik & Duyusal Giriş",
            "hook_type_badge": "🌿 ATMOSFERİK KANCA",
            "hook_sentence": f"Günün telaşı dinerken martıların sesini ve serin rüzgarı dinleyin; işte {topic}.",
            "visual_plan": "Boğaz vapurunun dalgaları, gün batımı altın saat tonları, sinematik ağır çekim.",
            "target_emotion": "Huzur & Nostalji",
            "recommended_duration": 40
        }
    ]

    return {"ok": True, "topic": topic, "variations": variations}


@app.get("/api/settings")
def get_settings():
    env = _read_env()
    # Mask key for security preview
    def mask(k: str) -> str:
        val = env.get(k, "")
        if not val:
            return ""
        if len(val) <= 8:
            return "******"
        return val[:6] + "..." + val[-4:]

    return {
        "gemini_api_key": mask("GEMINI_API_KEY"),
        "gemini_api_key_configured": bool(env.get("GEMINI_API_KEY")),
        "gemini_model": env.get("GEMINI_MODEL", "gemini-2.5-flash"),
        "groq_api_key": mask("GROQ_API_KEY"),
        "groq_api_key_configured": bool(env.get("GROQ_API_KEY")),
        "groq_model": env.get("GROQ_MODEL", "llama-3.3-70b-versatile"),
        "pexels_api_key": mask("PEXELS_API_KEY"),
        "pexels_api_key_configured": bool(env.get("PEXELS_API_KEY")),
        "pixabay_api_key": mask("PIXABAY_API_KEY"),
        "pixabay_api_key_configured": bool(env.get("PIXABAY_API_KEY")),
        "hf_token": mask("HF_TOKEN"),
        "hf_token_configured": bool(env.get("HF_TOKEN")),
        "hf_llm_model": env.get("HF_LLM_MODEL", "Qwen/Qwen2.5-72B-Instruct"),
        "hf_image_model": env.get("HF_IMAGE_MODEL", "black-forest-labs/FLUX.1-schnell"),
        "ffmpeg_installed": is_ffmpeg_available(),
        "system_status": "optimal"
    }


@app.post("/api/settings")
def update_settings(x: SettingsIn):
    env_path = ROOT / ".env"
    existing = _read_env()
    
    # Sadece yeni/değişen anahtarları güncelle
    if x.gemini_api_key and not x.gemini_api_key.startswith("***"):
        existing["GEMINI_API_KEY"] = x.gemini_api_key.strip()
    if x.gemini_model:
        existing["GEMINI_MODEL"] = x.gemini_model.strip()
        
    if x.groq_api_key and not x.groq_api_key.startswith("***"):
        existing["GROQ_API_KEY"] = x.groq_api_key.strip()
    if x.groq_model:
        existing["GROQ_MODEL"] = x.groq_model.strip()
        
    if x.pexels_api_key and not x.pexels_api_key.startswith("***"):
        existing["PEXELS_API_KEY"] = x.pexels_api_key.strip()
    if x.pixabay_api_key and not x.pixabay_api_key.startswith("***"):
        existing["PIXABAY_API_KEY"] = x.pixabay_api_key.strip()

    if x.hf_token and not x.hf_token.startswith("***"):
        existing["HF_TOKEN"] = x.hf_token.strip()
    if x.hf_llm_model:
        existing["HF_LLM_MODEL"] = x.hf_llm_model.strip()
    if x.hf_image_model:
        existing["HF_IMAGE_MODEL"] = x.hf_image_model.strip()

    lines = [
        f"# Eski Usul AI Studio Yapılandırması",
        f"GEMINI_API_KEY={existing.get('GEMINI_API_KEY', '')}",
        f"GEMINI_MODEL={existing.get('GEMINI_MODEL', 'gemini-2.5-flash')}",
        f"GROQ_API_KEY={existing.get('GROQ_API_KEY', '')}",
        f"GROQ_MODEL={existing.get('GROQ_MODEL', 'llama-3.3-70b-versatile')}",
        f"OLLAMA_BASE_URL={existing.get('OLLAMA_BASE_URL', 'http://localhost:11434')}",
        f"OLLAMA_MODEL={existing.get('OLLAMA_MODEL', 'qwen2.5:7b')}",
        f"APP_HOST=127.0.0.1",
        f"APP_PORT=8765",
        f"PEXELS_API_KEY={existing.get('PEXELS_API_KEY', '')}",
        f"PIXABAY_API_KEY={existing.get('PIXABAY_API_KEY', '')}",
        f"HF_TOKEN={existing.get('HF_TOKEN', '')}",
        f"HF_LLM_MODEL={existing.get('HF_LLM_MODEL', 'Qwen/Qwen2.5-72B-Instruct')}",
        f"HF_IMAGE_MODEL={existing.get('HF_IMAGE_MODEL', 'black-forest-labs/FLUX.1-schnell')}",
    ]
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"ok": True, "message": "Ayarlar başarıyla kaydedildi ve uygulandı."}


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "version": "0.5.0",
        "ffmpeg": is_ffmpeg_available(),
        "database": DB.exists(),
        "sse": SSE_AVAILABLE,
        "mode": "local-first",
    }


# ---------------------------------------------------------------------------
# FAZ 1 & 5: QUALITY GUARD (KALİTE KONTROL KARNESİ)
# ---------------------------------------------------------------------------

@app.get("/api/scripts/{script_id}/qa")
async def get_script_quality_audit(script_id: str):
    from app.quality_guard import perform_full_studio_qa
    script = one("SELECT * FROM scripts WHERE id=?", (script_id,))
    if not script:
        raise HTTPException(404, "Senaryo bulunamadı")
    
    voice_fn = script.get("voice_filename")
    voice_path = (VOICE / voice_fn) if voice_fn else None

    # Eğer video renderı varsa onun QA'ini de al
    render_qa = None
    mp4_name = f"eski_usul_{script_id[:8]}.mp4"
    mp4_path = EXPORTS / mp4_name
    if mp4_path.exists():
        from app.video_editor import validate_video_render, get_ffmpeg_bin
        qa_res = await validate_video_render(get_ffmpeg_bin(), mp4_path)
        render_qa = qa_res.to_dict()

    audit = perform_full_studio_qa(dict(script), voice_file_path=voice_path, render_qa_dict=render_qa)
    return audit.to_dict()


# ---------------------------------------------------------------------------
# FAZ 2: GENİŞLETİLMİŞ MEDYA KÜTÜPHANESİ
# ---------------------------------------------------------------------------

@app.get("/api/media")
def list_media_library(asset_type: Optional[str] = None, kind: Optional[str] = None, q: Optional[str] = None):
    from app.media_manager import query_assets_library
    return query_assets_library(asset_type=asset_type, kind=kind, search_query=q)


@app.post("/api/media/{asset_id}/thumbnail")
async def generate_media_thumbnail(asset_id: str):
    from app.media_manager import generate_video_thumbnail
    a = one("SELECT * FROM assets WHERE id=?", (asset_id,))
    if not a:
        raise HTTPException(404, "Medya bulunamadı")
    
    stored = a.get("stored_name")
    if not stored:
        raise HTTPException(400, "Dosya adı eksik")

    src = ASSETS / stored
    if not src.exists():
        raise HTTPException(404, "Dosya diskte bulunamadı")

    thumb_name = f"thumb_{asset_id[:8]}.jpg"
    thumb_path = THUMBNAILS / thumb_name
    success = await generate_video_thumbnail(src, thumb_path, at_second=1.0)
    if success:
        with conn() as c:
            c.execute("UPDATE assets SET thumbnail_path=? WHERE id=?", (f"/media/thumbnails/{thumb_name}", asset_id))
        return {"ok": True, "thumbnail_url": f"/media/thumbnails/{thumb_name}"}
    raise HTTPException(500, "Thumbnail oluşturulamadı.")


# ---------------------------------------------------------------------------
# FAZ 4: YAYIN TAKVİMİ, KUYRUK VE SOSYAL HESAPLAR
# ---------------------------------------------------------------------------

class SchedulePostIn(BaseModel):
    video_filename: str
    caption: str
    scheduled_at: str
    hashtags: Optional[list[str]] = None
    platform: str = "tiktok"
    account_id: Optional[str] = None
    script_id: Optional[str] = None


@app.get("/api/publishing/calendar")
def get_calendar():
    from app.publishing_service import get_publishing_calendar
    return get_publishing_calendar()


@app.post("/api/publishing/schedule")
def schedule_post(x: SchedulePostIn):
    from app.publishing_service import add_to_publishing_queue
    res = add_to_publishing_queue(
        video_filename=x.video_filename,
        caption=x.caption,
        scheduled_at=x.scheduled_at,
        hashtags=x.hashtags,
        platform=x.platform,
        account_id=x.account_id,
        script_id=x.script_id
    )
    return res


@app.get("/api/social-accounts")
def get_social_accounts():
    return rows("SELECT id, platform, account_name, account_handle, avatar_url, status, created_at FROM social_accounts")


# ---------------------------------------------------------------------------
# FAZ 5: ANALİTİK & SÜREKLİ ÖĞRENME
# ---------------------------------------------------------------------------

class AnalyticsRecordIn(BaseModel):
    project_id: str
    script_id: Optional[str] = None
    post_id: Optional[str] = None
    platform: str = "tiktok"
    views: int = 0
    likes: int = 0
    comments: int = 0
    shares: int = 0
    saves: int = 0
    avg_watch_time: float = 0.0
    completion_rate: float = 0.0
    notes: Optional[str] = ""


@app.get("/api/analytics/insights")
def get_insights():
    from app.analytics_engine import analyze_performance_patterns
    return analyze_performance_patterns()


@app.post("/api/analytics/record")
def post_analytics_record(x: AnalyticsRecordIn):
    from app.analytics_engine import record_content_metrics
    return record_content_metrics(
        project_id=x.project_id,
        script_id=x.script_id,
        post_id=x.post_id,
        platform=x.platform,
        views=x.views,
        likes=x.likes,
        comments=x.comments,
        shares=x.shares,
        saves=x.saves,
        avg_watch_time=x.avg_watch_time,
        completion_rate=x.completion_rate,
        notes=x.notes or ""
    )


# ---------------------------------------------------------------------------
# MARKA & SES AYARLARI (BRAND & VOICE SETTINGS)
# ---------------------------------------------------------------------------

class BrandSettingsIn(BaseModel):
    brand_name: str
    spirit: str
    tone: str
    primary_voice_tr: str
    primary_voice_en: str
    primary_voice_ar: str
    forbidden_words: Optional[list[str]] = None


@app.get("/api/brand-settings")
def get_brand_settings():
    row = one("SELECT * FROM brand_settings WHERE id='default'")
    if not row:
        return {
            "brand_name": "Eski Usul",
            "spirit": "Hayat, ekrandan ibaret değil.",
            "tone": "curious, observant, warm, grounded",
            "primary_voice_tr": "tr-TR-AhmetNeural",
            "primary_voice_en": "en-US-ChristopherNeural",
            "primary_voice_ar": "ar-SA-HamedNeural",
            "forbidden_words": ["carpe diem", "life is short", "put down your phone"]
        }
    res = dict(row)
    if isinstance(res.get("forbidden_words"), str):
        try:
            res["forbidden_words"] = json.loads(res["forbidden_words"])
        except Exception:
            res["forbidden_words"] = []
    return res


@app.post("/api/brand-settings")
def update_brand_settings(x: BrandSettingsIn):
    words_json = json.dumps(x.forbidden_words or [], ensure_ascii=False)
    with conn() as c:
        c.execute("""
            INSERT INTO brand_settings (id, brand_name, spirit, tone, primary_voice_tr, primary_voice_en, primary_voice_ar, forbidden_words, updated_at)
            VALUES ('default', ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                brand_name=excluded.brand_name,
                spirit=excluded.spirit,
                tone=excluded.tone,
                primary_voice_tr=excluded.primary_voice_tr,
                primary_voice_en=excluded.primary_voice_en,
                primary_voice_ar=excluded.primary_voice_ar,
                forbidden_words=excluded.forbidden_words,
                updated_at=excluded.updated_at
        """, (x.brand_name, x.spirit, x.tone, x.primary_voice_tr, x.primary_voice_en, x.primary_voice_ar, words_json, now()))
    return {"ok": True, "message": "Marka ve ses ayarları güncellendi."}
