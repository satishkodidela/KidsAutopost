"""One-time local OAuth bootstrap for the channel's Google account.

Run on your machine (opens a browser), sign in as the CHANNEL OWNER, and copy
the printed refresh token into the repo secrets. Reminder: the OAuth consent
screen must be set to "In production" in Google Cloud Console, or this refresh
token silently expires after 7 days and CI uploads start failing.

Usage:
  YT_CLIENT_ID=... YT_CLIENT_SECRET=... python scripts/youtube_oauth_bootstrap.py
"""

import os

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
]

flow = InstalledAppFlow.from_client_config(
    {
        "installed": {
            "client_id": os.environ["YT_CLIENT_ID"],
            "client_secret": os.environ["YT_CLIENT_SECRET"],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    },
    SCOPES,
)
creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")

print("\nAdd these as GitHub Actions secrets:")
print(f"  YT_REFRESH_TOKEN = {creds.refresh_token}")
print("  (YT_CLIENT_ID and YT_CLIENT_SECRET you already have)")
