"""
Eski Usul AI Studio — TTS (Text-to-Speech) & Subtitle Service
Edge-TTS ile doğal seslendirme + Windows SAPI / Yerel Fallback Motoru
"""
from __future__ import annotations

import os
import uuid
import re
import asyncio
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VOICE_DIR = ROOT / "data" / "media" / "voice"
VOICE_DIR.mkdir(parents=True, exist_ok=True)

VOICE_MAP = {
    "tr": "tr-TR-AhmetNeural",
    "tr_female": "tr-TR-EmelNeural",
    "en": "en-US-ChristopherNeural",
    "ar": "ar-SA-HamedNeural"
}


def _generate_windows_sapi_fallback(text: str, dest_path: Path):
    """Windows dahili SAPI.SpVoice ile yerel WAV/MP3 üretir (İnternet gerektirmez)."""
    import subprocess
    # PowerShell SpeechSynthesizer kullanarak yerel ses üret
    ps_cmd = f"""
    Add-Type -AssemblyName System.Speech;
    $synth = New-Object System.Speech.Synthesis.SpeechSynthesizer;
    $synth.SetOutputToWaveFile('{str(dest_path)}');
    $synth.Speak('{text.replace("'", " ")}');
    $synth.Dispose();
    """
    subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], capture_output=True, text=True)


async def generate_speech(
    text: str,
    language: str = "tr",
    voice_name: str | None = None
) -> tuple[str, str]:
    """
    Metni doğal seslendirmeye dönüştürür.
    Önce Edge-TTS'i dener; internet/bağlantı hatası olursa Windows SAPI'ye düşer.
    """
    clean_text = text.replace("/", " ").replace("...", ", ").strip()
    if not clean_text:
        raise ValueError("Seslendirilecek metin boş olamaz.")

    selected_voice = voice_name or VOICE_MAP.get(language, VOICE_MAP["tr"])
    filename = f"tts_{uuid.uuid4().hex[:10]}.mp3"
    dest_path = VOICE_DIR / filename

    try:
        import edge_tts
        communicate = edge_tts.Communicate(clean_text, selected_voice, rate="-4%", pitch="-2Hz")
        await communicate.save(str(dest_path))
    except Exception as exc:
        print(f"Edge-TTS bağlantı hatası ({exc}), yerel ses motoru devreye alınıyor...")
        # Fallback: Windows SAPI WAV üretimi
        wav_filename = f"tts_{uuid.uuid4().hex[:10]}.wav"
        wav_dest = VOICE_DIR / wav_filename
        try:
            await asyncio.to_thread(_generate_windows_sapi_fallback, clean_text[:400], wav_dest)
            if wav_dest.exists() and wav_dest.stat().st_size > 0:
                return wav_filename, str(wav_dest.relative_to(ROOT))
        except Exception as e:
            print(f"SAPI fallback error: {e}")
            
        raise RuntimeError(f"Seslendirme oluşturulamadı: {exc}")

    return filename, str(dest_path.relative_to(ROOT))


def parse_time_range(time_str: str) -> tuple[float, float]:
    clean = re.sub(r"[^\d\-–\.]", "", time_str.replace("–", "-"))
    parts = clean.split("-")
    if len(parts) >= 2:
        try:
            return float(parts[0]), float(parts[1])
        except ValueError:
            pass
    return 0.0, 5.0


def format_srt_time(seconds: float) -> str:
    millis = int((seconds % 1) * 1000)
    total_sec = int(seconds)
    secs = total_sec % 60
    total_min = total_sec // 60
    mins = total_min % 60
    hours = total_min // 60
    return f"{hours:02d}:{mins:02d}:{secs:02d},{millis:03d}"


def generate_srt_subtitles(scenes: list[dict], output_path: Path) -> Path:
    lines = []
    current_time = 0.0
    
    for idx, sc in enumerate(scenes, 1):
        t_str = sc.get("time", "")
        start_sec, end_sec = parse_time_range(t_str)
        if end_sec <= start_sec:
            start_sec = current_time
            end_sec = current_time + 4.0
        current_time = end_sec
        
        text = sc.get("on_screen_text") or sc.get("text") or sc.get("visual") or ""
        text = text.strip()
        if not text:
            continue
            
        start_srt = format_srt_time(start_sec)
        end_srt = format_srt_time(end_sec)
        
        lines.append(f"{idx}\n{start_srt} --> {end_srt}\n{text}\n")

    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path
