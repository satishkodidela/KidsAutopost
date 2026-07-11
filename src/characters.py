"""Series bible: the recurring cast and the single visual style anchor.

bank/series.json defines each series; assets/characters/<series>/ holds the
human-curated character sheet PNGs that condition every scene's first clip.
"""

import json
from dataclasses import dataclass, field

import config


@dataclass
class Character:
    name: str
    description: str
    sheets: list = field(default_factory=list)  # absolute Paths


@dataclass
class Series:
    id: str
    name: str
    style_block: str
    music_style: str
    characters: list = field(default_factory=list)

    def character_line(self) -> str:
        return " ".join(f"{c.name}: {c.description}." for c in self.characters)

    def all_sheets(self) -> list:
        return [p for c in self.characters for p in c.sheets]

    def reference_sheets(self, limit: int = 3) -> list:
        """Round-robin across characters (front views first) so every character
        stays represented — Veo rejects more than 3 reference images."""
        ordered = []
        for i in range(max((len(c.sheets) for c in self.characters), default=0)):
            ordered += [c.sheets[i] for c in self.characters if i < len(c.sheets)]
        return ordered[:limit]


def load_series(series_id: str) -> Series:
    registry = json.loads(config.SERIES_PATH.read_text())
    raw = next((s for s in registry["series"] if s["id"] == series_id), None)
    if raw is None:
        raise RuntimeError(f"Series {series_id!r} not found in {config.SERIES_PATH}")
    chars = []
    missing = []
    for c in raw["characters"]:
        sheets = []
        for fname in c.get("sheet_files", []):
            path = config.CHARACTERS_DIR / series_id / fname
            (sheets if path.exists() else missing).append(path)
        chars.append(Character(name=c["name"], description=c["description"], sheets=sheets))
    if missing:
        raise RuntimeError(
            "Missing character sheets (run scripts/make_character_sheets.py and "
            "curate the output): " + ", ".join(str(p) for p in missing)
        )
    return Series(
        id=raw["id"],
        name=raw["name"],
        style_block=raw["style_block"],
        music_style=raw["music_style"],
        characters=chars,
    )
