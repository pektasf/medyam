"""
Eski Usul AI Studio — Video Engine Orchestrator
Tüm alt modülleri birleştirerek uçtan uca akıllı montaj ve render doğrulaması yapar.
"""
from __future__ import annotations

import asyncio
import os
import shutil
import uuid
from pathlib import Path
from typing import Any

from app.video_engine.timeline_builder import build_timeline_from_scenes
from app.video_engine.scene_processor import process_scene_clip
from app.video_engine.transition_engine import render_merged_video_with_transitions
from app.video_engine.audio_mixer import mix_audio_track
from app.video_engine.subtitle_renderer import generate_srt_content, build_subtitle_filter
from app.video_engine.render_validator import validate_video_render

ROOT = Path(__file__).resolve().parents[2]
EXPORTS = ROOT / "data" / "media" / "exports"
VOICE = ROOT / "data" / "media" / "voice"
ASSETS = ROOT / "data" / "media" / "assets"
PROJECTS = ROOT / "data" / "projects"
BGM_DIR = ROOT / "data" / "media" / "bgm"

for p in [EXPORTS, VOICE, ASSETS, PROJECTS, BGM_DIR]:
    p.mkdir(parents=True, exist_ok=True)


def get_ffmpeg_bin() -> str:
    which = shutil.which("ffmpeg")
    if which:
        return which
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def is_ffmpeg_available() -> bool:
    try:
        bin_path = get_ffmpeg_bin()
        return bool(bin_path and (shutil.which(bin_path) or Path(bin_path).exists()))
    except Exception:
        return False


async def get_audio_duration_seconds(audio_path: Path) -> float:
    """FFmpeg ile ses dosyasının süresini milisaniye hassasiyetinde okur."""
    ffmpeg = get_ffmpeg_bin()
    cmd = [ffmpeg, "-i", str(audio_path)]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    _, stderr_bytes = await proc.communicate()
    import re
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", stderr_bytes.decode("utf-8", errors="ignore"))
    if match:
        h, m, s = match.groups()
        return int(h) * 3600 + int(m) * 60 + float(s)
    return 30.0


ACTIVE_RENDER_PROCESSES: dict[str, asyncio.subprocess.Process] = {}


def kill_active_render(script_or_workflow_id: str) -> bool:
    """Arka planda render alan FFmpeg sürecini anında sonlandırır."""
    proc = ACTIVE_RENDER_PROCESSES.pop(script_or_workflow_id, None)
    if proc:
        try:
            proc.kill()
            print(f"[Render Engine] {script_or_workflow_id} için çalışan FFmpeg süreci zorla sonlandırıldı.")
            return True
        except Exception as e:
            print(f"[Render Engine] Süreç sonlandırılamadı: {e}")
    return False


async def assemble_smart_video(
    script_id: str,
    scenes: list[dict[str, Any]],
    usable_assets: list[dict[str, Any]],
    voice_filename: str | None = None,
    burn_subtitles: bool = True,
    transition_style: str = "fade",
    enable_ken_burns: bool = True
) -> dict[str, Any]:
    """
    Profesyonel Modüler Video Montaj Motoru:
    1. Timeline oluşturulması
    2. Sahnelerin dikey formatta işlenmesi
    3. Geçiş efektleri ile birleştirme
    4. Speech-aware ducking ile ses miksajı
    5. TikTok safe-zone altyazı yakma
    6. Render QA doğrulama
    """
    ffmpeg = get_ffmpeg_bin()
    work_dir = PROJECTS / script_id
    work_dir.mkdir(parents=True, exist_ok=True)

    # 1. Ses Süresi Analizi
    total_voice_duration = 30.0
    voice_path = None
    if voice_filename:
        v_cand = VOICE / Path(voice_filename).name
        if v_cand.exists():
            voice_path = v_cand
            total_voice_duration = await get_audio_duration_seconds(voice_path)

    # 2. Timeline İnşası
    timeline = build_timeline_from_scenes(
        script_id=script_id,
        title=f"Project {script_id[:8]}",
        scenes=scenes,
        voice_filename=voice_filename,
        total_voice_duration=total_voice_duration
    )
    # Timeline JSON modelini projede sakla
    (work_dir / "timeline_project.json").write_text(timeline.to_json(), encoding="utf-8")

    # 3. Her Sahne Klibini Dikey 9:16 Olarak İşle
    clips: list[Path] = []
    scene_durations: list[float] = []

    for idx, clip in enumerate(timeline.clips):
        # Sahneye atanmış varlığı bul
        asset_info = None
        if clip.asset_stored_name:
            asset_info = next((a for a in usable_assets if a.get("stored_name") == clip.asset_stored_name), None)
        elif clip.asset_id:
            asset_info = next((a for a in usable_assets if a.get("id") == clip.asset_id), None)
        if not asset_info and usable_assets:
            asset_info = usable_assets[idx % len(usable_assets)]

        if not asset_info:
            continue

        src_path = ASSETS / asset_info["stored_name"]
        if not src_path.exists():
            continue

        out_clip = work_dir / f"scene_{idx:02d}.mp4"
        success = await process_scene_clip(
            ffmpeg_bin=ffmpeg,
            source_path=src_path,
            output_path=out_clip,
            duration=clip.duration,
            is_image=clip.is_image,
            enable_ken_burns=enable_ken_burns
        )
        if success:
            clips.append(out_clip)
            scene_durations.append(clip.duration)

    if not clips:
        raise RuntimeError("Sahneler için medya klipleri oluşturulamadı.")

    # 4. Geçiş Efektleri ile Birleştir (xfade)
    merged_visual = work_dir / "merged_visual.mp4"
    await render_merged_video_with_transitions(
        ffmpeg_bin=ffmpeg,
        clips=clips,
        scene_durations=scene_durations,
        output_video_path=merged_visual,
        transition_style=transition_style
    )

    # 5. Ses Miksajı (Speech-Aware Ducking)
    mixed_audio = None
    if voice_path and voice_path.exists():
        mixed_audio = work_dir / "mixed_audio.wav"
        # Varsayılan arka plan müziği varsa kullan
        bgm_cand = None
        bgm_files = list(BGM_DIR.glob("*.mp3")) + list(BGM_DIR.glob("*.wav"))
        if bgm_files:
            bgm_cand = bgm_files[0]

        await mix_audio_track(
            ffmpeg_bin=ffmpeg,
            voice_path=voice_path,
            bgm_path=bgm_cand,
            output_audio_path=mixed_audio,
            total_duration=total_voice_duration
        )

    # 6. Altyazı Hazırlığı (.SRT)
    srt_path = work_dir / "subtitles.srt"
    srt_content = generate_srt_content(scenes, scene_durations)
    srt_path.write_text(srt_content, encoding="utf-8")

    # 7. Final Render (Görsel + Mikslenmiş Ses + TikTok Safe-Zone Altyazı)
    out_final = EXPORTS / f"eski_usul_{script_id[:8]}.mp4"
    inputs = ["-i", str(merged_visual)]
    if mixed_audio and mixed_audio.exists():
        inputs.extend(["-i", str(mixed_audio)])

    vf_filters = []
    if burn_subtitles and srt_path.exists() and srt_path.stat().st_size > 0:
        vf_filters.append(build_subtitle_filter(srt_path, preset="bottom_safe"))

    cmd = [ffmpeg, "-y", *inputs]
    if vf_filters:
        cmd.extend(["-vf", ",".join(vf_filters)])

    cmd.extend([
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-pix_fmt", "yuv420p", "-r", "30",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest", str(out_final)
    ])

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    ACTIVE_RENDER_PROCESSES[script_id] = proc
    try:
        await proc.communicate()
    finally:
        ACTIVE_RENDER_PROCESSES.pop(script_id, None)

    # 8. Render QA Doğrulama (Teknik Denetim)
    qa_result = await validate_video_render(ffmpeg, out_final)
    if not qa_result.passed:
        print(f"[Render QA Uyarısı] {qa_result.errors}")

    return {
        "ok": qa_result.passed,
        "filename": out_final.name,
        "url": f"/api/exports/{out_final.name}",
        "clips_count": len(clips),
        "total_duration": qa_result.duration_sec or total_voice_duration,
        "has_voice": bool(voice_path),
        "has_subtitles": burn_subtitles,
        "safe_zone_applied": True,
        "transition_applied": len(clips) > 1,
        "qa": qa_result.to_dict(),
        "timeline_json": timeline.to_dict()
    }
