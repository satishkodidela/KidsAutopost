"""Original song lyrics + metadata via Gemini.

One section per scene; section timing is enforced later by the ElevenLabs
composition plan, so the writer only has to keep lines short and repetitive.
Originality pressure comes from feeding recent titles back into the prompt.
"""

import json
from dataclasses import dataclass, field

import config
import safety


@dataclass
class Section:
    name: str
    lines: list
    visual_theme: str


@dataclass
class Lyrics:
    title: str
    description: str
    tags: list = field(default_factory=list)
    sections: list = field(default_factory=list)


_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "description": {"type": "string"},
        "tags": {"type": "array", "items": {"type": "string"}},
        "sections": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "lines": {"type": "array", "items": {"type": "string"}},
                    "visual_theme": {"type": "string"},
                },
                "required": ["name", "lines", "visual_theme"],
            },
        },
    },
    "required": ["title", "description", "tags", "sections"],
}


def _parse(raw: dict) -> Lyrics:
    return Lyrics(
        title=raw["title"],
        description=raw["description"],
        tags=[t.lstrip("#") for t in raw.get("tags", [])][:12],
        sections=[Section(s["name"], s["lines"], s["visual_theme"]) for s in raw["sections"]],
    )


def write_lyrics(client, topic, series, recent_titles: list, n_scenes: int,
                 rewrite_feedback: str = "") -> Lyrics:
    prompt = (
        f"You write original songs for a preschool animation channel (ages 1-4). "
        f"The recurring characters are: {series.character_line()}\n"
        f"Today's video: {topic.concept} (theme: {topic.theme}, focus: {topic.focus or topic.slug}). "
        f"Working title idea: {topic.title_hint!r}. Props available: {', '.join(topic.props) or 'your choice'}.\n"
        f"Write exactly {n_scenes} sections; each will be sung over ~{config.SCENE_SECONDS}s "
        f"of animation. Section 1 must open with a catchy hook. Each section: 2-4 very short "
        f"lines, and a one-sentence visual_theme describing what the characters do on screen "
        f"(concrete, filmable in one location, uses the props).\n"
        f"{safety.LYRICS_RULES}\n"
        f"Must be ORIGINAL — do not paraphrase or echo these recent songs: "
        f"{', '.join(recent_titles) or '(none yet)'}. Never borrow classic nursery-rhyme "
        f"melodies or lyrics (Wheels on the Bus, Baby Shark, etc.).\n"
        f"Also produce: an honest YouTube title (no clickbait, include the learning focus), "
        f"a 2-3 sentence description, and up to 12 tags."
        + (f"\nA previous draft was rejected: {rewrite_feedback} — fix this." if rewrite_feedback else "")
    )
    resp = client.models.generate_content(
        model=config.LYRICS_MODEL,
        contents=prompt,
        config={"response_mime_type": "application/json", "response_schema": _SCHEMA},
    )
    raw = resp.parsed if getattr(resp, "parsed", None) else json.loads(resp.text)
    if not isinstance(raw, dict):
        raw = json.loads(resp.text)
    lyrics = _parse(raw)
    if len(lyrics.sections) != n_scenes:
        raise RuntimeError(f"Writer returned {len(lyrics.sections)} sections, wanted {n_scenes}")
    return lyrics


def write_safe_lyrics(client, topic, series, recent_titles: list, n_scenes: int,
                      max_attempts: int = 3) -> Lyrics:
    """Write → lint → LLM-judge loop. Fails the run rather than soften the gate."""
    feedback = ""
    for attempt in range(1, max_attempts + 1):
        lyrics = write_lyrics(client, topic, series, recent_titles, n_scenes, feedback)
        result = safety.lint_lyrics(lyrics)
        if result.ok:
            result = safety.judge_lyrics(client, lyrics, config.LYRICS_MODEL)
        if result.ok:
            return lyrics
        feedback = "; ".join(result.issues)
        print(f"  lyrics attempt {attempt} rejected: {feedback}", flush=True)
    raise RuntimeError(f"Lyrics failed safety after {max_attempts} attempts: {feedback}")
