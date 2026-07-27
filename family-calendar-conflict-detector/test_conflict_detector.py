"""Tests for the conflict detector. Run: python3 -m pytest (or python3 test_conflict_detector.py)."""

from datetime import datetime, timezone, timedelta

from conflict_detector import (
    parse_events, find_new_conflicts, all_conflicts, Event,
)

NOW = datetime(2026, 7, 27, 12, 0, tzinfo=timezone.utc)

RAW = [
    # An all-day camping trip created a while ago.
    {"id": "camp", "summary": "Jellystone Camping", "status": "confirmed",
     "start": {"date": "2026-08-02"}, "end": {"date": "2026-08-05"},
     "created": "2026-06-01T00:00:00Z",
     "creator": {"displayName": "Elise Deitrick", "email": "edeitrick@gmail.com"}},
    # A timed appointment just added on top of the camping day.
    {"id": "ot", "summary": "EVIE OT", "status": "confirmed",
     "start": {"dateTime": "2026-08-03T14:00:00Z"}, "end": {"dateTime": "2026-08-03T15:00:00Z"},
     "created": "2026-07-27T09:00:00Z",
     "creator": {"displayName": "David", "email": "davidcpcu@gmail.com"}},
    # A far-away event that overlaps nothing.
    {"id": "solo", "summary": "Dentist", "status": "confirmed",
     "start": {"dateTime": "2026-09-01T14:00:00Z"}, "end": {"dateTime": "2026-09-01T15:00:00Z"},
     "created": "2026-07-27T09:00:00Z", "creator": {"displayName": "David"}},
]


def test_all_day_counts_as_conflict_and_newer_is_the_scheduler():
    events = parse_events(RAW)
    conflicts = find_new_conflicts(events, NOW, timedelta(hours=4))
    assert len(conflicts) == 1
    c = conflicts[0]
    assert c.new_event.id == "ot"            # the just-created event
    assert c.existing_event.id == "camp"     # the pre-existing all-day event
    assert c.new_event.creator == "David"


def test_subject_and_body_format():
    c = find_new_conflicts(parse_events(RAW), NOW, timedelta(hours=4))[0]
    assert c.subject == "CONFLICT: EVIE OT is attempting to overlap with existing event Jellystone Camping"
    assert c.body == "David is attempting to schedule EVIE OT on top of Jellystone Camping on Monday, August 3, 2026."


def test_window_excludes_old_events():
    # With a tiny window, nothing was "just" created -> no alerts.
    assert find_new_conflicts(parse_events(RAW), NOW, timedelta(minutes=1)) == []


def test_same_recurring_series_never_conflicts():
    raw = [
        {"id": "a", "summary": "Soccer", "status": "confirmed", "recurringEventId": "s1",
         "start": {"dateTime": "2026-08-03T14:00:00Z"}, "end": {"dateTime": "2026-08-03T15:00:00Z"},
         "created": "2026-07-27T09:00:00Z", "creator": {"displayName": "David"}},
        {"id": "b", "summary": "Soccer", "status": "confirmed", "recurringEventId": "s1",
         "start": {"dateTime": "2026-08-03T14:30:00Z"}, "end": {"dateTime": "2026-08-03T15:30:00Z"},
         "created": "2026-07-27T09:00:00Z", "creator": {"displayName": "David"}},
    ]
    assert find_new_conflicts(parse_events(raw), NOW, timedelta(hours=4)) == []


def test_touching_edges_do_not_overlap():
    raw = [
        {"id": "a", "summary": "A", "status": "confirmed",
         "start": {"dateTime": "2026-08-03T14:00:00Z"}, "end": {"dateTime": "2026-08-03T15:00:00Z"},
         "created": "2026-07-27T09:00:00Z", "creator": {"displayName": "X"}},
        {"id": "b", "summary": "B", "status": "confirmed",
         "start": {"dateTime": "2026-08-03T15:00:00Z"}, "end": {"dateTime": "2026-08-03T16:00:00Z"},
         "created": "2026-07-27T09:00:00Z", "creator": {"displayName": "X"}},
    ]
    assert find_new_conflicts(parse_events(raw), NOW, timedelta(hours=4)) == []


def test_cancelled_events_ignored():
    raw = RAW + [{"id": "x", "summary": "Cancelled", "status": "cancelled",
                  "start": {"dateTime": "2026-08-03T14:00:00Z"},
                  "end": {"dateTime": "2026-08-03T15:00:00Z"},
                  "created": "2026-07-27T09:00:00Z", "creator": {"displayName": "X"}}]
    assert len(parse_events(raw)) == len(RAW)


def test_emailer_builds_correct_message():
    import emailer
    c = find_new_conflicts(parse_events(RAW), NOW, timedelta(hours=4))[0]
    msg = emailer.build_message("edeitrick@gmail.com",
                                ["edeitrick@gmail.com", "davidcpcu@gmail.com"],
                                c.subject, c.body)
    assert msg["Subject"] == "CONFLICT: EVIE OT is attempting to overlap with existing event Jellystone Camping"
    assert msg["To"] == "edeitrick@gmail.com, davidcpcu@gmail.com"
    assert msg.get_content().strip() == c.body


if __name__ == "__main__":
    fns = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for fn in fns:
        fn()
        print("ok:", fn.__name__)
    print(f"\n{len(fns)} tests passed")
