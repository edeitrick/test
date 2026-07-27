"""Family calendar conflict detector.

Given a list of Google Calendar events (as returned by the Calendar API /
the Google Calendar connector's ``list_events``), find cases where a newly
created event overlaps an already-existing event -- including all-day
events -- and build the alert email that should be sent to the family.

The overlap rule intentionally treats all-day events as real conflicts,
because the whole point is to catch "you scheduled X on top of the day we're
already doing Y". Two instances of the *same* recurring series are never
considered a conflict with each other.

This module is pure logic with no network calls, so it can be unit-tested and
reused from any runner (the live Claude "Routine" monitor, an AWS Lambda, a
cron job, etc.). See README.md for how it is wired up.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta


# --------------------------------------------------------------------------
# Parsing
# --------------------------------------------------------------------------

@dataclass
class Event:
    id: str
    title: str
    start: datetime          # timezone-aware, UTC
    end: datetime            # timezone-aware, UTC (exclusive)
    all_day: bool
    created: datetime        # timezone-aware, UTC
    creator: str             # display name, falling back to email
    series: str | None       # recurringEventId, if any


def _parse_point(node: dict) -> tuple[datetime, bool]:
    """Parse a Calendar start/end node into (utc_datetime, is_all_day)."""
    if "dateTime" in node:
        raw = node["dateTime"].replace("Z", "+00:00")
        return datetime.fromisoformat(raw).astimezone(timezone.utc), False
    # All-day event: {"date": "2026-08-03"}. Google's `end.date` is exclusive.
    return datetime.fromisoformat(node["date"]).replace(tzinfo=timezone.utc), True


def parse_events(raw_events: list[dict]) -> list[Event]:
    """Normalize raw Calendar API events, skipping cancelled ones."""
    out: list[Event] = []
    for ev in raw_events:
        if ev.get("status") == "cancelled":
            continue
        start, all_day = _parse_point(ev["start"])
        end, _ = _parse_point(ev["end"])
        creator_node = ev.get("creator", {}) or {}
        out.append(Event(
            id=ev.get("id", ""),
            title=(ev.get("summary") or "(no title)").strip(),
            start=start,
            end=end,
            all_day=all_day,
            created=datetime.fromisoformat(ev["created"].replace("Z", "+00:00")),
            creator=creator_node.get("displayName") or creator_node.get("email") or "Someone",
            series=ev.get("recurringEventId"),
        ))
    return out


# --------------------------------------------------------------------------
# Conflict detection
# --------------------------------------------------------------------------

def _overlaps(a: Event, b: Event) -> bool:
    # Half-open intervals: [start, end). Touching edges do not overlap.
    return a.start < b.end and b.start < a.end


@dataclass
class Conflict:
    new_event: Event         # the just-scheduled event ("attempting to schedule")
    existing_event: Event    # the event it lands on top of
    date: datetime           # the day the overlap begins (for the email)

    @property
    def subject(self) -> str:
        return (f"CONFLICT: {self.new_event.title} is attempting to overlap "
                f"with existing event {self.existing_event.title}")

    @property
    def body(self) -> str:
        day = self.date.strftime("%A, %B %-d, %Y")
        return (f"{self.new_event.creator} is attempting to schedule "
                f"{self.new_event.title} on top of {self.existing_event.title} "
                f"on {day}.")

    def key(self) -> tuple[str, str]:
        """Stable identity for de-duplication."""
        return (self.new_event.id, self.existing_event.id)


def find_new_conflicts(events: list[Event], now: datetime,
                       window: timedelta) -> list[Conflict]:
    """Return conflicts caused by events created within ``window`` of ``now``.

    An event is a "new scheduling action" if its ``created`` timestamp is
    within the polling window. We only alert on those, so the monitor reacts
    to fresh double-bookings instead of re-reporting the entire backlog.
    The event it overlaps (``existing_event``) is always the one created
    earlier, matching "scheduling X on top of an event that was already there".
    """
    cutoff = now - window
    conflicts: list[Conflict] = []
    for i, a in enumerate(events):
        for b in events[i + 1:]:
            if a.series and a.series == b.series:
                continue
            if not _overlaps(a, b):
                continue
            newer, older = (a, b) if a.created >= b.created else (b, a)
            if newer.created < cutoff:
                continue  # nothing newly scheduled here
            conflicts.append(Conflict(
                new_event=newer,
                existing_event=older,
                date=max(a.start, b.start),
            ))
    return conflicts


def all_conflicts(events: list[Event]) -> list[Conflict]:
    """Every current overlap, regardless of when created (for a backlog digest)."""
    out: list[Conflict] = []
    for i, a in enumerate(events):
        for b in events[i + 1:]:
            if a.series and a.series == b.series:
                continue
            if not _overlaps(a, b):
                continue
            newer, older = (a, b) if a.created >= b.created else (b, a)
            out.append(Conflict(newer, older, max(a.start, b.start)))
    return out


ALERT_RECIPIENTS = ["edeitrick@gmail.com", "davidcpcu@gmail.com"]
FAMILY_CALENDAR_ID = "family04215781631001689506@group.calendar.google.com"


if __name__ == "__main__":
    import json
    import sys

    data = json.load(open(sys.argv[1]))
    evs = parse_events(data["events"])
    now = datetime.now(timezone.utc)
    window = timedelta(minutes=int(sys.argv[2])) if len(sys.argv) > 2 else timedelta(days=30)
    found = find_new_conflicts(evs, now, window)
    print(f"{len(evs)} events, {len(found)} new-conflict alert(s) in the last {window}:\n")
    for c in found:
        print("SUBJECT:", c.subject)
        print("BODY:   ", c.body)
        print()
