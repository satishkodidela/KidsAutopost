"""Generate candidate character sheets for a series (one-time, local).

Produces several candidates per character/view into
assets/characters/<series>/candidates/. YOU curate: pick the best, rename to
the sheet_files names in bank/series.json (e.g. pip-front.png), place them in
assets/characters/<series>/, and commit. The pipeline refuses to run until the
named sheets exist — curation is deliberately human.

Usage:
  GEMINI_API_KEY=... python scripts/make_character_sheets.py [series_id]
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import config  # noqa: E402
import json  # noqa: E402

IMAGE_MODEL = config.env("IMAGE_MODEL", "gemini-2.5-flash-image")
VIEWS = {
    "front": "full body, standing straight, facing the camera, neutral happy pose",
    "three-quarter": "full body, three-quarter view, mid-step cheerful pose",
}
VARIANTS = 3


def main() -> None:
    from google import genai

    series_id = sys.argv[1] if len(sys.argv) > 1 else config.SERIES_ID
    registry = json.loads(config.SERIES_PATH.read_text())
    series = next(s for s in registry["series"] if s["id"] == series_id)
    out_dir = config.CHARACTERS_DIR / series_id / "candidates"
    out_dir.mkdir(parents=True, exist_ok=True)

    client = genai.Client()
    for char in series["characters"]:
        for view, pose in VIEWS.items():
            prompt = (
                f"Character sheet reference image: {char['name']}, {char['description']}. "
                f"{pose}. {series['style_block']} Plain solid pale-grey background, "
                f"soft even studio lighting, no text, no watermark, whole character in frame."
            )
            for v in range(1, VARIANTS + 1):
                resp = client.models.generate_content(model=IMAGE_MODEL, contents=prompt)
                saved = False
                for part in resp.candidates[0].content.parts:
                    data = getattr(part, "inline_data", None)
                    if data and data.data:
                        path = out_dir / f"{char['name'].lower()}-{view}-v{v}.png"
                        path.write_bytes(data.data)
                        print(f"  {path}")
                        saved = True
                if not saved:
                    print(f"  (no image returned for {char['name']} {view} v{v})")

    print(f"\nCurate: pick the best per character/view, rename to the sheet_files in "
          f"bank/series.json, move them up to {config.CHARACTERS_DIR / series_id}/, commit.")


if __name__ == "__main__":
    main()
