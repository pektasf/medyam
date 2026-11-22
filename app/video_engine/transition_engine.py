"""
Eski Usul AI Studio — Transition Engine
FFmpeg xfade ile sahneler arası sinematik geçiş efektleri oluşturur.
"""
from __future__ import annotations

import asyncio
from pathlib import Path


def build_xfade_filter_graph(
    clips: list[Path],
    scene_durations: list[float],
    transition_style: str = "fade",
    transition_duration: float = 0.4
) -> tuple[list[str], str, str]:
    """
    Birden fazla klip için xfade filtergraph zinciri kurar.
    Döner: (inputs, filter_str, final_stream_label)
    """
    inputs: list[str] = []
    for c in clips:
        inputs.extend(["-i", str(c)])

    filter_parts: list[str] = []
    current_offset = scene_durations[0] - transition_duration
    last_stream = "[0:v]"

    for i in range(1, len(clips)):
        next_stream = f"[{i}:v]"
        out_stream = f"[v{i}]" if i < len(clips) - 1 else "[vfinal]"
        filter_parts.append(
            f"{last_stream}{next_stream}xfade=transition={transition_style}:"
            f"duration={transition_duration}:offset={max(0.1, current_offset):.2f}{out_stream}"
        )
        last_stream = out_stream
        if i < len(scene_durations):
            current_offset += scene_durations[i] - transition_duration

    return inputs, ";".join(filter_parts), "[vfinal]"


async def render_merged_video_with_transitions(
    ffmpeg_bin: str,
    clips: list[Path],
    scene_durations: list[float],
    output_video_path: Path,
    transition_style: str = "fade"
) -> bool:
    """Klipleri xfade geçişleriyle birleştirir."""
    if len(clips) == 1:
        # Tek klip: kopyala veya hafif transcode
        cmd = [ffmpeg_bin, "-y", "-i", str(clips[0]), "-c", "copy", str(output_video_path)]
    elif len(clips) >= 2 and transition_style in ["fade", "dissolve", "wipeleft"]:
        inputs, filter_graph, out_stream = build_xfade_filter_graph(
            clips, scene_durations, transition_style=transition_style
        )
        cmd = [
            ffmpeg_bin, "-y",
            *inputs,
            "-filter_complex", filter_graph,
            "-map", out_stream,
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30",
            str(output_video_path)
        ]
    else:
        # Basit concat fallback
        concat_txt = output_video_path.parent / "concat.txt"
        concat_txt.write_text("\n".join([f"file '{c.name}'" for c in clips]), encoding="utf-8")
        cmd = [
            ffmpeg_bin, "-y", "-f", "concat", "-safe", "0", "-i", str(concat_txt),
            "-c", "copy", str(output_video_path)
        ]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    await proc.communicate()
    return proc.returncode == 0 and output_video_path.exists()
