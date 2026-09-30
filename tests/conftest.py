"""Both scripts read their config from the environment at import time, so the
minimum required variables are set here before any test module imports them.
Tests that need a different value monkeypatch the module attribute instead."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

_TEST_ENV = {
    "CANVAS_ICS_URL": "http://canvas.invalid/feeds/calendars/user_x.ics",
    "CANVAS_API_TOKEN": "",
    "CANVAS_API_TOKEN_ISSUED_AT": "",
    "TOKEN_FILE": os.path.join(ROOT, "tests", "does-not-exist.json"),
    "DAV_USERNAME": "user",
    "DAV_PASSWORD": "pass",
    "INACTIVE_COURSES": "",
    "CHAT_API_KEY": "test",
    "OUTLINE_API_TOKEN": "test",
    "CANVAS_TZ": "America/New_York",
}
for key, value in _TEST_ENV.items():
    os.environ[key] = value
os.environ.pop("EXTRA_CA_CERT_FILE", None)
