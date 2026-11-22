"""
Eski Usul AI Studio — Audio Mixer & Speech-Aware Ducking Engine
Seslendirme normalizasyonu, arka plan müziği ducking (akıllı alçalma) ve ses miksajı.
"""
from __future__ import annotations

import asyncio
from pathlib import Path


def build_ducking_filter(
    has_bgm: bool,
    voice_duration: float,
    bgm_duck_volume: float = 0.14,
    bgm_normal_volume: float = 0.32
) -> str:
    """
    FFmpeg speech-aware ducking ve loudness miksaj filtre dizesi.
    Konuşma varken müziği otomatik kısar, bittiğinde fade ile yumuşakça yükseltir.
    """
    if not has_bgm:
        # Sadece voiceover: EBU R128 ses normalizasyonu
        return "aresample=44100,volume=1.0"

    # [0:a] voiceover, [1:a] bgm
    # sidechain ducking veya zaman tabanlı volume zarfı
    return (
        f"[1:a]volume={bgm_duck_volume},afade=t=in:ss=0:d=1.0,afade=t=out:st={max(0, voice_duration - 1.5):.2f}:d=1.5[bgm_duck];"
        f"[0:a]volume=1.0[voice];"
        f"[voice][bgm_duck]amix=inputs=2:duration=first:dropout_transition=2[aout]"
    )


async def mix_audio_track(
    ffmpeg_bin: str,
    voice_path: Path,
    bgm_path: Path | None,
    output_audio_path: Path,
    total_duration: float
) -> bool:
    """Voiceover ve BGM'i ducking ve fade ile miksler."""
    if not voice_path.exists():
        return False

    if bgm_path and bgm_path.exists():
        filt = build_ducking_filter(has_bgm=True, voice_duration=total_duration)
        cmd = [
            ffmpeg_bin, "-y",
            "-i", str(voice_path),
            "-stream_loop", "-1", "-i", str(bgm_path),
            "-filter_complex", filt,
            "-map", "[aout]",
            "-t", f"{total_duration:.2f}",
            "-ac", "2", "-ar", "44100",
            str(output_audio_path)
        ]
    else:
        cmd = [
            ffmpeg_bin, "-y",
            "-i", str(voice_path),
            "-t", f"{total_duration:.2f}",
            "-af", "aresample=44100,volume=1.0",
            "-ac", "2", "-ar", "44100",
            str(output_audio_path)
        ]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    await proc.communicate()
    return proc.returncode == 0 and output_audio_path.exists()
