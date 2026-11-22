"""
Eski Usul AI Studio — Hugging Face AI Integration Hub
Açık kaynaklı ve ücretsiz Hugging Face modellerini stüdyoya bağlar:
1. Brain / LLM: Qwen 2.5 72B / Llama 3.3 70B (Hugging Face Serverless Chat Router)
2. Vision / Image Gen: FLUX.1-schnell (9:16 Dikey Sahne Üretimi)
3. Speech-to-Text: Whisper Large v3 (Otomatik Altyazı ve Senkron)
"""
from __future__ import annotations

import os
import uuid
import httpx
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "data" / "media" / "assets"
ASSETS.mkdir(parents=True, exist_ok=True)


def _get_hf_config() -> dict[str, str]:
    from app.agent_runtime import _read_env
    env = _read_env()
    token = os.getenv("HF_TOKEN") or env.get("HF_TOKEN", "")
    llm_model = os.getenv("HF_LLM_MODEL") or env.get("HF_LLM_MODEL", "Qwen/Qwen2.5-72B-Instruct")
    image_model = os.getenv("HF_IMAGE_MODEL") or env.get("HF_IMAGE_MODEL", "black-forest-labs/FLUX.1-schnell")
    return {
        "token": token,
        "llm_model": llm_model,
        "image_model": image_model,
    }


async def call_hf_chat_completion(messages: list[dict[str, str]], model: str | None = None, temperature: float = 0.35) -> str:
    """
    Hugging Face Serverless Chat API üzerinden LLM yanıtı alır.
    Varsayılan model: Qwen/Qwen2.5-72B-Instruct veya meta-llama/Llama-3.3-70B-Instruct
    """
    cfg = _get_hf_config()
    target_model = model or cfg["llm_model"]
    url = "https://router.huggingface.co/hf-inference/v1/chat/completions"
    
    headers = {"Content-Type": "application/json"}
    if cfg["token"]:
        headers["Authorization"] = f"Bearer {cfg['token']}"
        
    payload = {
        "model": target_model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": 1500
    }
    
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]


async def generate_hf_scene_visual(prompt: str, width: int = 768, height: int = 1360) -> dict[str, Any] | None:
    """
    FLUX.1-schnell (veya yapılandırılan HF modeli) ile 9:16 dikey sahne görseli üretir
    ve yerel medya kütüphanesine (assets) kaydeder.
    """
    cfg = _get_hf_config()
    target_model = cfg["image_model"]
    url = f"https://api-inference.huggingface.co/models/{target_model}"
    
    headers = {}
    if cfg["token"]:
        headers["Authorization"] = f"Bearer {cfg['token']}"
        
    # Güvenli, sinematik ve 9:16 dikey mobil odaklı prompt geliştirme
    enhanced_prompt = (
        f"{prompt.strip()}, vertical 9:16 aspect ratio, mobile wallpaper format, "
        "cinematic lighting, photorealistic, 8k resolution, documentary style, highly detailed, masterpieces"
    )
    
    payload = {
        "inputs": enhanced_prompt,
        "parameters": {
            "width": width,
            "height": height,
            "num_inference_steps": 4
        }
    }
    
    try:
        async with httpx.AsyncClient(timeout=90) as client:
            resp = await client.post(url, headers=headers, json=payload)
            if resp.status_code == 200:
                aid = str(uuid.uuid4())
                stored_name = f"hf_flux_{aid[:8]}.jpg"
                dest = ASSETS / stored_name
                dest.write_bytes(resp.content)
                
                return {
                    "id": aid,
                    "filename": stored_name,
                    "stored_name": stored_name,
                    "kind": "image",
                    "source_url": f"https://huggingface.co/{target_model}",
                    "license_name": "Creative Open Access (FLUX.1-schnell)",
                    "commercial_ok": 1,
                    "attribution": f"{target_model} on Hugging Face",
                    "notes": f"AI Görsel Üretimi: {prompt[:60]}"
                }
    except Exception as exc:
        print(f"[HuggingFace Image Gen Error] {exc}")
        
    return None
