"""
Eski Usul AI Studio — Quality Guard & Multi-Stage QA Engine (v0.5)
Script QA, Visual QA, Audio QA, Subtitle QA ve Render QA denetim sistemi.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any


@dataclass
class StageQAResult:
    stage_name: str
    passed: bool
    score: int                  # 0 - 100
    blocking_issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


@dataclass
class StudioQualityAudit:
    overall_passed: bool
    total_score: int
    stages: dict[str, StageQAResult]
    can_proceed_to_publish: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall_passed": self.overall_passed,
            "total_score": self.total_score,
            "stages": {k: asdict(v) for k, v in self.stages.items()},
            "can_proceed_to_publish": self.can_proceed_to_publish
        }


def audit_script_qa(script_data: dict[str, Any]) -> StageQAResult:
    """Senaryo metnini, hook gücünü ve tekrarları denetler."""
    blocking = []
    warnings = []
    score = 100

    hook = script_data.get("hook", "").strip()
    narration = script_data.get("narration", "").strip()
    scenes = script_data.get("scenes", [])

    if not hook or len(hook) < 6:
        blocking.append("Hook cümlesi eksik veya 6 karakterden kısa.")
        score -= 30

    if not narration and not scenes:
        blocking.append("Seslendirme metni ve sahneler boş.")
        score -= 40

    # Klişe / yasaklı dil kontrolü
    forbidden = ["carpe diem", "hayat çok kısa", "telefonunu bırak", "seize the moment"]
    for f in forbidden:
        if f in narration.lower():
            warnings.append(f"Klişe/didaktik ifade tespit edildi: '{f}'")
            score -= 10

    # Tekrar kontrolü
    words = [w.lower() for w in re.findall(r"\w+", narration)]
    if len(words) > 20:
        word_freq = {}
        for w in words:
            if len(w) > 4:
                word_freq[w] = word_freq.get(w, 0) + 1
        excessive = [w for w, count in word_freq.items() if count > 4]
        if excessive:
            warnings.append(f"Aşırı tekrarlanan kelimeler: {', '.join(excessive[:3])}")
            score -= 10

    return StageQAResult(
        stage_name="Script QA",
        passed=len(blocking) == 0,
        score=max(0, score),
        blocking_issues=blocking,
        warnings=warnings
    )


def audit_visual_qa(scenes: list[dict[str, Any]]) -> StageQAResult:
    """Görsel atamalarını, tekrarlanan videoları ve kadrajı denetler."""
    blocking = []
    warnings = []
    score = 100

    if not scenes:
        return StageQAResult(
            stage_name="Visual QA",
            passed=False,
            score=0,
            blocking_issues=["Senaryoda sahne bulunamadı."]
        )

    used_assets = []
    missing_assets = 0

    for idx, sc in enumerate(scenes):
        stored = sc.get("asset_stored_name")
        if not stored:
            missing_assets += 1
        else:
            if stored in used_assets:
                warnings.append(f"Sahne {idx + 1} tekrarlanan video kullanıyor: {stored}")
                score -= 15
            used_assets.append(stored)

    if missing_assets > 0:
        blocking.append(f"{missing_assets} sahneye video/medya atanmamış.")
        score -= missing_assets * 20

    return StageQAResult(
        stage_name="Visual QA",
        passed=len(blocking) == 0,
        score=max(0, score),
        blocking_issues=blocking,
        warnings=warnings
    )


def audit_audio_qa(voice_filename: str | None, voice_file_path: Path | None) -> StageQAResult:
    """Seslendirme dosyasının varlığını ve boyutunu denetler."""
    blocking = []
    warnings = []
    score = 100

    if not voice_filename:
        blocking.append("Seslendirme dosyası tanımlanmamış.")
        return StageQAResult(stage_name="Audio QA", passed=False, score=0, blocking_issues=blocking)

    if not voice_file_path or not voice_file_path.exists():
        blocking.append(f"Ses dosyası diskte bulunamadı: {voice_filename}")
        score -= 50
    else:
        size = voice_file_path.stat().st_size
        if size < 5000:
            blocking.append("Ses dosyası 5KB'dan küçük; seslendirme başarısız olmuş olabilir.")
            score -= 40

    return StageQAResult(
        stage_name="Audio QA",
        passed=len(blocking) == 0,
        score=max(0, score),
        blocking_issues=blocking,
        warnings=warnings
    )


def audit_subtitle_qa(scenes: list[dict[str, Any]], language: str = "tr") -> StageQAResult:
    """Altyazıların TikTok safe-zone ve uzunluk uyumunu denetler."""
    warnings = []
    blocking = []
    score = 100

    for idx, sc in enumerate(scenes):
        text = (sc.get("on_screen_text") or "").strip()
        words = text.split()
        if len(words) > 8:
            warnings.append(f"Sahne {idx + 1} ekranda çok fazla kelime içeriyor ({len(words)} kelime; önerilen max 7).")
            score -= 5

        # Arapça RTL tespiti
        if language == "ar":
            has_arabic = any("\u0600" <= ch <= "\u06FF" for ch in text)
            if not has_arabic and text:
                warnings.append(f"Sahne {idx + 1} Arapça içerik brief'inde Arapça harf içermiyor.")

    return StageQAResult(
        stage_name="Subtitle QA",
        passed=len(blocking) == 0,
        score=max(0, score),
        blocking_issues=blocking,
        warnings=warnings
    )


def perform_full_studio_qa(
    script_data: dict[str, Any],
    voice_file_path: Path | None = None,
    render_qa_dict: dict[str, Any] | None = None
) -> StudioQualityAudit:
    """Tüm aşamaları birleştirerek stüdyo kalite karnesi üretir."""
    scenes = script_data.get("scenes", [])
    if isinstance(scenes, str):
        import json
        try:
            scenes = json.loads(scenes)
        except Exception:
            scenes = []

    script_qa = audit_script_qa(script_data)
    visual_qa = audit_visual_qa(scenes)
    audio_qa = audit_audio_qa(script_data.get("voice_filename"), voice_file_path)
    sub_qa = audit_subtitle_qa(scenes, language=script_data.get("language", "tr"))

    render_passed = True
    render_score = 100
    render_blocking = []
    render_warnings = []
    if render_qa_dict:
        render_passed = render_qa_dict.get("passed", False)
        render_blocking = render_qa_dict.get("errors", [])
        render_warnings = render_qa_dict.get("warnings", [])
        render_score = 100 if render_passed else 40

    render_stage = StageQAResult(
        stage_name="Render QA",
        passed=render_passed,
        score=render_score,
        blocking_issues=render_blocking,
        warnings=render_warnings
    )

    stages = {
        "script": script_qa,
        "visual": visual_qa,
        "audio": audio_qa,
        "subtitle": sub_qa,
        "render": render_stage
    }

    avg_score = int(sum(s.score for s in stages.values()) / len(stages))
    overall_passed = all(s.passed for s in stages.values()) and avg_score >= 70

    return StudioQualityAudit(
        overall_passed=overall_passed,
        total_score=avg_score,
        stages=stages,
        can_proceed_to_publish=overall_passed and render_passed
    )
