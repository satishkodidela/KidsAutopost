import json
import random

import pytest

import bank
import config


@pytest.fixture
def repo(tmp_path, monkeypatch):
    themes = tmp_path / "themes"
    themes.mkdir()
    (themes / "colors.json").write_text(json.dumps({
        "theme": "colors",
        "concepts": [
            {"slug": "red", "concept": "red things", "focus": "red"},
            {"slug": "blue", "concept": "blue things", "focus": "blue"},
        ],
    }))
    queue = tmp_path / "queue"
    queue.mkdir()
    videos = tmp_path / "videos"
    videos.mkdir()
    posted = tmp_path / "posted.json"
    monkeypatch.setattr(config, "THEMES_DIR", themes)
    monkeypatch.setattr(config, "QUEUE_DIR", queue)
    monkeypatch.setattr(config, "VIDEOS_DIR", videos)
    monkeypatch.setattr(config, "POSTED_PATH", posted)
    return tmp_path


def test_queue_wins(repo):
    (repo / "queue" / "001.json").write_text(json.dumps(
        {"slug": "special", "concept": "owner request"}))
    topic = bank.select_topic()
    assert topic.source == "queue" and topic.slug == "special"


def test_posted_deduped(repo):
    (repo / "posted.json").write_text(json.dumps([{"theme": "colors", "slug": "red"}]))
    picks = {bank.select_topic(rng=random.Random(i)).slug for i in range(10)}
    assert picks == {"blue"}


def test_staged_deduped(repo):
    stage = repo / "videos" / "2026-07-11-colors-red"
    stage.mkdir()
    (stage / "meta.json").write_text(json.dumps({"topic": {"theme": "colors", "slug": "red"}}))
    picks = {bank.select_topic(rng=random.Random(i)).slug for i in range(10)}
    assert picks == {"blue"}


def test_exhausted_bank_raises(repo):
    (repo / "posted.json").write_text(json.dumps(
        [{"theme": "colors", "slug": "red"}, {"theme": "colors", "slug": "blue"}]))
    with pytest.raises(RuntimeError, match="No unposted concepts"):
        bank.select_topic()


def test_consume_queue_file(repo):
    qfile = repo / "queue" / "001.json"
    qfile.write_text(json.dumps({"slug": "special", "concept": "owner request"}))
    topic = bank.select_topic()
    bank.consume_queue_file(topic)
    assert not qfile.exists()
