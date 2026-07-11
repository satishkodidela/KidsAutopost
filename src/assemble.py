"""ffmpeg assembly: normalize clips → scenes → final short with the song.

Every clip is normalized to the target canvas (fps 30, yuv420p, aac audio —
silent track injected if a backend returns video-only) so scene and final
concats are plain demuxer joins. The final mux keeps the clips' generated
ambience at low volume under the ElevenLabs song, uses an explicit -t (never
-shortest), and +faststart for social platforms.
"""

import re
import shutil
import subprocess
from pathlib import Path

import config

MAX_BYTES = 95 * 1024 * 1024  # stay under GitHub's 100MB hard limit


def _ffmpeg() -> str:
    found = shutil.which("ffmpeg")
    if found:
        return found
    import imageio_ffmpeg

    return imageio_ffmpeg.get_ffmpeg_exe()


def _run(args: list, capture: bool = False) -> str:
    proc = subprocess.run(
        [_ffmpeg(), "-hide_banner", "-y", *args],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    if proc.returncode != 0 and not capture:
        raise RuntimeError(f"ffmpeg failed: {' '.join(args)}\n{proc.stderr[-2000:]}")
    return proc.stderr


def _stream_info(path) -> str:
    """`ffmpeg -i` stderr — works without ffprobe (imageio wheel has no ffprobe)."""
    return _run(["-i", str(path)], capture=True)


def probe_duration(path) -> float:
    match = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", _stream_info(path))
    if not match:
        raise RuntimeError(f"Could not probe duration of {path}")
    h, m, s = match.groups()
    return int(h) * 3600 + int(m) * 60 + float(s)


def has_audio(path) -> bool:
    return "Audio:" in _stream_info(path)


def video_height(path) -> int:
    match = re.search(r"Video:.* (\d{3,4})x(\d{3,4})", _stream_info(path))
    return int(match.group(2)) if match else 0


def extract_last_frame(clip, out_png) -> None:
    _run(["-sseof", "-0.25", "-i", str(clip), "-frames:v", "1", "-update", "1", str(out_png)])


def normalize_clip(src, dst, aspect: str = "9:16") -> None:
    w, h = config.CANVAS[aspect]
    vf = (
        f"scale={w}:{h}:force_original_aspect_ratio=increase,"
        f"crop={w}:{h},fps={config.FPS},format=yuv420p"
    )
    args = ["-i", str(src)]
    if not has_audio(src):
        args += ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-shortest"]
    args += [
        "-vf", vf, "-c:v", "libx264", "-crf", "20", "-preset", "medium",
        "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2", str(dst),
    ]
    _run(args)


def _concat(paths: list, out, duration_s: float | None = None) -> None:
    list_file = Path(out).with_suffix(".txt")
    list_file.write_text("".join(f"file '{Path(p).resolve()}'\n" for p in paths))
    args = ["-f", "concat", "-safe", "0", "-i", str(list_file), "-c", "copy"]
    if duration_s:
        args += ["-t", f"{duration_s:.3f}"]
    _run(args + [str(out)])
    list_file.unlink()


def assemble_scene(clip_paths: list, out, duration_s: int, aspect: str = "9:16") -> None:
    normalized = []
    for i, clip in enumerate(clip_paths):
        norm = Path(out).parent / f"{Path(out).stem}_norm{i}.mp4"
        normalize_clip(clip, norm, aspect)
        normalized.append(norm)
    _concat(normalized, out, duration_s)
    for n in normalized:
        n.unlink()


def _find_font():
    candidates = [
        config.BRANDING_DIR / "font.ttf",
        Path("/System/Library/Fonts/Supplemental/Arial Rounded Bold.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ]
    return next((p for p in candidates if p.exists()), None)


def make_outro_clip(out_mp4, title: str, aspect: str = "9:16") -> None:
    """Soft branded end card (custom PNG in assets/branding wins if present)."""
    from PIL import Image, ImageDraw, ImageFont

    w, h = config.CANVAS[aspect]
    override = config.BRANDING_DIR / f"outro_{aspect.replace(':', 'x')}.png"
    png = Path(out_mp4).with_suffix(".png")
    if override.exists():
        png = override
    else:
        img = Image.new("RGB", (w, h), "#FFF3D6")
        draw = ImageDraw.Draw(img)
        font_path = _find_font()

        def font(size):
            return (ImageFont.truetype(str(font_path), size) if font_path
                    else ImageFont.load_default(size=size))

        draw.ellipse([w / 2 - 140, h * 0.22 - 140, w / 2 + 140, h * 0.22 + 140], fill="#FFD966")
        lines = ["Thanks for", "singing along!", "", title, "",
                 config.CHANNEL_HANDLE, "New songs every week"]
        sizes = [90, 90, 40, 56, 40, 48, 44]
        y = h * 0.38
        for line, size in zip(lines, sizes):
            if line:
                f = font(size)
                tw = draw.textlength(line, font=f)
                draw.text(((w - tw) / 2, y), line, fill="#5C4A32", font=f)
            y += size * 1.35
        img.save(png)

    _run([
        "-loop", "1", "-i", str(png),
        "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
        "-t", str(config.OUTRO_SECONDS),
        "-vf", f"scale={w}:{h},fps={config.FPS},format=yuv420p",
        "-c:v", "libx264", "-crf", "20", "-c:a", "aac", "-b:a", "128k",
        "-shortest", str(out_mp4),
    ])
    if png != override:
        png.unlink(missing_ok=True)


def assemble_final(scene_paths: list, song_path, out, title: str,
                   aspect: str = "9:16") -> float:
    """Concat scenes + outro, mux song over low ambience. Returns duration."""
    out = Path(out)
    total = len(scene_paths) * config.SCENE_SECONDS + config.OUTRO_SECONDS
    outro = out.parent / f"outro_{aspect.replace(':', 'x')}.mp4"
    make_outro_clip(outro, title, aspect)
    merged = out.parent / "merged_video.mp4"
    _concat([*scene_paths, outro], merged)

    fade_start = max(total - 1.5, 0)
    _run([
        "-i", str(merged), "-i", str(song_path),
        "-filter_complex",
        f"[0:a]volume=0.25[amb];[1:a]volume=1.0[m];"
        f"[amb][m]amix=inputs=2:duration=first:dropout_transition=2,"
        f"afade=t=out:st={fade_start:.2f}:d=1.5[a]",
        "-map", "0:v", "-map", "[a]",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        "-t", f"{total:.3f}", "-movflags", "+faststart", str(out),
    ])
    merged.unlink()
    outro.unlink()

    if out.stat().st_size > MAX_BYTES:
        smaller = out.with_name(out.stem + "_crf23.mp4")
        _run(["-i", str(out), "-c:v", "libx264", "-crf", "23", "-preset", "medium",
              "-c:a", "copy", "-movflags", "+faststart", str(smaller)])
        smaller.replace(out)
    return total
