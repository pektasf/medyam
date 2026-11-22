"""
Eski Usul AI Studio — Scene Processor
Her sahne klibini 9:16 (1080x1920) dikey formata dönüştürür, kırpar ve hazırlar.
"""
from __future__ import annotations

import asyncio
from pathlib import Path


async def process_scene_clip(
    ffmpeg_bin: str,
    source_path: Path,
    output_path: Path,
    duration: float,
    is_image: bool = False,
    enable_ken_burns: bool = True
) -> bool:
    """
    Tek bir sahne klibini 9:16 portre formatına ölçekler, ortalar ve renderlar.
    """
    if is_image:
        if enable_ken_burns:
            total_frames = int(duration * 30)
            vf = (
                f"zoompan=z='min(zoom+0.0018,1.18)':d={total_frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1080x1920:fps=30,"
                f"setsar=1,format=yuv420p"
            )
        else:
            vf = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,format=yuv420p"
        
        cmd = [
            ffmpeg_bin, "-y", "-loop", "1", "-i", str(source_path),
            "-t", f"{duration:.2f}", "-vf", vf, "-r", "30", "-an", str(output_path)
        ]
    else:
        # Yatay videodan dikey 9:16 odaklı merkez kırpma
        vf = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,format=yuv420p"
        cmd = [
            ffmpeg_bin, "-y", "-stream_loop", "-1", "-i", str(source_path),
            "-t", f"{duration:.2f}", "-vf", vf, "-r", "30", "-an", str(output_path)
        ]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    await proc.communicate()
    return proc.returncode == 0 and output_path.exists()
