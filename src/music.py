"""Song generation via the ElevenLabs Music API.

A composition_plan pins each section to exactly SCENE_SECONDS so the song and
the scenes line up by construction (drift is ±1-2s in practice — visuals are
thematic, not lip-synced, so that's acceptable). A short instrumental tail
covers the branded outro card.
"""

import os

import config


def build_composition_plan(lyrics, music_style: str) -> dict:
    section_ms = config.SCENE_SECONDS * 1000
    sections = [
        {
            "section_name": s.name,
            "duration_ms": section_ms,
            "lines": s.lines,
            "positive_local_styles": ["bright", "playful"] if i == 0 else ["warm", "singalong"],
            "negative_local_styles": [],
        }
        for i, s in enumerate(lyrics.sections)
    ]
    sections.append(
        {
            "section_name": "outro",
            "duration_ms": config.OUTRO_SECONDS * 1000,
            "lines": [],
            "positive_local_styles": ["gentle instrumental fade"],
            "negative_local_styles": [],
        }
    )
    return {
        "positive_global_styles": [
            "children's song", "cheerful", "simple catchy melody",
            "warm female vocals", music_style,
        ],
        "negative_global_styles": [
            "aggressive", "distorted", "minor key", "heavy drums", "sad", "spooky",
        ],
        "sections": sections,
    }


def generate_song(plan: dict, out_path) -> None:
    from elevenlabs.client import ElevenLabs

    client = ElevenLabs(api_key=os.environ["ELEVENLABS_API_KEY"])
    audio = client.music.compose(composition_plan=plan)
    with open(out_path, "wb") as fh:
        if isinstance(audio, (bytes, bytearray)):
            fh.write(audio)
        else:
            for chunk in audio:
                fh.write(chunk)
