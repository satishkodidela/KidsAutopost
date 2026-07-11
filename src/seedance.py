"""Seedance via Kie.ai — availability fallback and cheap pipeline smoke tests.

Honest limitations vs the Veo path: no local reference images and no local
first-frame chaining (Kie wants public URLs), so clips are independent
generations — character consistency will be weak. That's fine for its two
jobs: end-to-end smoke tests at 480p pennies, and emergency fallback when Veo
is down. Quality renders go through veo.py.
"""

import json
import os
import re
import time

import requests

import config

KIE_BASE = "https://api.kie.ai/api/v1"
KIE_MODEL = config.env("KIE_SEEDANCE_MODEL", "bytedance/seedance-2-mini")
KIE_RESOLUTION = config.env("KIE_RESOLUTION", "480p")


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {os.environ['KIE_API_KEY']}",
        "Content-Type": "application/json",
    }


def get_credits() -> float:
    resp = requests.get(f"{KIE_BASE}/chat/credit", headers=_headers(), timeout=30)
    body = resp.json()
    if body.get("code") != 200 or body.get("data") is None:
        raise RuntimeError(f"Kie.ai credit check failed: {body}")
    return float(body["data"])


def generate_clip(prompt: str, negative: str, out_path, duration_s: int,
                  aspect: str = "9:16") -> None:
    task_input = {
        "prompt": f"{prompt} Avoid: {negative}.",
        "duration": duration_s,
        "resolution": KIE_RESOLUTION,
        "aspect_ratio": aspect,
        "generate_audio": False,
    }
    resp = requests.post(
        f"{KIE_BASE}/jobs/createTask",
        headers=_headers(),
        json={"model": KIE_MODEL, "input": task_input},
        timeout=60,
    )
    body = resp.json()
    task_id = (body.get("data") or {}).get("taskId") or body.get("taskId")
    if not resp.ok or not task_id:
        raise RuntimeError(f"Kie.ai createTask failed: {resp.status_code} {body}")
    url = _poll(task_id)
    with requests.get(url, stream=True, timeout=300) as dl:
        dl.raise_for_status()
        with open(out_path, "wb") as fh:
            for chunk in dl.iter_content(chunk_size=1 << 20):
                fh.write(chunk)


def _poll(task_id: str, timeout_s: int = 1200) -> str:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        resp = requests.get(
            f"{KIE_BASE}/jobs/recordInfo",
            headers=_headers(),
            params={"taskId": task_id},
            timeout=60,
        )
        body = resp.json()
        data = body.get("data") or {}
        state = (data.get("state") or "").lower()
        if state in ("success", "completed"):
            urls = re.findall(r"https://[^\"\\\s]+?\.mp4[^\"\\\s]*", json.dumps(data))
            if urls:
                return urls[0]
            raise RuntimeError(f"Kie.ai task succeeded but no mp4 URL found: {body}")
        if state in ("fail", "failed", "error"):
            raise RuntimeError(f"Kie.ai task failed: {body}")
        time.sleep(10)
    raise RuntimeError(f"Kie.ai task {task_id} timed out after {timeout_s}s")
