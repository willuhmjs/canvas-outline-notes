from datetime import datetime, timedelta, timezone

import pytest

import sync


def days_from_today(n):
    return (datetime.now(timezone.utc).date() + timedelta(days=n)).strftime("%Y%m%d")


class TestParseInactiveCourses:
    def test_empty_means_all_active(self):
        assert sync.parse_inactive_courses("") == set()
        assert sync.parse_inactive_courses(None) == set()
        assert sync.parse_inactive_courses("   ") == set()

    def test_json_array(self):
        assert sync.parse_inactive_courses('["A", " B ", ""]') == {"A", "B"}

    def test_comma_separated_fallback(self):
        assert sync.parse_inactive_courses("A, B ,,C") == {"A", "B", "C"}

    def test_names_containing_colons_survive(self):
        raw = '["TPCS:CLOUD COMPUTING FUNDAMENT"]'
        assert sync.parse_inactive_courses(raw) == {"TPCS:CLOUD COMPUTING FUNDAMENT"}

    def test_non_list_json_treated_as_plain_text(self):
        # A JSON scalar is not a list, so it falls through to comma splitting
        assert sync.parse_inactive_courses('"A"') == {'"A"'}


class TestCourseNames:
    def test_clean_canvas_course_name(self):
        raw = "202610_ASTP103N_18192 INTRO ASTRONOMY-SOLAR SYSTEM"
        assert sync.clean_canvas_course_name(raw) == "INTRO ASTRONOMY-SOLAR SYSTEM"

    def test_clean_canvas_course_name_passthrough(self):
        assert sync.clean_canvas_course_name(" Sandbox ") == "Sandbox"
        assert sync.clean_canvas_course_name(None) == ""

    def test_normalize_ics_code(self):
        assert sync.normalize_ics_code("202610_FALL_ASTP103N_18192") == "202610_ASTP103N_18192"
        assert sync.normalize_ics_code("202620_spring_CS350_1") == "202620_CS350_1"

    def test_build_ics_to_course_map(self):
        courses = [
            {"name": "202610_ASTP103N_18192 INTRO ASTRONOMY"},
            {"name": "Sandbox"},
            {"name": "202610_CS350_1 "},
        ]
        assert sync.build_ics_to_course_map(courses) == {"202610_ASTP103N_18192": "INTRO ASTRONOMY"}


class TestCurrentTermCourses:
    def test_picks_term_of_most_recently_started_course(self):
        old = {"id": 1, "start_at": "2025-08-20T00:00:00Z", "enrollment_term_id": 10}
        new_a = {"id": 2, "start_at": "2026-08-20T00:00:00Z", "enrollment_term_id": 20}
        new_b = {"id": 3, "start_at": None, "enrollment_term_id": 20}
        assert sync.current_term_courses([old, new_a, new_b]) == [new_a, new_b]

    def test_no_dated_courses_returns_all(self):
        courses = [{"id": 1}, {"id": 2}]
        assert sync.current_term_courses(courses) == courses


class TestIcsParsing:
    def test_unfold(self):
        assert sync.unfold("A:1\r\n 23\r\nB:4") == ["A:123", "B:4"]

    def test_escape_roundtrip(self):
        value = "a, b; c\\d\nnext"
        assert sync.ics_unescape(sync.ics_escape(value)) == value

    def test_due_date_all_day_passthrough(self):
        assert sync.due_date_from_dtstart("20260915") == "20260915"

    def test_due_date_converts_utc_to_local_day(self):
        # 23:59 EDT on the 15th is 03:59Z on the 16th
        assert sync.due_date_from_dtstart("20260916T035900Z") == "20260915"

    def test_parse_assignments(self):
        raw = (
            "BEGIN:VCALENDAR\r\n"
            "BEGIN:VEVENT\r\n"
            "UID:event-assignment-1\r\n"
            "SUMMARY:Quiz 1\\, part A [202610_FALL_X_1]\r\n"
            "DTSTART;VALUE=DATE;VALUE=DATE:20260915\r\n"
            "URL:https://canvas/a/1\r\n"
            "DESCRIPTION:line1\\nline2\r\n"
            "END:VEVENT\r\n"
            "BEGIN:VEVENT\r\n"
            "UID:event-no-date\r\n"
            "SUMMARY:dropped\r\n"
            "END:VEVENT\r\n"
            "END:VCALENDAR\r\n"
        )
        assert sync.parse_assignments(raw) == [{
            "uid": "event-assignment-1",
            "summary": "Quiz 1, part A [202610_FALL_X_1]",
            "due_date": "20260915",
            "url": "https://canvas/a/1",
            "description": "line1\nline2",
        }]

    def test_parse_vtodo_fields_ignores_valarm(self):
        body = sync.build_vtodo(
            "canvas-x", "Task", "20260915", "https://u", "task desc",
            "NEEDS-ACTION", None, None, 3, "COURSE", 5,
        )
        fields = sync.parse_vtodo_fields(body)
        assert fields["DESCRIPTION"] == "task desc"
        assert fields["SUMMARY"] == "Task"
        assert fields["DUE"] == "20260915"
        assert fields["SEQUENCE"] == "3"
        assert fields["CATEGORIES"] == "COURSE"
        assert fields["PRIORITY"] == "5"
        assert "COMPLETED" not in fields


class TestSmallHelpers:
    def test_canvas_uid_to_object_uid(self):
        assert sync.canvas_uid_to_object_uid("event-assignment-1") == "canvas-event-assignment-1"
        assert sync.canvas_uid_to_object_uid("a/b c") == "canvas-a-b-c"

    def test_split_summary_categories(self):
        assert sync.split_summary_categories("Quiz [202610_FALL_X_1]") == ("Quiz", "202610_FALL_X_1")
        assert sync.split_summary_categories("No code") == ("No code", "")

    @pytest.mark.parametrize("days,expected", [(-3, 1), (2, 1), (3, 5), (7, 5), (8, 9)])
    def test_compute_priority(self, days, expected):
        assert sync.compute_priority(days_from_today(days)) == expected

    def test_within_completion_window(self, monkeypatch):
        monkeypatch.setattr(sync, "COMPLETION_LOOKBACK_DAYS", 30)
        monkeypatch.setattr(sync, "COMPLETION_LOOKAHEAD_DAYS", 21)
        assert sync.within_completion_window(days_from_today(0))
        assert sync.within_completion_window(days_from_today(-30))
        assert not sync.within_completion_window(days_from_today(-31))
        assert not sync.within_completion_window(days_from_today(22))

    def test_calendar_slug(self):
        assert sync.calendar_slug("TPCS:CLOUD COMPUTING FUNDAMENT") == "tpcs-cloud-computing-fundament"
        assert sync.calendar_slug("R&D") == "randd"
        assert sync.calendar_slug("!!!") == "calendar"

    def test_parse_next_link(self):
        header = '<https://c/api?page=1>; rel="current", <https://c/api?page=2>; rel="next"'
        assert sync.parse_next_link(header) == "https://c/api?page=2"
        assert sync.parse_next_link('<https://c/api?page=1>; rel="last"') is None
        assert sync.parse_next_link(None) is None


class TestArchiveStaleCalendars:
    def run(self, monkeypatch, calendars, keep, managed, status=204):
        deleted = []

        def fake_request(method, url, **_):
            deleted.append((method, url))
            return status, {}, b""

        monkeypatch.setattr(sync, "dav_request", fake_request)
        sync.archive_stale_calendars("/home/", calendars, keep, managed)
        return deleted

    def test_deletes_managed_calendars_not_kept(self, monkeypatch):
        calendars = {"Academics": "/a", "ASTRO": "/astro", "CALC": "/calc", "OLD": "/old", "Personal": "/p"}
        deleted = self.run(monkeypatch, calendars, {"CALC"}, {"ASTRO", "CALC", "OLD"})
        assert deleted == [("DELETE", "/astro"), ("DELETE", "/old")]
        assert sorted(calendars) == ["Academics", "CALC", "Personal"]

    def test_academics_is_protected_even_if_managed(self, monkeypatch):
        calendars = {"Academics": "/a"}
        assert self.run(monkeypatch, calendars, set(), {"Academics"}) == []
        assert calendars == {"Academics": "/a"}

    def test_failed_delete_keeps_entry(self, monkeypatch):
        calendars = {"OLD": "/old"}
        self.run(monkeypatch, calendars, set(), {"OLD"}, status=500)
        assert calendars == {"OLD": "/old"}
