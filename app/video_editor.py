"""
Eski Usul AI Studio — Video Editor Module (Facade)
Modüler video_engine alt paketine köprü sağlar.
"""
from app.video_engine.orchestrator import (
    assemble_smart_video,
    get_ffmpeg_bin,
    is_ffmpeg_available,
    get_audio_duration_seconds,
    ROOT,
    EXPORTS,
    VOICE,
    ASSETS,
    PROJECTS,
    BGM_DIR
)
from app.video_engine.timeline_builder import TimelineProject, build_timeline_from_scenes
from app.video_engine.render_validator import validate_video_render, RenderQAResult

__all__ = [
    "assemble_smart_video",
    "get_ffmpeg_bin",
    "is_ffmpeg_available",
    "get_audio_duration_seconds",
    "TimelineProject",
    "build_timeline_from_scenes",
    "validate_video_render",
    "RenderQAResult",
    "ROOT",
    "EXPORTS",
    "VOICE",
    "ASSETS",
    "PROJECTS",
    "BGM_DIR"
]
