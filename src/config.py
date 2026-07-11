"""Paths, env tunables, and shared constants for the KidsAutopost pipeline."""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BANK_DIR = ROOT / "bank"
THEMES_DIR = BANK_DIR / "themes"
QUEUE_DIR = ROOT / "queue"
VIDEOS_DIR = ROOT / "videos"
DATA_DIR = ROOT / "data"
ASSETS_DIR = ROOT / "assets"
CHARACTERS_DIR = ASSETS_DIR / "characters"
BRANDING_DIR = ASSETS_DIR / "branding"

POSTED_PATH = DATA_DIR / "posted.json"
COSTS_PATH = DATA_DIR / "costs.json"
SERIES_PATH = BANK_DIR / "series.json"


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, "").strip() or default


def env_int(name: str, default: int) -> int:
    raw = env(name)
    return int(raw) if raw else default


def env_float(name: str, default: float) -> float:
    raw = env(name)
    return float(raw) if raw else default


# Scene math: a scene is the atomic unit (24s = 3 x 8s clips). ElevenLabs song
# sections are generated at exactly SCENE_SECONDS so audio and scenes align by
# construction. A short = SCENES_PER_SHORT scenes + a branded outro card.
SCENE_SECONDS = env_int("SCENE_SECONDS", 24)
CLIP_SECONDS = env_int("CLIP_SECONDS", 8)
SCENES_PER_SHORT = env_int("SCENES_PER_SHORT", 2)
OUTRO_SECONDS = env_int("OUTRO_SECONDS", 4)
CLIPS_PER_SCENE = SCENE_SECONDS // CLIP_SECONDS

FPS = 30
CANVAS = {"9:16": (1080, 1920), "16:9": (1920, 1080)}

VIDEO_BACKEND = env("VIDEO_BACKEND", "veo")
SERIES_ID = env("SERIES_ID", "pip-and-lulu")
CHANNEL_HANDLE = env("CHANNEL_HANDLE", "")

MAX_CLIP_ATTEMPTS = env_int("MAX_CLIP_ATTEMPTS", 5)
MAX_SCENE_REGENS = env_int("MAX_SCENE_REGENS", 2)

LYRICS_MODEL = env("LYRICS_MODEL", "gemini-2.5-flash")
