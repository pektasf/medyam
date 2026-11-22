"""
Eski Usul AI Studio — Subtitle & Typography Renderer
TikTok Safe-Zone uyumlu dinamik altyazı ve on-screen metin yakma filtresi.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any


def is_arabic_text(text: str) -> bool:
    """Metnin Arapça karakterler içerip içermediğini tespit eder."""
    return bool(re.search(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]", text))


def shape_arabic_for_subtitles(text: str) -> str:
    """
    Arapça metinlerin FFmpeg/libass motorunda harflerinin doğru bağlanmasını
    ve RTL (sağdan sola) akışının kusursuz görüntülenmesini sağlar.
    """
    if not is_arabic_text(text):
        return text
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        reshaped = arabic_reshaper.reshape(text)
        return get_display(reshaped)
    except Exception:
        return text


def format_srt_timestamp(seconds: float) -> str:
    hrs = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int(round((seconds - int(seconds)) * 1000))
    return f"{hrs:02d}:{mins:02d}:{secs:02d},{millis:03d}"


def generate_srt_content(scenes: list[dict[str, Any]], scene_durations: list[float]) -> str:
    """Sahnelerden standart .SRT altyazı formatı üretir (Arapça RTL destekli)."""
    lines = []
    current_time = 0.0
    counter = 1

    for idx, sc in enumerate(scenes):
        dur = scene_durations[idx] if idx < len(scene_durations) else 3.5
        end_time = current_time + dur
        raw_text = sc.get("on_screen_text") or sc.get("text") or sc.get("narration") or ""
        clean_text = raw_text.strip().replace("\n", " ")

        if clean_text:
            # Arapça RTL shaping uygula
            display_text = shape_arabic_for_subtitles(clean_text)
            lines.append(str(counter))
            lines.append(f"{format_srt_timestamp(current_time)} --> {format_srt_timestamp(end_time)}")
            lines.append(display_text)
            lines.append("")
            counter += 1

        current_time = end_time

    return "\n".join(lines)


def get_safe_zone_ass_style(
    preset: str = "bottom_safe",
    font_name: str | None = None,
    font_size: int = 24,
    primary_color: str = "&H0000FFFF",  # ASS Yellow BGR
    outline_color: str = "&H00000000",  # ASS Black
    outline_width: int = 3,
    is_arabic: bool = False
) -> str:
    """
    TikTok Safe-Zone:
    Alt 220px (marginV=240), yan butonlar (marginR=60, marginL=40).
    Arapça için Windows native Segoe UI/Arial fontu ve optimize punto kullanılır.
    """
    margin_v = 240 if preset == "bottom_safe" else (960 if preset == "center" else 180)
    selected_font = font_name or ("Segoe UI" if is_arabic else "Inter")
    size = font_size + 4 if is_arabic else font_size
    return (
        f"FontName={selected_font},FontSize={size},PrimaryColour={primary_color},"
        f"OutlineColour={outline_color},BackColour=&H80000000,Bold=1,Outline={outline_width},"
        f"Shadow=1,Alignment=2,MarginL=40,MarginR=60,MarginV={margin_v}"
    )


def build_subtitle_filter(srt_path: Path, preset: str = "bottom_safe", is_arabic: bool = False) -> str:
    """
    Windows FFmpeg subtitles filtresi için güvenli kaçışlı yol hazırlar.
    """
    posix_path = srt_path.as_posix()
    clean_path = posix_path.replace(":", "\\:").replace("'", "\\'")
    style = get_safe_zone_ass_style(preset=preset, is_arabic=is_arabic)
    return f"subtitles='{clean_path}':force_style='{style}'"
