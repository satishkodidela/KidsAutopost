"""Veo 3.1 client (google-genai SDK): t2v with character reference images,
i2v from a first frame for intra-scene chaining.

Notes learned the hard way on the previous pipeline:
- Tier-1 Veo rate-limits back-to-back creates → 70s backoff, sequential.
- Safety-filtered outputs return filter reasons instead of videos.
- Vertical 9:16 has historically rendered 720p only; we request VEO_RESOLUTION
  (default 1080p) and drop to 720p once if the API rejects it.
"""

import os
import time

import config

VEO_MODEL = config.env("VEO_MODEL", "veo-3.1-fast-generate-preview")
_RESOLUTION = config.env("VEO_RESOLUTION", "1080p")


class FilteredError(RuntimeError):
    """Generation was blocked or stripped by content filters — retryable with
    a softer prompt, unlike infrastructure errors."""


def make_client():
    from google import genai

    return genai.Client(
        http_options={"api_version": "v1beta"},
        api_key=os.environ["GEMINI_API_KEY"],
    )


def load_reference_images(paths: list):
    from google.genai import types

    refs = []
    for path in paths:
        mime = "image/png" if str(path).lower().endswith(".png") else "image/jpeg"
        refs.append(
            types.VideoGenerationReferenceImage(
                image=types.Image(image_bytes=path.read_bytes(), mime_type=mime),
                reference_type="asset",
            )
        )
    return refs


def _first_frame_image(png_path):
    from google.genai import types

    return types.Image(image_bytes=png_path.read_bytes(), mime_type="image/png")


def generate_clip(client, prompt: str, negative: str, out_path, duration_s: int,
                  aspect: str = "9:16", reference_images=None, first_frame=None) -> None:
    """One clip. reference_images (scene openers) and first_frame (chained
    clips) are mutually exclusive modes in the API."""
    global _RESOLUTION
    from google.genai import types

    if reference_images and first_frame:
        raise ValueError("reference_images and first_frame are mutually exclusive")

    for resolution in (_RESOLUTION, "720p"):
        # negative_prompt config is rejected when combined with reference
        # images ("not supported in your use case") — the avoid-list already
        # rides in the prompt text, which is the approach proven in production.
        config_obj = types.GenerateVideosConfig(
            aspect_ratio=aspect,
            resolution=resolution,
            duration_seconds=duration_s,
            number_of_videos=1,
        )
        if reference_images:
            config_obj.reference_images = reference_images
        kwargs = {"model": VEO_MODEL, "prompt": prompt, "config": config_obj}
        if first_frame is not None:
            kwargs["image"] = _first_frame_image(first_frame)

        try:
            operation = _start_with_backoff(client, kwargs)
            _wait_and_save(client, operation, out_path)
            return
        except Exception as exc:
            msg = str(exc).lower()
            if resolution != "720p" and "resolution" in msg:
                print(f"  Veo rejected {resolution}, falling back to 720p", flush=True)
                _RESOLUTION = "720p"
                continue
            if "safety" in msg or "blocked" in msg or "filtered" in msg:
                raise FilteredError(str(exc)) from exc
            raise
    raise RuntimeError("unreachable")


def _start_with_backoff(client, kwargs, attempts: int = 5):
    for attempt in range(attempts):
        try:
            return client.models.generate_videos(**kwargs)
        except Exception as exc:
            rate_limited = "429" in str(exc) or "RESOURCE_EXHAUSTED" in str(exc)
            if not rate_limited or attempt == attempts - 1:
                raise
            print(f"  Veo rate limit; retrying in 70s ({attempt + 1}/{attempts - 1})", flush=True)
            time.sleep(70)


def _transient(exc: Exception) -> bool:
    msg = str(exc)
    return ("429" in msg or "RESOURCE_EXHAUSTED" in msg
            or "500" in msg or "503" in msg or "UNAVAILABLE" in msg)


def _wait_and_save(client, operation, path, timeout_s: int = 1800) -> None:
    """Poll to completion, tolerating rate-limited/transient polls — a 429 on a
    status check must never kill a render that's already paid for."""
    deadline = time.time() + timeout_s
    while not operation.done:
        if time.time() > deadline:
            raise RuntimeError(f"Veo generation timed out after {timeout_s}s")
        time.sleep(10)
        try:
            operation = client.operations.get(operation)
        except Exception as exc:
            if not _transient(exc):
                raise
            print("  Veo poll rate-limited; waiting 60s", flush=True)
            time.sleep(60)
    if operation.error:
        raise RuntimeError(f"Veo generation failed: {operation.error}")
    result = operation.result
    videos = (result.generated_videos or []) if result else []
    if not videos:
        reasons = getattr(result, "rai_media_filtered_reasons", None)
        raise FilteredError(f"Veo returned no video (filtered: {reasons})")
    video = videos[0].video
    for attempt in range(4):
        try:
            client.files.download(file=video)
            video.save(str(path))
            return
        except Exception as exc:
            if not _transient(exc) or attempt == 3:
                raise
            print("  Veo download rate-limited; waiting 60s", flush=True)
            time.sleep(60)
