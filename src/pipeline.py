"""Generate one short end-to-end: topic → lyrics → song → scenes → final mp4.

Writes everything into videos/<video_id>/ with a progressively-updated
meta.json; CI commits the staged folder and uploads to YouTube as private.
Exits non-zero (and stages nothing publishable) on any safety or QC failure.
"""

import datetime as dt
import json
import os
import sys
from dataclasses import asdict

import assemble
import bank
import budget as budget_mod
import characters
import config
import lyrics as lyrics_mod
import music
import qc
import storyboard
import veo
import videogen


def _recent_titles(limit: int = 25) -> list:
    titles = []
    if config.POSTED_PATH.exists():
        titles += [e.get("title", "") for e in json.loads(config.POSTED_PATH.read_text())]
    for meta_path in config.VIDEOS_DIR.glob("*/meta.json"):
        titles.append(json.loads(meta_path.read_text()).get("title", ""))
    return [t for t in titles if t][-limit:]


def _write_meta(workdir, meta: dict) -> None:
    (workdir / "meta.json").write_text(json.dumps(meta, indent=2, default=str) + "\n")


def _gh_output(video_id: str) -> None:
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as fh:
            fh.write(f"video_id={video_id}\n")


def _step_summary(meta: dict, report) -> None:
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    branch = os.environ.get("GITHUB_REF_NAME", "main")
    mp4_link = (
        f"https://github.com/{repo}/blob/{branch}/videos/{meta['video_id']}/final_9x16.mp4"
        if repo else "(local run)"
    )
    lines = [
        f"## {meta['title']}",
        f"- video_id: `{meta['video_id']}`",
        f"- preview: {mp4_link}",
        f"- cost this run: ${meta['cost_usd']:.2f}",
        f"- QC: {'PASS' if report.ok else 'FAIL'} — `{json.dumps(report.checks)}`",
        *([f"- issue: {i}" for i in report.issues]),
        "",
        "### Lyrics",
        *(f"**[{s['name']}]** " + " / ".join(s["lines"]) for s in meta["lyrics_sections"]),
    ]
    with open(path, "a") as fh:
        fh.write("\n".join(lines) + "\n")


def main() -> int:
    backend = config.VIDEO_BACKEND
    series = characters.load_series(config.SERIES_ID)
    topic = bank.select_topic(config.env("THEME"))

    today = dt.datetime.now(dt.timezone.utc).date().isoformat()
    video_id = f"{today}-{topic.theme}-{topic.slug}"
    workdir = config.VIDEOS_DIR / video_id
    workdir.mkdir(parents=True, exist_ok=True)
    print(f"video_id: {video_id} (backend: {backend})", flush=True)

    run_budget = budget_mod.Budget()
    n_clips = config.SCENES_PER_SHORT * config.CLIPS_PER_SCENE
    estimate = run_budget.precheck(n_clips, config.CLIP_SECONDS, backend)
    print(f"budget precheck OK — estimate ${estimate:.2f}", flush=True)

    client = veo.make_client()  # Gemini client, also used for lyrics
    song_lyrics = lyrics_mod.write_safe_lyrics(
        client, topic, series, _recent_titles(), n_scenes=config.SCENES_PER_SHORT
    )
    print(f"lyrics OK: {song_lyrics.title!r}", flush=True)

    meta = {
        "video_id": video_id,
        "created_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "topic": asdict(topic),
        "title": song_lyrics.title,
        "description": song_lyrics.description,
        "tags": song_lyrics.tags,
        "lyrics_sections": [asdict(s) for s in song_lyrics.sections],
        "series": series.id,
        "backend": backend,
        "format": config.env("FORMAT", "song"),
        "status": "generating",
    }
    _write_meta(workdir, meta)

    plan = music.build_composition_plan(song_lyrics, series.music_style)
    song_path = workdir / "song.mp3"
    music.generate_song(plan, song_path)
    meta["composition_plan"] = plan
    meta["song_duration_s"] = round(assemble.probe_duration(song_path), 2)
    print(f"song OK ({meta['song_duration_s']}s)", flush=True)

    specs = storyboard.plan_scenes(topic, song_lyrics, series)
    meta["scenes"] = [s.to_dict() for s in specs]
    _write_meta(workdir, meta)

    scene_paths = []
    for spec in specs:
        print(f"generating scene {spec.index + 1}/{len(specs)}...", flush=True)
        scene_paths.append(videogen.make_scene(spec, series, workdir, run_budget, backend))

    final_path = workdir / "final_9x16.mp4"
    expected = assemble.assemble_final(scene_paths, song_path, final_path, song_lyrics.title)
    meta["cost_usd"] = round(run_budget.run_spent, 2)

    report = qc.technical_qc(final_path, expected)
    meta["qc"] = {"ok": report.ok, "checks": report.checks, "issues": report.issues}
    meta["status"] = "staged" if report.ok else "qc_failed"
    _write_meta(workdir, meta)
    _step_summary(meta, report)

    if not report.ok:
        print(f"QC FAILED: {report.issues}", flush=True)
        return 1

    bank.consume_queue_file(topic)
    _gh_output(video_id)
    print(f"staged: {workdir} (${meta['cost_usd']:.2f})", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
