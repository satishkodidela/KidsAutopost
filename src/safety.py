"""Kid-safety guardrails: prompt blocks injected everywhere + lyrics lint.

Safety is layered: these blocks go into every generation prompt, the lint
rejects lyrics before any money is spent, and (Phase 2) the video judge hard-
gates the rendered result. Nothing here is overridable from CI inputs.
"""

import re
from dataclasses import dataclass, field

# Appended to every video/image generation prompt.
SAFETY_STYLE_BLOCK = (
    "Soft, bright, G-rated preschool animation. Gentle slow movements, warm "
    "daylight, smiling friendly characters, calm and joyful mood throughout. "
    "Everything is safe, soft-edged, and comforting for a 2-year-old viewer."
)

# Negative prompt for backends that accept one; also appended textually as an
# avoid-list for backends that don't.
NEGATIVE_BLOCK = (
    "darkness, night, shadows, scary faces, sharp teeth, claws, weapons, fire, "
    "smoke, falling, crying, injury, chase, strangers, flashing lights, strobe, "
    "fast cuts, distorted faces, text, watermark"
)

# Given to the lyrics writer verbatim.
LYRICS_RULES = (
    "Rules: vocabulary a 2-4 year old knows; every line short and singable; "
    "lots of repetition; only happy, warm, encouraging feelings; no fear, no "
    "danger, no sadness, no conflict, nothing a toddler could imitate unsafely "
    "(no climbing high, running into roads, touching hot things); no brand "
    "names; no scary creatures."
)

# Word-boundary blocklist. Deliberately blunt: a false positive costs one
# lyrics rewrite, a false negative costs trust on a kids channel.
_BLOCKLIST = (
    "kill", "gun", "knife", "blood", "dead", "death", "die", "dies", "hurt",
    "monster", "ghost", "zombie", "demon", "devil", "witch", "scary", "scared",
    "fear", "afraid", "scream", "cry", "cries", "crying", "hate", "stupid",
    "dumb", "fight", "hit", "punch", "fire", "burn", "poison", "drown",
    "choke", "gross", "beer", "wine", "drunk", "cigarette", "drug",
)
_BLOCKLIST_RE = re.compile(r"\b(" + "|".join(_BLOCKLIST) + r")\b", re.IGNORECASE)

MAX_WORDS_PER_LINE = 9


@dataclass
class LintResult:
    ok: bool
    issues: list = field(default_factory=list)


def lint_text(text: str) -> list:
    """Return blocklist hits in a piece of text (empty list = clean)."""
    return sorted({m.lower() for m in _BLOCKLIST_RE.findall(text)})


def lint_lyrics(lyrics) -> LintResult:
    """Cheap deterministic gate run before the Gemini judge and before any
    generation spend. `lyrics` is a lyrics.Lyrics."""
    issues = []
    for hit in lint_text(lyrics.title + " " + lyrics.description):
        issues.append(f"blocklisted word in title/description: {hit!r}")
    for section in lyrics.sections:
        for hit in lint_text(" ".join(section.lines) + " " + section.visual_theme):
            issues.append(f"blocklisted word in section {section.name!r}: {hit!r}")
        if not 2 <= len(section.lines) <= 4:
            issues.append(f"section {section.name!r} has {len(section.lines)} lines (want 2-4)")
        for line in section.lines:
            if len(line.split()) > MAX_WORDS_PER_LINE:
                issues.append(f"line too long to sing in section {section.name!r}: {line!r}")
    return LintResult(ok=not issues, issues=issues)


def judge_lyrics(client, lyrics, model: str) -> LintResult:
    """LLM pass for what regexes can't catch (innuendo, unsafe-to-imitate
    actions, frightening scenarios told in soft words)."""
    body = "\n".join(
        f"[{s.name}] " + " / ".join(s.lines) + f" (visuals: {s.visual_theme})"
        for s in lyrics.sections
    )
    prompt = (
        "You review songs for a channel for babies and toddlers (ages 1-4). "
        "Reject anything not perfectly G-rated: fear, sadness, conflict, "
        "unsafe imitable actions, innuendo, or scary imagery — even mild. "
        f"Title: {lyrics.title}\n{body}\n"
        'Answer JSON: {"safe": bool, "issues": [str]}'
    )
    resp = client.models.generate_content(
        model=model,
        contents=prompt,
        config={
            "response_mime_type": "application/json",
            "response_schema": {
                "type": "object",
                "properties": {
                    "safe": {"type": "boolean"},
                    "issues": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["safe", "issues"],
            },
        },
    )
    verdict = resp.parsed if hasattr(resp, "parsed") else None
    if verdict is None:
        import json

        verdict = json.loads(resp.text)
    if isinstance(verdict, dict):
        return LintResult(ok=bool(verdict.get("safe")), issues=list(verdict.get("issues") or []))
    return LintResult(ok=bool(verdict.safe), issues=list(verdict.issues or []))
