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
- **Only newly-created events alert.** The monitor does not re-report the
  existing backlog of overlaps (there were ~110 at setup time); it reacts to
  fresh scheduling actions only. `all_conflicts()` exists if you ever want a
  one-time full digest.

---

## The code

- `conflict_detector.py` — pure, network-free detection logic: parse Calendar
  events, find new conflicts, and build the exact email subject/body. Reusable
  from any runner.
- `test_conflict_detector.py` — unit tests for the overlap rule, all-day
  handling, recurring-series exclusion, edge-touching, and email formatting.

```bash
python3 test_conflict_detector.py          # run tests
python3 conflict_detector.py events.json 90 # dry-run against a saved events dump (window = 90 min)
```

`events.json` is anything shaped like the Calendar API's `events.list`
response: `{"events": [ ... ]}`.

---

## Self-hosting it yourself (optional)

If you'd rather run this as your own service instead of the Claude Routine,
wire `conflict_detector.py` to the Google APIs:

1. Create a Google Cloud project, enable the **Google Calendar API** and
   **Gmail API**, and make OAuth credentials (or a service account with
   domain-wide delegation / calendar sharing).
2. Fetch events with `events.list` on the Family calendar and feed the raw
   list into `parse_events()`.
3. Call `find_new_conflicts(events, now, window)` where `window` matches your
   cron cadence (plus a small buffer so nothing slips between runs).
4. For each returned `Conflict`, de-dupe (query Sent mail for `conflict.subject`,
   or keep a small local store of `conflict.key()`), then send `conflict.subject`
   / `conflict.body` to `ALERT_RECIPIENTS` via the Gmail API or SMTP.
5. Run it on any scheduler (cron, systemd timer, Lambda + EventBridge, GitHub
   Actions `schedule`).
