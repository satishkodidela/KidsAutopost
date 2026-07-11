"""YouTube upload: private-first, kids-compliant metadata.

--stage uploads the staged video as PRIVATE (Phase 1 stops here; the operator
watches it in YouTube Studio). --make-public flips it after human approval
(Phase 2). selfDeclaredMadeForKids and containsSyntheticMedia are always set —
COPPA and YouTube's AI-disclosure policy are not optional for this channel.
"""

import argparse
import json
import os
import sys
from pathlib import Path

CATEGORY_BY_FORMAT = {"song": "24", "learning": "27"}  # Entertainment / Education


def _service():
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    creds = Credentials(
        token=None,
        refresh_token=os.environ["YT_REFRESH_TOKEN"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.environ["YT_CLIENT_ID"],
        client_secret=os.environ["YT_CLIENT_SECRET"],
        scopes=["https://www.googleapis.com/auth/youtube.upload",
                "https://www.googleapis.com/auth/youtube"],
    )
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def upload_private(stage_dir: Path) -> str:
    from googleapiclient.http import MediaFileUpload

    meta = json.loads((stage_dir / "meta.json").read_text())
    if meta.get("yt_video_id"):
        print(f"already uploaded: {meta['yt_url']}")
        return meta["yt_video_id"]

    body = {
        "snippet": {
            "title": meta["title"],
            "description": meta["description"],
            "tags": meta.get("tags", []),
            "categoryId": CATEGORY_BY_FORMAT.get(meta.get("format", "song"), "24"),
            "defaultLanguage": "en",
            "defaultAudioLanguage": "en",
        },
        "status": {
            "privacyStatus": "private",
            "selfDeclaredMadeForKids": True,
            "containsSyntheticMedia": True,
        },
    }
    media = MediaFileUpload(str(stage_dir / "final_9x16.mp4"), resumable=True)
    request = _service().videos().insert(part="snippet,status", body=body, media_body=media)
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"  upload {int(status.progress() * 100)}%", flush=True)

    video_id = response["id"]
    meta["yt_video_id"] = video_id
    meta["yt_url"] = f"https://youtube.com/watch?v={video_id}"
    meta["status"] = "uploaded_private"
    (stage_dir / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    print(f"uploaded PRIVATE: {meta['yt_url']}")

    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a") as fh:
            fh.write(f"\n**Private YouTube preview:** {meta['yt_url']}\n")
    return video_id


def make_public(stage_dir: Path) -> None:
    meta = json.loads((stage_dir / "meta.json").read_text())
    video_id = meta["yt_video_id"]
    _service().videos().update(
        part="status",
        body={"id": video_id, "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": True,
            "containsSyntheticMedia": True,
        }},
    ).execute()
    meta["status"] = "published"
    (stage_dir / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    print(f"now PUBLIC: {meta['yt_url']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", help="videos/<id> dir to upload as private")
    parser.add_argument("--make-public", dest="public", help="videos/<id> dir to flip public")
    args = parser.parse_args()
    if args.stage:
        upload_private(Path(args.stage))
    elif args.public:
        make_public(Path(args.public))
    else:
        parser.print_help()
        sys.exit(2)
