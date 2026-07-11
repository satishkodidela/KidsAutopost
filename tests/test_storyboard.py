import config
import safety
import storyboard
from bank import Topic
from characters import Character, Series
from lyrics import Lyrics, Section


def fixtures():
    topic = Topic(theme="colors", slug="red-balloon", title_hint="The Big Red Balloon",
                  concept="Learning red", focus="the color red", props=["a red balloon"])
    lyr = Lyrics(
        title="The Big Red Balloon", description="d",
        sections=[
            Section("hook", ["Red balloon!", "Up it goes"], "Pip holds a big red balloon."),
            Section("verse", ["Red red red", "We love red"], "Lulu points at red apples."),
        ],
    )
    series = Series(
        id="test", name="Test", style_block="STYLEBLOCK.", music_style="ukulele",
        characters=[Character("Pip", "a baby panda"), Character("Lulu", "a baby bunny")],
    )
    return topic, lyr, series


def test_scene_count_and_clip_count():
    topic, lyr, series = fixtures()
    specs = storyboard.plan_scenes(topic, lyr, series)
    assert len(specs) == 2
    for spec in specs:
        assert len(spec.clip_prompts) == config.CLIPS_PER_SCENE
        assert spec.duration_s == config.SCENE_SECONDS


def test_prompts_carry_anchors():
    topic, lyr, series = fixtures()
    for spec in storyboard.plan_scenes(topic, lyr, series):
        for prompt in spec.clip_prompts:
            assert "STYLEBLOCK." in prompt                      # series style anchor
            assert safety.SAFETY_STYLE_BLOCK in prompt          # safety anchor
            assert "Avoid:" in prompt                           # negative list
            assert "Pip" in prompt and "Lulu" in prompt         # cast
            assert "[00:00-00:04]" in prompt                    # timestamped beats
        assert spec.negative == safety.NEGATIVE_BLOCK


def test_visual_theme_reaches_prompts():
    topic, lyr, series = fixtures()
    specs = storyboard.plan_scenes(topic, lyr, series)
    assert any("red balloon" in p.lower() for p in specs[0].clip_prompts)
    assert any("red apples" in p.lower() for p in specs[1].clip_prompts)


def test_scene_spec_serializes():
    topic, lyr, series = fixtures()
    spec = storyboard.plan_scenes(topic, lyr, series)[0]
    d = spec.to_dict()
    assert d["index"] == 0 and len(d["clip_prompts"]) == config.CLIPS_PER_SCENE


def test_reference_sheets_capped_and_balanced():
    from pathlib import Path
    _, _, series = fixtures()
    series.characters[0].sheets = [Path("pip-front.png"), Path("pip-3q.png")]
    series.characters[1].sheets = [Path("lulu-front.png"), Path("lulu-3q.png")]
    refs = series.reference_sheets()
    assert len(refs) == 3
    assert refs[0].name == "pip-front.png" and refs[1].name == "lulu-front.png"
