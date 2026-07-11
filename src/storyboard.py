"""Turn lyrics sections into per-clip generation prompts (SceneSpecs).

Deterministic on purpose: the creativity lives in the lyrics' visual_theme;
this module only assembles filmable, timestamped shot prompts around it, so it
is fully unit-testable and every prompt carries the same style/safety anchors.
"""

from dataclasses import asdict, dataclass, field

import config
import safety


@dataclass
class SceneSpec:
    index: int
    name: str
    duration_s: int
    lines: list
    clip_prompts: list
    negative: str

    def to_dict(self) -> dict:
        return asdict(self)


# One entry per clip in a scene: (shot focus, beat action template).
# {chars} = character line, {theme} = section visual_theme, {focus} = concept focus.
_SHOT_PLAN = [
    (
        "Wide establishing shot.",
        "[00:00-00:04] {chars_first} waves hello and smiles at the camera. "
        "[00:04-00:08] The friends look at {theme_lower}",
    ),
    (
        "Medium shot on the action.",
        "[00:00-00:04] {theme} "
        "[00:04-00:08] The characters clap and bounce gently in rhythm, delighted.",
    ),
    (
        "Playful closing shot.",
        "[00:00-00:04] The friends dance a simple gentle dance together. "
        "[00:04-00:08] They cheer softly and strike a happy pose, ready to sing again.",
    ),
]


def _clip_prompt(shot: str, beats: str, series, section, topic) -> str:
    theme = section.visual_theme.rstrip(".") + "."
    beats_filled = beats.format(
        chars_first=series.characters[0].name,
        theme=theme,
        theme_lower=theme[0].lower() + theme[1:],
    )
    focus_note = f" Make the learning subject unmistakably clear: {topic.focus}." if topic.focus else ""
    return (
        f"{shot} {beats_filled}{focus_note} "
        f"Characters (keep their exact appearance consistent): {series.character_line()} "
        f"{series.style_block} {safety.SAFETY_STYLE_BLOCK} "
        f"Avoid: {safety.NEGATIVE_BLOCK}."
    )


def plan_scenes(topic, lyrics, series) -> list:
    if config.SCENE_SECONDS % config.CLIP_SECONDS != 0:
        raise ValueError("SCENE_SECONDS must be a multiple of CLIP_SECONDS")
    if config.CLIPS_PER_SCENE != len(_SHOT_PLAN):
        raise ValueError(
            f"Scene math wants {config.CLIPS_PER_SCENE} clips/scene but the shot plan "
            f"defines {len(_SHOT_PLAN)} — adjust SCENE_SECONDS/CLIP_SECONDS or _SHOT_PLAN"
        )
    specs = []
    for i, section in enumerate(lyrics.sections):
        prompts = [
            _clip_prompt(shot, beats, series, section, topic) for shot, beats in _SHOT_PLAN
        ]
        specs.append(
            SceneSpec(
                index=i,
                name=section.name,
                duration_s=config.SCENE_SECONDS,
                lines=list(section.lines),
                clip_prompts=prompts,
                negative=safety.NEGATIVE_BLOCK,
            )
        )
    return specs
