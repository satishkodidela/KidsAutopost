"""Quality control. Phase 1: technical checks (duration, resolution, audio,
black frames). Phase 2 adds the Gemini video judge with the kid-safety rubric.
"""

import re
from dataclasses import dataclass, field

import assemble
import config


@dataclass
class TechnicalReport:
    ok: bool
    checks: dict = field(default_factory=dict)
    issues: list = field(default_factory=list)


def technical_qc(final_mp4, expected_seconds: float, aspect: str = "9:16") -> TechnicalReport:
    checks, issues = {}, []

    duration = assemble.probe_duration(final_mp4)
    checks["duration_s"] = round(duration, 2)
    if abs(duration - expected_seconds) > 2.0:
        issues.append(f"duration {duration:.1f}s deviates from expected {expected_seconds}s")

    height = assemble.video_height(final_mp4)
    checks["height_px"] = height
    min_height = 1900 if aspect == "9:16" else 1000  # 1080x1920 vertical / 1920x1080 wide
    if height and height < min_height:
        # 720p vertical is a known Veo limitation — warn, don't fail (plan risk #1)
        checks["resolution_warning"] = f"height {height}px below target"

    checks["has_audio"] = assemble.has_audio(final_mp4)
    if not checks["has_audio"]:
        issues.append("final video has no audio track")

    black = _black_spans(final_mp4)
    checks["black_spans"] = black
    if black:
        issues.append(f"black frames detected: {black}")

    return TechnicalReport(ok=not issues, checks=checks, issues=issues)


def _black_spans(path) -> list:
    stderr = assemble._run(
        ["-i", str(path), "-vf", "blackdetect=d=0.4:pix_th=0.10", "-an", "-f", "null", "-"],
        capture=True,
    )
    return [
        f"{m.group(1)}s-{m.group(2)}s"
        for m in re.finditer(r"black_start:(\d+\.?\d*).*?black_end:(\d+\.?\d*)", stderr)
    ]
