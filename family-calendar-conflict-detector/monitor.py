"""Self-hosted Family calendar conflict monitor with real auto-send.

Fetches events from the Google Calendar API, detects newly-created events that
overlap existing ones (all-day included), and SENDS an email alert via SMTP to
both family addresses. De-dupes with a local state file so nothing is sent
twice.

Commands:
    python3 monitor.py run         # check + send alerts for new conflicts
    python3 monitor.py run --dry-run   # print what would be sent, send nothing
    python3 monitor.py baseline    # mark ALL current overlaps as seen, send nothing
                                   # (run once before enabling cron to suppress the backlog)

Configuration comes from environment variables (see .env.example). Requires a
Google OAuth client (credentials.json) authorized once interactively to create
token.json; and an SMTP app password for sending.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

from conflict_detector import (
    parse_events, find_new_conflicts, all_conflicts, Conflict,
    ALERT_RECIPIENTS, FAMILY_CALENDAR_ID,
)
import emailer

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# --- config ---------------------------------------------------------------
CALENDAR_ID = os.environ.get("FAMILY_CALENDAR_ID", FAMILY_CALENDAR_ID)
LOOKAHEAD_DAYS = int(os.environ.get("LOOKAHEAD_DAYS", "90"))
WINDOW_MINUTES = int(os.environ.get("WINDOW_MINUTES", "90"))
RECIPIENTS = os.environ.get("ALERT_RECIPIENTS", ",".join(ALERT_RECIPIENTS)).split(",")
STATE_PATH = Path(os.environ.get("STATE_PATH", "state.json"))

SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")          # e.g. edeitrick@gmail.com
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")  # Gmail app password
SMTP_FROM = os.environ.get("SMTP_FROM", SMTP_USER)

# Google OAuth files
CREDENTIALS_FILE = os.environ.get("GOOGLE_CREDENTIALS_FILE", "credentials.json")
TOKEN_FILE = os.environ.get("GOOGLE_TOKEN_FILE", "token.json")
SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]


# --- state (de-dup) -------------------------------------------------------
def load_state() -> set[str]:
    if STATE_PATH.exists():
        return set(json.loads(STATE_PATH.read_text()).get("alerted", []))
    return set()


def save_state(keys: set[str]) -> None:
    STATE_PATH.write_text(json.dumps({"alerted": sorted(keys)}, indent=2))


def _key(c: Conflict) -> str:
    return "|".join(c.key())


# --- calendar fetch -------------------------------------------------------
def fetch_events(now: datetime) -> list[dict]:
    """Fetch raw events from the Google Calendar API for the lookahead window.

    If the EVENTS_FILE env var points at a saved `events.list` JSON dump, read
    from that instead of hitting the API (used for offline dry-runs/tests).
    """
    events_file = os.environ.get("EVENTS_FILE")
    if events_file:
        return json.loads(Path(events_file).read_text()).get("events", [])

    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    creds = None
    if Path(TOKEN_FILE).exists():
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)  # one-time interactive auth
        Path(TOKEN_FILE).write_text(creds.to_json())

    service = build("calendar", "v3", credentials=creds)
    time_min = now.isoformat()
    time_max = (now + timedelta(days=LOOKAHEAD_DAYS)).isoformat()
    events, page_token = [], None
    while True:
        resp = service.events().list(
            calendarId=CALENDAR_ID, timeMin=time_min, timeMax=time_max,
            singleEvents=True, maxResults=250, pageToken=page_token,
        ).execute()
        events.extend(resp.get("items", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return events


# --- commands -------------------------------------------------------------
def cmd_run(dry_run: bool) -> int:
    now = datetime.now(timezone.utc)
    events = parse_events(fetch_events(now))
    conflicts = find_new_conflicts(events, now, timedelta(minutes=WINDOW_MINUTES))

    seen = load_state()
    fresh = [c for c in conflicts if _key(c) not in seen]
    if not fresh:
        print("No new conflicts.")
        return 0

    for c in fresh:
        if dry_run:
            print(f"[dry-run] would send to {RECIPIENTS}:")
            print("  SUBJECT:", c.subject)
            print("  BODY:   ", c.body)
        else:
            msg = emailer.build_message(SMTP_FROM, RECIPIENTS, c.subject, c.body)
            emailer.send(msg, SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD)
            print("Sent:", c.subject)
        seen.add(_key(c))

    if not dry_run:
        save_state(seen)
    return 0


def cmd_baseline() -> int:
    """Mark every current overlap as already-alerted, without sending."""
    now = datetime.now(timezone.utc)
    events = parse_events(fetch_events(now))
    seen = load_state()
    for c in all_conflicts(events):
        seen.add(_key(c))
    save_state(seen)
    print(f"Baseline set: {len(seen)} existing overlaps marked as seen (no emails sent).")
    return 0


def main(argv: list[str]) -> int:
    cmd = argv[1] if len(argv) > 1 else "run"
    if cmd == "run":
        return cmd_run(dry_run="--dry-run" in argv)
    if cmd == "baseline":
        return cmd_baseline()
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
