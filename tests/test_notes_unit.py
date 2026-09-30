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


class TestChatCompletion:
    def fake_api(self, monkeypatch, replies):
        calls = []

        def fake_http_json(method, url, headers=None, body=None, timeout=60):
            calls.append(body["max_tokens"])
            return replies.pop(0)

        monkeypatch.setattr(notes, "http_json", fake_http_json)
        monkeypatch.setattr(notes, "CHAT_MAX_TOKENS", 1000)
        return calls

    @staticmethod
    def reply(content, finish_reason="stop"):
        return 200, {"choices": [{"message": {"content": content}, "finish_reason": finish_reason}]}

    def test_returns_content(self, monkeypatch):
        calls = self.fake_api(monkeypatch, [self.reply("notes")])
        assert notes.chat_completion("m", "prompt") == "notes"
        assert calls == [1000]

    def test_all_reasoning_retries_with_double_budget(self, monkeypatch):
        calls = self.fake_api(monkeypatch, [self.reply(None, "length"), self.reply("notes")])
        assert notes.chat_completion("m", "prompt") == "notes"
        assert calls == [1000, 2000]

    def test_gives_up_with_clear_error_after_one_retry(self, monkeypatch):
        calls = self.fake_api(monkeypatch, [self.reply(None, "length"), self.reply(None, "length")])
        with pytest.raises(RuntimeError, match="returned no content"):
            notes.chat_completion("m", "prompt")
        assert calls == [1000, 2000]

    def test_empty_content_without_length_does_not_retry(self, monkeypatch):
        calls = self.fake_api(monkeypatch, [self.reply("  ", "stop")])
        with pytest.raises(RuntimeError, match="finish_reason=stop"):
            notes.chat_completion("m", "prompt")
        assert calls == [1000]

    def test_truncated_content_is_kept(self, monkeypatch):
        self.fake_api(monkeypatch, [self.reply("partial", "length")])
        assert notes.chat_completion("m", "prompt") == "partial"

    def test_auth_failure(self, monkeypatch):
        self.fake_api(monkeypatch, [(401, {"error": "bad key"})])
        with pytest.raises(notes.AuthFailure):
            notes.chat_completion("m", "prompt")
