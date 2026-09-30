"""End-to-end runs of sync.main() against the fake Davis + Canvas in fakes.py."""
from datetime import datetime, timedelta, timezone

import pytest

import sync
from fakes import FakeServer, FakeWorld, object_uid

DS = "DATA STRUCTURES"
CLOUD = "TPCS:CLOUD COMPUTING FUNDAMENT"
OLD = "OLD HISTORY"

CURRENT_TERM = 20
COURSES = [
    {"id": 101, "name": f"202610_CS350_1 {DS}", "start_at": "2026-08-20T00:00:00Z", "enrollment_term_id": CURRENT_TERM},
    {"id": 102, "name": f"202610_TPCS_2 {CLOUD}", "start_at": "2026-08-21T00:00:00Z", "enrollment_term_id": CURRENT_TERM},
    {"id": 90, "name": f"202520_HIST_3 {OLD}", "start_at": "2026-01-10T00:00:00Z", "enrollment_term_id": 10},
]


def day(n):
    return (datetime.now(timezone.utc).date() + timedelta(days=n)).strftime("%Y%m%d")


def vevent(assignment_id, title, code, due):
    return (
        "BEGIN:VEVENT\r\n"
        f"UID:event-assignment-{assignment_id}\r\n"
        f"SUMMARY:{title} [{code}]\r\n"
        f"DTSTART;VALUE=DATE:{due}\r\n"
        f"URL:https://canvas.example/a/{assignment_id}\r\n"
        "END:VEVENT\r\n"
    )


FEED = (
    "BEGIN:VCALENDAR\r\n"
    + vevent(1, "HW1", "202610_FALL_CS350_1", day(3))
    + vevent(2, "HW2", "202610_FALL_CS350_1", day(10))
    + vevent(3, "Lab 1", "202610_FALL_TPCS_2", day(4))
    + vevent(4, "Mystery", "999999_FALL_NOPE_0", day(5))
    + "END:VCALENDAR\r\n"
)


@pytest.fixture
def world():
    w = FakeWorld()
    w.ics_feed = FEED
    w.courses = [dict(c) for c in COURSES]
    return w


@pytest.fixture
def run(world, monkeypatch, capsys):
    """run(inactive=set(), token="t") -> stdout of one sync.main() pass."""
    with FakeServer(world) as server:
        monkeypatch.setattr(sync, "DAV_BASE_URL", server.base_url)
        monkeypatch.setattr(sync, "CANVAS_ICS_URL", server.base_url + "/feeds/calendars/user_x.ics")
        monkeypatch.setattr(sync, "CANVAS_API_TOKEN_ISSUED_AT", "")

        def _run(inactive=frozenset(), token="t"):
            monkeypatch.setattr(sync, "INACTIVE_COURSES", set(inactive))
            monkeypatch.setattr(sync, "CANVAS_API_TOKEN", token)
            world.requests.clear()
            sync.main()
            return capsys.readouterr().out

        yield _run


def uids(world, displayname):
    cal = world.calendar_by_name(displayname)
    assert cal is not None, f"no calendar {displayname!r}; have {world.names()}"
    return sorted(object_uid(text) for _etag, text in cal["objects"].values())


def test_fresh_run_creates_current_term_calendars_and_routes_assignments(world, run):
    out = run()
    assert world.names() == sorted(["Academics", DS, CLOUD])
    assert OLD not in world.names()
    assert uids(world, DS) == ["canvas-event-assignment-1", "canvas-event-assignment-2"]
    assert uids(world, CLOUD) == ["canvas-event-assignment-3"]
    # Unroutable course code falls back to Academics
    assert uids(world, "Academics") == ["canvas-event-assignment-4"]
    assert "created=4" in out and "errors=0" in out


def test_second_run_is_idempotent(world, run):
    world.ics_feed = FEED.replace(vevent(4, "Mystery", "999999_FALL_NOPE_0", day(5)), "")
    run()
    out = run()
    assert "created=0 updated=0 unchanged=3" in out
    assert not [r for r in world.requests if r[0] in ("PUT", "DELETE", "MKCALENDAR")]


def test_unroutable_assignment_is_stable_in_academics(world, run):
    # It falls back to Academics as canvas-event-assignment-*, the same prefix
    # the leftover cleanup targets -- it must not be deleted and recreated
    run()
    slug = next(s for s, c in world.calendars.items() if c["displayname"] == "Academics")
    _etag, text = world.calendars[slug]["objects"]["canvas-event-assignment-4.ics"]
    world.put_object(slug, "canvas-event-assignment-4.ics", text.replace("STATUS:NEEDS-ACTION", "STATUS:COMPLETED"))
    out = run()
    assert "removed" not in out
    assert "created=0 updated=0 unchanged=4" in out
    _etag, text = world.calendars[slug]["objects"]["canvas-event-assignment-4.ics"]
    assert "STATUS:COMPLETED" in text


def test_inactive_course_calendar_is_deleted(world, run):
    run()
    assert CLOUD in world.names()
    out = run(inactive={CLOUD})
    assert CLOUD not in world.names()
    assert f"archived calendar '{CLOUD}'" in out
    assert "skipped_inactive=1" in out
    # The active course is untouched and nothing leaks into Academics
    assert uids(world, DS) == ["canvas-event-assignment-1", "canvas-event-assignment-2"]
    assert uids(world, "Academics") == ["canvas-event-assignment-4"]


def test_inactive_course_is_not_recreated_on_later_runs(world, run):
    run(inactive={CLOUD})
    out = run(inactive={CLOUD})
    assert CLOUD not in world.names()
    assert "archived" not in out
    assert ("MKCALENDAR", "/dav/calendars/user/tpcs-cloud-computing-fundament/") not in world.requests


def test_inactive_course_skips_completion_polling(world, run):
    run(inactive={CLOUD})
    polled = {path for method, path in world.requests if path.endswith("/assignments")}
    assert polled == {"/api/v1/courses/101/assignments"}


def test_reactivating_recreates_and_refills_calendar(world, run):
    run(inactive={CLOUD})
    assert CLOUD not in world.names()
    run()
    assert uids(world, CLOUD) == ["canvas-event-assignment-3"]


def test_past_term_calendar_archived_but_unmanaged_ones_kept(world, run):
    world.add_calendar("old-history", OLD)
    world.add_calendar("personal", "Personal")
    run()
    assert OLD not in world.names()
    assert "Personal" in world.names()
    assert "Academics" in world.names()


def test_inactivating_every_course_keeps_academics(world, run):
    run()
    run(inactive={DS, CLOUD})
    assert world.names() == ["Academics"]


def test_without_canvas_api_nothing_is_deleted(world, run):
    world.add_calendar("tpcs-cloud-computing-fundament", CLOUD)
    world.add_calendar("old-history", OLD)
    out = run(inactive={CLOUD}, token="")
    assert CLOUD in world.names() and OLD in world.names()
    assert "archived" not in out
    # Without the API there is no code -> course mapping, so everything lands in Academics
    assert len(uids(world, "Academics")) == 4


def test_canvas_submission_auto_completes_new_task(world, run):
    world.course_assignments[101] = [{"id": 1, "submission": {"submitted_at": "2026-09-01T00:00:00Z"}}]
    out = run()
    cal = world.calendar_by_name(DS)
    _etag, text = cal["objects"]["canvas-event-assignment-1.ics"]
    assert "STATUS:COMPLETED" in text
    assert "auto_completed=1" in out


def test_hand_completion_is_never_reverted(world, run):
    run()
    cal = world.calendar_by_name(DS)
    etag, text = cal["objects"]["canvas-event-assignment-2.ics"]
    slug = next(s for s, c in world.calendars.items() if c["displayname"] == DS)
    world.put_object(slug, "canvas-event-assignment-2.ics", text.replace("STATUS:NEEDS-ACTION", "STATUS:COMPLETED"))
    # Change a Canvas-owned field so the task gets rewritten
    world.ics_feed = FEED.replace("HW2", "HW2 (revised)")
    out = run()
    _etag, text = cal["objects"]["canvas-event-assignment-2.ics"]
    assert "SUMMARY:HW2 (revised)" in text
    assert "STATUS:COMPLETED" in text
    assert "updated=1" in out


def test_leftover_assignment_tasks_removed_from_academics(world, run):
    world.add_calendar("academics", "Academics")
    world.put_object("academics", "canvas-event-assignment-77.ics",
                     "BEGIN:VCALENDAR\r\nBEGIN:VTODO\r\nUID:canvas-event-assignment-77\r\nEND:VTODO\r\nEND:VCALENDAR\r\n")
    world.put_object("academics", "mine.ics",
                     "BEGIN:VCALENDAR\r\nBEGIN:VTODO\r\nUID:my-own-task\r\nEND:VTODO\r\nEND:VCALENDAR\r\n")
    run()
    remaining = uids(world, "Academics")
    assert "canvas-event-assignment-77" not in remaining
    assert "my-own-task" in remaining


def test_empty_feed_aborts_before_touching_calendars(world, run):
    world.ics_feed = "BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n"
    world.add_calendar("old-history", OLD)
    with pytest.raises(SystemExit) as exc:
        run()
    assert exc.value.code == 1
    assert OLD in world.names()
