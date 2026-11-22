"""
Eski Usul AI Studio — Render Validator & Video QA
Üretilen video dosyasını teknik parametrelere (stream, codec, çözünürlük, süre) göre denetler.
"""
from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any


@dataclass
class RenderQAResult:
    passed: bool
    file_exists: bool
    file_size_bytes: int
    has_video_stream: bool
    has_audio_stream: bool
    video_codec: str
    audio_codec: str
    width: int
    height: int
    fps: float
    duration_sec: float
    is_corrupt: bool
    errors: list[str]
    warnings: list[str]

    @property
    def resolution(self) -> str:
        return f"{self.width}x{self.height}"

    @property
    def corruption_detected(self) -> bool:
        return self.is_corrupt

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["resolution"] = self.resolution
        d["corruption_detected"] = self.corruption_detected
        return d


async def validate_video_render(ffmpeg_bin: str, video_path: Path) -> RenderQAResult:
    """
    FFmpeg probe ile video dosyasının teknik bütünlüğünü analiz eder.
    Bozuk dosya, eksik stream veya yanlış çözünürlükleri tespit eder.
    """
    errors: list[str] = []
    warnings: list[str] = []

    if not video_path.exists():
        return RenderQAResult(
            passed=False,
            file_exists=False,
            file_size_bytes=0,
            has_video_stream=False,
            has_audio_stream=False,
            video_codec="none",
            audio_codec="none",
            width=0,
            height=0,
            fps=0.0,
            duration_sec=0.0,
            is_corrupt=True,
            errors=["Video dosyası diskte bulunamadı."],
            warnings=[]
        )

    size = video_path.stat().st_size
    if size < 10000:
        errors.append(f"Video dosya boyutu çok küçük ({size} byte).")

    # FFmpeg probe komutu
    proc = await asyncio.create_subprocess_exec(
        ffmpeg_bin, "-i", str(video_path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    _, stderr_bytes = await proc.communicate()
    output = stderr_bytes.decode("utf-8", errors="ignore")

    # 1. Süre analizi
    dur_match = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", output)
    dur = 0.0
    if dur_match:
        h, m, s = dur_match.groups()
        dur = int(h) * 3600 + int(m) * 60 + float(s)
    else:
        errors.append("Video süresi okunamadı veya dosya bozuk.")

    # 2. Video Stream kontrolü
    has_v = False
    v_codec = "unknown"
    width, height = 0, 0
    fps = 0.0

    v_stream_match = re.search(r"Stream #\d+:\d+.*Video:\s*([a-zA-Z0-9_\-]+)", output)
    if v_stream_match:
        has_v = True
        v_codec = v_stream_match.group(1).lower()

    res_match = re.search(r"(\d{3,4})x(\d{3,4})", output)
    if res_match:
        width = int(res_match.group(1))
        height = int(res_match.group(2))

    fps_match = re.search(r"(\d+(?:\.\d+)?)\s*fps", output)
    if fps_match:
        fps = float(fps_match.group(1))

    if not has_v:
        errors.append("Video akışı (video stream) bulunamadı.")
    elif width != 1080 or height != 1920:
        warnings.append(f"Dikey 9:16 çözünürlük yerine {width}x{height} tespit edildi.")

    # 3. Audio Stream kontrolü
    has_a = False
    a_codec = "none"
    a_stream_match = re.search(r"Stream #\d+:\d+.*Audio:\s*([a-zA-Z0-9_\-]+)", output)
    if a_stream_match:
        has_a = True
        a_codec = a_stream_match.group(1).lower()
    else:
        warnings.append("Ses akışı (audio stream) bulunamadı.")

    is_corrupt = "moov atom not found" in output or "Invalid data found" in output
    if is_corrupt:
        errors.append("Video container bozuk veya moov atom eksik.")

    passed = len(errors) == 0

    return RenderQAResult(
        passed=passed,
        file_exists=True,
        file_size_bytes=size,
        has_video_stream=has_v,
        has_audio_stream=has_a,
        video_codec=v_codec,
        audio_codec=a_codec,
        width=width,
        height=height,
        fps=fps,
        duration_sec=round(dur, 2),
        is_corrupt=is_corrupt,
        errors=errors,
        warnings=warnings
    )
