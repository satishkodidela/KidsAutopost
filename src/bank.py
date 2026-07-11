"""Themed content bank + owner queue: what should today's video teach?

queue/*.json (oldest first) always wins; otherwise a random not-yet-posted
concept from bank/themes/*.json. posted.json is only written on publish, so a
failed run naturally retries the same concept.
"""

import json
import random
from dataclasses import dataclass, field
from pathlib import Path

import config


@dataclass
class Topic:
    theme: str
    slug: str
    title_hint: str
    concept: str
    focus: str
    props: list = field(default_factory=list)
    source: str = "bank"
    queue_file: str = ""  # set when source == "queue"; deleted after staging


def _posted_keys(posted_path: Path) -> set:
    if not posted_path.exists():
        return set()
    entries = json.loads(posted_path.read_text())
    return {f"{e['theme']}/{e['slug']}" for e in entries}


def _staged_keys(videos_dir: Path) -> set:
    keys = set()
    for meta_path in videos_dir.glob("*/meta.json"):
        meta = json.loads(meta_path.read_text())
        topic = meta.get("topic") or {}
        if topic.get("theme") and topic.get("slug"):
            keys.add(f"{topic['theme']}/{topic['slug']}")
    return keys


def _from_queue(queue_dir: Path) -> Topic | None:
    files = sorted(queue_dir.glob("*.json"))
    if not files:
        return None
    raw = json.loads(files[0].read_text())
    return Topic(
        theme=raw.get("theme", "custom"),
        slug=raw["slug"],
        title_hint=raw.get("title_hint", raw["slug"].replace("-", " ").title()),
        concept=raw["concept"],
        focus=raw.get("focus", ""),
        props=raw.get("props", []),
        source="queue",
        queue_file=str(files[0]),
    )


def select_topic(theme_override: str = "", rng: random.Random | None = None) -> Topic:
    rng = rng or random.Random()
    queued = _from_queue(config.QUEUE_DIR)
    if queued:
        return queued

    used = _posted_keys(config.POSTED_PATH) | _staged_keys(config.VIDEOS_DIR)
    candidates = []
    for theme_file in sorted(config.THEMES_DIR.glob("*.json")):
        bank = json.loads(theme_file.read_text())
        theme = bank["theme"]
        if theme_override and theme != theme_override:
            continue
        for c in bank["concepts"]:
            if f"{theme}/{c['slug']}" not in used:
                candidates.append((theme, c))
    if not candidates:
        raise RuntimeError(
            "No unposted concepts left"
            + (f" for theme {theme_override!r}" if theme_override else "")
            + " — add concepts to bank/themes/ or a topic to queue/."
        )
    theme, c = rng.choice(candidates)
    return Topic(
        theme=theme,
        slug=c["slug"],
        title_hint=c.get("title_hint", c["slug"].replace("-", " ").title()),
        concept=c["concept"],
        focus=c.get("focus", ""),
        props=c.get("props", []),
    )


def consume_queue_file(topic: Topic) -> None:
    """Delete the queue file once its video is staged (CI commits the deletion)."""
    if topic.source == "queue" and topic.queue_file:
        Path(topic.queue_file).unlink(missing_ok=True)
