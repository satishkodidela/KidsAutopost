# KidsAutopost

Automated 3D-animated kids content (nursery-rhyme-style original songs and learning
videos for ages 1–4), generated with AI and published to YouTube, Instagram, and
Facebook. Kid safety is the top design constraint at every layer.

## How a short gets made

1. **Topic** — `bank/themes/*.json` concept not yet posted (or `queue/` owner request).
2. **Lyrics** — Gemini writes an original song (one section per scene) → deterministic
   safety lint → Gemini safety judge; up to 3 rewrites, then the run fails.
3. **Song** — ElevenLabs Music `composition_plan` pins every section to exactly 24s,
   so the song and the scenes line up by construction.
4. **Scenes** — each 24s scene = 3×8s Veo 3.1 clips: clip 1 is text-to-video conditioned
   on the committed character sheets (re-anchors the cast), clips 2–3 continue from the
   previous clip's last frame. Content-filter rejections retry with softer prompts.
   Every attempt is charged against hard per-run/per-month budget caps.
5. **Assembly** — ffmpeg: normalize → concat scenes + branded outro card → mux the song
   over low clip ambience.
6. **QC** — technical checks now (duration/resolution/audio/black-frames); Phase 2 adds
   a Gemini video judge with a non-overridable kid-safety gate.
7. **Publish** — YouTube upload as **private** (`selfDeclaredMadeForKids=true`,
   `containsSyntheticMedia=true`). Phase 2: human approval gate → public + IG/FB Reels.

## One-time setup

1. **Google Cloud**: create a project, enable YouTube Data API v3, create OAuth
   client (Desktop), set the consent screen to **In production** (testing-mode refresh
   tokens die after 7 days), and **submit the YouTube API compliance audit form
   immediately** — unaudited projects get every upload locked private.
2. **YouTube token**: `YT_CLIENT_ID=... YT_CLIENT_SECRET=... python scripts/youtube_oauth_bootstrap.py`
   signed in as the channel owner; save the printed refresh token as a secret.
3. **ElevenLabs**: paid plan (commercial music license) → `ELEVENLABS_API_KEY`.
4. **Character sheets**: `python scripts/make_character_sheets.py`, curate the
   candidates into `assets/characters/pip-and-lulu/` matching `bank/series.json`,
   commit. The pipeline refuses to run without them — curation is deliberately human.
5. **Secrets/vars**: copy `.env.example` values into Actions secrets and repo variables.
6. Repo must be **public** (IG/FB Phase 2 fetch the mp4 via raw.githubusercontent.com).

## Running

- CI: Actions → "Generate kids video" → Run workflow (choose theme/backend/budget).
- Local: `pip install -r requirements.txt`, export the env vars, `python src/pipeline.py`.
  Cheap smoke test: `VIDEO_BACKEND=seedance SCENES_PER_SHORT=1` (~pennies, low quality —
  Seedance is for smoke tests/fallback only, quality renders use Veo).
- Tests: `pytest tests/` (pure functions only, no API calls).

## Compliance notes (read once, they're load-bearing)

- Every video is marked **Made for Kids** (COPPA) — comments and personalized ads are
  disabled by YouTube; expect $1–3 RPM. Do not build the business case on ads.
- YouTube's inauthentic-content policy actively strikes mass-produced AI kids channels:
  modest cadence (3×/week), original songs, honest metadata, human review of every
  video, and the synthetic-media disclosure flag are all deliberate defenses.
- Never reuse classic nursery-rhyme melodies/lyrics — original songs only (Content ID
  + differentiation).

## Roadmap

- **Phase 1 (this)**: dispatch-only run → staged short → private YouTube.
- **Phase 2**: Gemini video judge + regen loop, `publish-approval` environment gate,
  Instagram + Facebook publishers, token refresh, 3×/week cron, more themes.
- **Phase 3**: long-form 16:9 re-renders of top scenes (medleys), metrics loop, thumbnails.
