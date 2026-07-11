"""Clip orchestration: chaining, filter-retry ladder, budget enforcement.

Per scene: clip 1 is text-to-video conditioned on the character sheets
(re-anchors identity at every scene boundary); clips 2..N are image-to-video
seeded with the previous clip's last frame (motion continuity). Content-filter
rejections retry with progressively softer prompts. Every attempt is charged
to the budget BEFORE the call — filtered attempts cost real money too.
"""

import re
from pathlib import Path

import assemble
import config
import veo
from veo import FilteredError

# Progressive softening for filter retries: energetic verbs that occasionally
# trip filters get calmer synonyms at higher levels.
_CALM_SWAPS = [
    (r"\bbounce[sd]?\b", "sway gently"),
    (r"\bjump[sd]?\b", "step softly"),
    (r"\bcheer[sd]?\b", "smile happily"),
    (r"\bdance[sd]?\b", "move slowly"),
]


def soften(prompt: str, level: int) -> str:
    if level <= 0:
        return prompt
    softened = prompt
    if level >= 2:
        for pattern, repl in _CALM_SWAPS:
            softened = re.sub(pattern, repl, softened, flags=re.IGNORECASE)
    return softened + " Very calm, very gentle, slow minimal motion." * min(level, 2)


def make_scene(spec, series, workdir: Path, budget, backend: str = "veo") -> Path:
    """Generate and assemble one scene; returns the scene mp4 path."""
    clips_dir = workdir / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)
    client = veo.make_client() if backend == "veo" else None
    refs = veo.load_reference_images(series.all_sheets()) if backend == "veo" else None

    clip_paths = []
    last_frame = None
    for ci in range(len(spec.clip_prompts)):
        clip_path = clips_dir / f"scene{spec.index:02d}_clip{ci + 1}.mp4"
        _generate_with_ladder(
            spec, ci, clip_path, client=client, refs=refs if ci == 0 else None,
            first_frame=last_frame if ci > 0 else None, budget=budget, backend=backend,
        )
        clip_paths.append(clip_path)
        if backend == "veo" and ci < len(spec.clip_prompts) - 1:
            last_frame = clips_dir / f"scene{spec.index:02d}_clip{ci + 1}_last.png"
            assemble.extract_last_frame(clip_path, last_frame)

    scene_path = workdir / "scenes" / f"scene{spec.index:02d}.mp4"
    scene_path.parent.mkdir(parents=True, exist_ok=True)
    assemble.assemble_scene(clip_paths, scene_path, duration_s=spec.duration_s)
    return scene_path


def _generate_with_ladder(spec, ci: int, out_path: Path, *, client, refs,
                          first_frame, budget, backend: str) -> None:
    prompt = spec.clip_prompts[ci]
    last_error = None
    for attempt in range(config.MAX_CLIP_ATTEMPTS):
        attempt_prompt = soften(prompt, attempt)
        budget.charge(
            config.CLIP_SECONDS, backend,
            note=f"scene{spec.index} clip{ci + 1} attempt{attempt + 1}",
        )
        try:
            if backend == "veo":
                veo.generate_clip(
                    client, attempt_prompt, spec.negative, out_path,
                    duration_s=config.CLIP_SECONDS,
                    reference_images=refs, first_frame=first_frame,
                )
            else:
                import seedance

                seedance.generate_clip(
                    attempt_prompt, spec.negative, out_path,
                    duration_s=config.CLIP_SECONDS,
                )
            return
        except FilteredError as exc:
            last_error = exc
            print(
                f"  scene{spec.index} clip{ci + 1} filtered "
                f"(attempt {attempt + 1}/{config.MAX_CLIP_ATTEMPTS}); softening",
                flush=True,
            )
    raise RuntimeError(
        f"scene{spec.index} clip{ci + 1} exhausted filter retries: {last_error}"
    )
