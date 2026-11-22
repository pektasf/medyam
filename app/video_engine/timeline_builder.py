"""
Eski Usul AI Studio — Timeline Project Builder
Render motorundan bağımsız, saklanabilir ve düzenlenebilir JSON timeline proje modeli.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class TimelineClip:
    scene_index: int
    start_sec: float
    end_sec: float
    duration: float
    asset_id: str | None = None
    asset_filename: str | None = None
    asset_stored_name: str | None = None
    visual_prompt: str = ""
    is_image: bool = False
    transition_in: str = "none"
    transition_out: str = "fade"
    transition_duration: float = 0.4


@dataclass
class AudioTrack:
    track_type: str            # 'voiceover', 'bgm', 'sfx'
    filename: str
    volume: float = 1.0        # 0.0 - 1.0
    start_sec: float = 0.0
    duration: float = 0.0
    ducking_enabled: bool = False
    ducking_volume: float = 0.15


@dataclass
class SubtitleTrack:
    scene_index: int
    start_sec: float
    end_sec: float
    text: str
    preset: str = "bottom_safe"
    font_size: int = 24
    font_color: str = "#FFFF00"
    stroke_color: str = "#000000"
    stroke_width: int = 2
    x_percent: float = 50.0
    y_percent: float = 76.0


@dataclass
class TimelineProject:
    script_id: str
    title: str
    target_duration: float
    aspect_ratio: str = "9:16"
    width: int = 1080
    height: int = 1920
    fps: int = 30
    clips: list[TimelineClip] = field(default_factory=list)
    audio_tracks: list[AudioTrack] = field(default_factory=list)
    subtitle_tracks: list[SubtitleTrack] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TimelineProject:
        clips = [TimelineClip(**c) for c in data.get("clips", [])]
        audio_tracks = [AudioTrack(**a) for a in data.get("audio_tracks", [])]
        subtitle_tracks = [SubtitleTrack(**s) for s in data.get("subtitle_tracks", [])]
        return cls(
            script_id=data["script_id"],
            title=data.get("title", ""),
            target_duration=float(data.get("target_duration", 30.0)),
            aspect_ratio=data.get("aspect_ratio", "9:16"),
            width=int(data.get("width", 1080)),
            height=int(data.get("height", 1920)),
            fps=int(data.get("fps", 30)),
            clips=clips,
            audio_tracks=audio_tracks,
            subtitle_tracks=subtitle_tracks,
            metadata=data.get("metadata", {})
        )


def build_timeline_from_scenes(
    script_id: str,
    title: str,
    scenes: list[dict[str, Any]],
    voice_filename: str | None = None,
    total_voice_duration: float | None = None
) -> TimelineProject:
    """Senaryo sahnelerinden profesyonel timeline nesnesi türetir."""
    total_scenes = len(scenes) if scenes else 1
    total_dur = total_voice_duration if total_voice_duration and total_voice_duration > 3 else total_scenes * 4.0
    scene_dur = max(2.5, total_dur / total_scenes)

    clips: list[TimelineClip] = []
    subtitle_tracks: list[SubtitleTrack] = []
    current_time = 0.0

    for idx, sc in enumerate(scenes):
        end_time = current_time + scene_dur
        stored = sc.get("asset_stored_name")
        is_img = False
        if stored:
            is_img = any(stored.lower().endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".webp"])

        clip = TimelineClip(
            scene_index=idx,
            start_sec=round(current_time, 2),
            end_sec=round(end_time, 2),
            duration=round(scene_dur, 2),
            asset_id=sc.get("asset_id"),
            asset_filename=sc.get("asset_filename"),
            asset_stored_name=stored,
            visual_prompt=sc.get("visual") or sc.get("shot") or "",
            is_image=is_img,
            transition_in="none" if idx == 0 else "fade",
            transition_out="fade"
        )
        clips.append(clip)

        # Altyazı izi
        text = sc.get("on_screen_text") or sc.get("text") or ""
        typo = sc.get("typography") or {}
        sub = SubtitleTrack(
            scene_index=idx,
            start_sec=round(current_time, 2),
            end_sec=round(end_time, 2),
            text=text,
            preset=typo.get("preset", "bottom_safe"),
            font_size=typo.get("font_size", 24),
            font_color=typo.get("font_color", "#FFFF00"),
            stroke_color=typo.get("stroke_color", "#000000"),
            stroke_width=typo.get("stroke_width", 2),
            x_percent=float(typo.get("x_percent", 50.0)),
            y_percent=float(typo.get("y_percent", 76.0))
        )
        subtitle_tracks.append(sub)
        current_time = end_time

    audio_tracks: list[AudioTrack] = []
    if voice_filename:
        audio_tracks.append(
            AudioTrack(
                track_type="voiceover",
                filename=voice_filename,
                volume=1.0,
                start_sec=0.0,
                duration=round(total_dur, 2)
            )
        )

    return TimelineProject(
        script_id=script_id,
        title=title,
        target_duration=round(current_time, 2),
        clips=clips,
        audio_tracks=audio_tracks,
        subtitle_tracks=subtitle_tracks
    )
