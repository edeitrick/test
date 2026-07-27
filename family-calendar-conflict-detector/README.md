# Family Calendar Conflict Detector

Watches the shared **Family** Google Calendar and emails
`edeitrick@gmail.com` and `davidcpcu@gmail.com` whenever someone schedules a
new event **on top of an existing one** — including on top of all-day events.

**Alert email**

- **Subject:** `CONFLICT: <new event title> is attempting to overlap with existing event <existing event>`
- **Body:** `<person scheduling> is attempting to schedule <new event> on top of <existing event> on <date of conflict>.`

---

## How it runs (the live version)

The monitor runs as a scheduled **Claude Code Routine** (hourly) that already
has access to your Google Calendar and Gmail. On each run it:

1. Lists events on the Family calendar
   (`family04215781631001689506@group.calendar.google.com`) for the next ~90 days.
2. Finds events that were **created since the last check** (a newly scheduled
   event is the one "attempting to schedule").
3. For each new event, checks whether it overlaps any other event — all-day
   events included. Overlap uses half-open intervals `[start, end)`, so events
   that merely touch edges (back-to-back) do **not** count. Two instances of
   the same recurring series never conflict with each other.
4. The overlapping event that was created earlier is the "existing event";
   the newer one is the one being scheduled on top of it. The new event's
   creator is the person named in the email.
5. Before drafting, it searches your mail (sent + existing drafts) for the
   identical subject so the same conflict is never raised twice.
6. Prepares the alert to both addresses (see the sending note below).

### Sending: draft vs. auto-send

The connected Gmail (the Claude Gmail connector) can **create drafts but not
send** — no send capability is exposed. So the live Routine drops a ready-to-go
draft into your Gmail addressed to both recipients, and you hit **Send**.

For true hands-off **auto-send**, self-host the code (below) with either an
app-password + SMTP or the Gmail API `gmail.send` scope. The detection logic
and the exact subject/body are identical; only the final delivery step changes.

### Why it polls instead of firing instantly

Google Calendar cannot notify anyone at the *moment* an event is being typed
unless you host a public webhook endpoint tied to a Google Workspace domain
(Calendar "push notifications" / watch channels). For a personal Google
account the practical design is polling: the monitor checks on a schedule and
alerts right after a conflicting event is created. The scheduler's minimum
interval is hourly, so an alert can lag a new event by up to the poll interval.

### Design choices worth knowing

- **All-day events count as conflicts.** This is intentional — the point is to
  catch "you booked a dentist appointment during our camping trip." It also
  means busy all-day items (birthdays, trips, "work trip" blocks) will
  generate alerts for anything scheduled during them. If that gets noisy, the
  detector can be told to skip all-day events on one side — see
  `find_new_conflicts` in `conflict_detector.py`.
- **Different named people are not a conflict.** A double-booking only matters
  if the *same* person is in two places. If a new event names one family member
  (e.g. "David pick up cake" or "David to call Rob" — non-family names like Rob
  are ignored) and the overlapping event names *different* people (e.g.
  "Elise+Evie Family Reunion"), no alert fires. The family roster and nicknames
  live in `ROSTER` in `conflict_detector.py`.
  - This works when **both** titles name people. A name-less event like
    "Jellystone Camping" names nobody, so by default it is *not* auto-attributed
    (we'd rather send a spurious alert than hide a real one — Evie could be on
    that trip even though the title doesn't say so). Two ways to make the
    camping case suppress cleanly:
    1. **Name participants in the title** — "Jellystone Camping (Elise + Evie)".
       Safest and most precise.
    2. **Set `USE_CREATOR_FALLBACK=true`** — attributes a name-less event to
       whoever created it. Suppresses more (David's errands vs Elise's camping),
       but can hide a real conflict when a shared/family event was created by
       one person. Off by default.
- **Only newly-created events alert.** The monitor does not re-report the
  existing backlog of overlaps (there were ~110 at setup time); it reacts to
  fresh scheduling actions only. `all_conflicts()` exists if you ever want a
  one-time full digest.

---

## The code

- `conflict_detector.py` — pure, network-free detection logic: parse Calendar
  events, find new conflicts, and build the exact email subject/body.
- `emailer.py` — SMTP sender (the real auto-send the connector can't do).
- `monitor.py` — the self-hosted runner: fetch from the Calendar API, detect,
  de-dupe with a local state file, and send.
- `test_conflict_detector.py` — unit tests for the overlap rule, all-day
  handling, recurring-series exclusion, edge-touching, and email formatting.

```bash
python3 test_conflict_detector.py                       # run tests
EVENTS_FILE=events.json python3 monitor.py run --dry-run # offline dry-run, no API/SMTP
```

`events.json` is anything shaped like the Calendar API's `events.list`
response: `{"events": [ ... ]}`.

---

## Self-hosting with real auto-send

This is the fully hands-off version: it **sends** the email itself (SMTP),
rather than leaving a draft.

**1. Install deps**
```bash
pip install -r requirements.txt
cp .env.example .env      # then fill it in
```

**2. Gmail App Password (for sending)**
Turn on 2-Step Verification, then create an App Password at
<https://myaccount.google.com/apppasswords>. Put the 16-character value in
`SMTP_PASSWORD` and your address in `SMTP_USER` / `SMTP_FROM`.

**3. Google Calendar API (for reading)**
In Google Cloud Console: create a project, enable the **Google Calendar API**,
configure the OAuth consent screen, and create an **OAuth client ID → Desktop
app**. Download it as `credentials.json` next to `monitor.py`. The first run
opens a browser once to authorize read-only calendar access and writes
`token.json` (reused thereafter — copy it to a headless server if needed).

**4. Suppress the existing backlog, then go live**
```bash
python3 monitor.py baseline     # marks all ~110 current overlaps as seen; sends nothing
python3 monitor.py run          # from now on, sends only genuinely new conflicts
```

**5. Schedule it** (cron every 15 min, with a matching window buffer):
```cron
*/15 * * * * cd /path/to/family-calendar-conflict-detector && WINDOW_MINUTES=20 /usr/bin/python3 monitor.py run >> monitor.log 2>&1
```
Because reading uses the Calendar API directly (not the Claude scheduler), you
can poll as often as you like — every few minutes — so alerts are near-immediate
rather than hourly.

Secrets (`.env`, `credentials.json`, `token.json`) and `state.json` are
git-ignored — never commit them.
