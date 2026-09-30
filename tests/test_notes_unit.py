from datetime import datetime, timedelta, timezone

import pytest

import notes


def iso_in(days):
    return (datetime.now(timezone.utc) + timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")


def test_parse_inactive_courses_matches_sync():
    import sync
    for raw in ["", '["A", "B"]', "A, B", '["TPCS:CLOUD COMPUTING FUNDAMENT"]']:
        assert notes.parse_inactive_courses(raw) == sync.parse_inactive_courses(raw)


def test_current_term_courses():
    old = {"id": 1, "start_at": "2025-08-20T00:00:00Z", "enrollment_term_id": 10}
    new = {"id": 2, "start_at": "2026-08-20T00:00:00Z", "enrollment_term_id": 20}
    assert notes.current_term_courses([old, new]) == [new]


def test_clean_course_name():
    assert notes.clean_course_name("202610_CS350_1 DATA STRUCTURES") == "DATA STRUCTURES"
    assert notes.clean_course_name(None) == ""


def test_html_to_text():
    assert notes.html_to_text("<p>Hello&nbsp;<b>world</b></p>\n\n\n<p>x</p>") == "Hello\xa0 world \n\n x"
    assert notes.html_to_text("") == ""


def test_extract_file_ids_dedupes_in_order():
    html = '<a href="/courses/1/files/42/download">a</a> <img src="/files/7"> <a href="/files/42">'
    assert notes.extract_file_ids(html) == ["42", "7"]


@pytest.mark.parametrize("content_type,name,expected", [
    ("application/pdf", "x", True),
    ("application/octet-stream", "Slides.PDF", True),
    (notes.PPTX_CONTENT_TYPE, "x", True),
    ("application/octet-stream", "deck.pptx", True),
    ("application/msword", "doc.docx", False),
])
def test_is_presentation_file(content_type, name, expected):
    assert notes.is_presentation_file(content_type, name) is expected


def test_classify_external_url():
    assert notes.classify_external_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == ("youtube", "dQw4w9WgXcQ")
    kind, (url, ctype) = notes.classify_external_url("https://docs.google.com/presentation/d/abc123/edit")
    assert kind == "google_file" and url.endswith("/abc123/export/pptx") and ctype == notes.PPTX_CONTENT_TYPE
    assert notes.classify_external_url("https://docs.google.com/document/d/doc1/edit") == (
        "url", "https://docs.google.com/document/d/doc1/export?format=txt")
    assert notes.classify_external_url("https://example.com/page") == ("url", "https://example.com/page")


def test_assignment_bucket(monkeypatch):
    monkeypatch.setattr(notes, "CURRENT_WINDOW_DAYS", 14)
    assert notes.assignment_bucket(None) == notes.BUCKET_FUTURE
    assert notes.assignment_bucket("garbage") == notes.BUCKET_FUTURE
    assert notes.assignment_bucket(iso_in(-2)) == notes.BUCKET_PAST
    assert notes.assignment_bucket(iso_in(3)) == notes.BUCKET_CURRENT
    assert notes.assignment_bucket(iso_in(30)) == notes.BUCKET_FUTURE
