"""
Eski Usul AI Studio — Pydantic Scene Schema & Validator
Master Implementation Directive 2.1 gereksinimlerini karşılayan tip güvenli sahne modeli.
"""
from __future__ import annotations

import uuid
from typing import Optional, Any, Literal
from pydantic import BaseModel, Field, field_validator


class SceneAssetMetadata(BaseModel):
    match_score: int = Field(default=85, ge=0, le=100)
    source_provider: str = Field(default="pexels")
    license_name: str = Field(default="Pexels / Commercial OK")
    aspect_ratio: str = Field(default="9:16")
    resolution: str = Field(default="1080x1920")
    duration: float = Field(default=5.0, ge=0.5)
    alternatives: list[dict[str, Any]] = Field(default_factory=list)


class StudioScene(BaseModel):
    scene_id: str = Field(default_factory=lambda: f"sc_{uuid.uuid4().hex[:8]}")
    narration_text: str = Field(default="", description="Sahne seslendirme metni")
    estimated_duration: float = Field(default=4.0, ge=0.5, le=60.0, description="Tahmini saniye süresi")
    visual_description: str = Field(default="", description="Görsel tarif veya arama anahtar kelimeleri")
    visual_source_type: Literal["stock_video", "stock_image", "local_asset", "ai_generated"] = "stock_video"
    selected_asset: Optional[dict[str, Any]] = Field(default=None, description="Seçilen medya dosyası")
    asset_metadata: Optional[SceneAssetMetadata] = Field(default=None, description="Medya kalite ve kaynak metadatası")
    subtitle_text: str = Field(default="", description="Ekranda görünecek safe-zone altyazısı")
    transition: Literal["fade", "dissolve", "wipeleft", "none"] = "fade"
    audio_requirements: dict[str, Any] = Field(default_factory=lambda: {"ducking": True, "bgm_volume": 0.14})
    production_status: Literal["draft", "curated", "rendered", "failed"] = "draft"

    @field_validator("narration_text", mode="before")
    def clean_narration(cls, v: Any) -> str:
        return str(v or "").strip()

    @field_validator("subtitle_text", mode="before")
    def default_subtitle(cls, v: Any, info) -> str:
        s = str(v or "").strip()
        if not s and "narration_text" in info.data:
            return info.data["narration_text"][:60]
        return s

    @classmethod
    def from_dict(cls, data: dict[str, Any], index: int = 0) -> StudioScene:
        """Eski usul sahne sözlüğünü tip güvenli StudioScene modeline dönüştürür."""
        # Süre parse
        time_str = data.get("time", "")
        est_dur = 4.0
        if "-" in time_str:
            try:
                parts = time_str.replace("s", "").split("-")
                est_dur = float(parts[1]) - float(parts[0])
            except Exception:
                est_dur = 4.0

        narration = data.get("narration") or data.get("text") or ""
        visual = data.get("visual") or data.get("shot") or ""
        on_screen = data.get("on_screen_text") or narration

        asset_dict = None
        if data.get("asset_stored_name") or data.get("asset_filename"):
            asset_dict = {
                "id": data.get("asset_id", f"ast_{index}"),
                "filename": data.get("asset_filename"),
                "stored_name": data.get("asset_stored_name"),
                "url": data.get("asset_url")
            }

        meta = None
        if data.get("match_score"):
            meta = SceneAssetMetadata(match_score=int(data["match_score"]))

        return cls(
            scene_id=data.get("scene_id") or f"sc_{index + 1}",
            narration_text=narration,
            estimated_duration=max(1.0, est_dur),
            visual_description=visual,
            visual_source_type="stock_video",
            selected_asset=asset_dict,
            asset_metadata=meta,
            subtitle_text=on_screen,
            transition="fade",
            production_status="curated" if asset_dict else "draft"
        )

    def to_dict(self) -> dict[str, Any]:
        """FFmpeg ve SQLite için geriye dönük uyumlu sözlük çıktısı."""
        res = {
            "scene_id": self.scene_id,
            "time": f"0-{int(self.estimated_duration)}s",
            "shot": self.visual_description,
            "visual": self.visual_description,
            "on_screen_text": self.subtitle_text,
            "narration": self.narration_text,
            "transition": self.transition,
            "production_status": self.production_status
        }
        if self.selected_asset:
            res["asset_id"] = self.selected_asset.get("id")
            res["asset_filename"] = self.selected_asset.get("filename")
            res["asset_stored_name"] = self.selected_asset.get("stored_name")
            res["asset_url"] = self.selected_asset.get("url")
        if self.asset_metadata:
            res["match_score"] = self.asset_metadata.match_score
        return res
