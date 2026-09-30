"""In-process stand-ins for Davis (CalDAV) and Canvas, served over real HTTP so
sync.py's urllib code paths run unmodified. Only the requests sync.py actually
makes are implemented."""
import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlsplit
from xml.sax.saxutils import escape

PRINCIPAL = "/dav/principals/user/"
HOME = "/dav/calendars/user/"
DISPLAYNAME_RE = re.compile(r"<d:displayname>(.*?)</d:displayname>", re.S)
UID_RE = re.compile(r"^UID:(.+?)\r?$", re.M)


class FakeWorld:
    """Shared state for one test: calendars live under HOME as
    {slug: {"displayname": str, "objects": {name: (etag, ics_text)}}}."""

    def __init__(self):
        self.calendars = {}
        self.ics_feed = ""
        self.courses = []
        self.course_assignments = {}   # {course_id: [assignment dicts]}
        self.user_id = 1
        self.requests = []             # [(method, path)]
        self._etag = 0
        self.lock = threading.Lock()

    # --- helpers for tests ---
    def add_calendar(self, slug, displayname):
        self.calendars[slug] = {"displayname": displayname, "objects": {}}

    def calendar_by_name(self, displayname):
        for cal in self.calendars.values():
            if cal["displayname"] == displayname:
                return cal
        return None

    def names(self):
        return sorted(c["displayname"] for c in self.calendars.values())

    def put_object(self, slug, name, text):
        self._etag += 1
        self.calendars[slug]["objects"][name] = (f'"{self._etag}"', text)


class _Handler(BaseHTTPRequestHandler):
    world = None  # set per server

    def log_message(self, *args):
        pass

    def _body(self):
        length = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(length).decode("utf-8") if length else ""

    def _send(self, status, body=b"", headers=None):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(status)
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _multistatus(self, responses):
        xml = (
            '<?xml version="1.0" encoding="utf-8"?>'
            '<d:multistatus xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">'
            + "".join(responses) + "</d:multistatus>"
        )
        self._send(207, xml, {"Content-Type": "application/xml"})

    def _split(self):
        """-> (slug, object_name) for paths under HOME, else (None, None)."""
        path = unquote(urlsplit(self.path).path)
        if not path.startswith(HOME):
            return None, None
        parts = path[len(HOME):].strip("/").split("/")
        slug = parts[0] if parts[0] else None
        obj = parts[1] if len(parts) > 1 else None
        return slug, obj

    def _dispatch(self):
        w = self.world
        path = urlsplit(self.path).path
        with w.lock:
            w.requests.append((self.command, path))
            handler = getattr(self, "do_dav_" + self.command, None)
            if path.startswith("/dav") and handler:
                return handler()
            if self.command == "GET":
                return self.canvas_get()
            self._send(405)

    do_GET = do_PUT = do_DELETE = do_PROPFIND = do_MKCALENDAR = do_REPORT = _dispatch

    # --- CalDAV ---
    def do_dav_PROPFIND(self):
        self._body()
        path = urlsplit(self.path).path
        if path == "/dav/":
            return self._multistatus([
                f"<d:response><d:href>/dav/</d:href><d:propstat><d:prop>"
                f"<d:current-user-principal><d:href>{PRINCIPAL}</d:href></d:current-user-principal>"
                f"</d:prop></d:propstat></d:response>"
            ])
        if path == PRINCIPAL:
            return self._multistatus([
                f"<d:response><d:href>{PRINCIPAL}</d:href><d:propstat><d:prop>"
                f"<c:calendar-home-set><d:href>{HOME}</d:href></c:calendar-home-set>"
                f"</d:prop></d:propstat></d:response>"
            ])
        if path == HOME:
            responses = [
                f"<d:response><d:href>{HOME}</d:href><d:propstat><d:prop>"
                f"<d:resourcetype><d:collection/></d:resourcetype></d:prop></d:propstat></d:response>"
            ]
            for slug, cal in self.world.calendars.items():
                responses.append(
                    f"<d:response><d:href>{HOME}{slug}/</d:href><d:propstat><d:prop>"
                    f"<d:displayname>{escape(cal['displayname'])}</d:displayname>"
                    f"<d:resourcetype><d:collection/><c:calendar/></d:resourcetype>"
                    f"</d:prop></d:propstat></d:response>"
                )
            return self._multistatus(responses)
        self._send(404)

    def do_dav_MKCALENDAR(self):
        slug, _ = self._split()
        body = self._body()
        if slug in self.world.calendars:
            return self._send(405)
        m = DISPLAYNAME_RE.search(body)
        self.world.add_calendar(slug, m.group(1) if m else slug)
        self._send(201)

    def do_dav_DELETE(self):
        slug, obj = self._split()
        cal = self.world.calendars.get(slug)
        if cal is None:
            return self._send(404)
        if obj is None:
            del self.world.calendars[slug]
            return self._send(204)
        if cal["objects"].pop(obj, None) is None:
            return self._send(404)
        self._send(204)

    def do_dav_GET(self):
        slug, obj = self._split()
        cal = self.world.calendars.get(slug)
        if cal is None or obj not in cal["objects"]:
            return self._send(404)
        etag, text = cal["objects"][obj]
        self._send(200, text, {"ETag": etag, "Content-Type": "text/calendar"})

    def do_dav_PUT(self):
        slug, obj = self._split()
        body = self._body()
        cal = self.world.calendars.get(slug)
        if cal is None:
            return self._send(409)
        existing = cal["objects"].get(obj)
        if self.headers.get("If-None-Match") == "*" and existing:
            return self._send(412)
        if_match = self.headers.get("If-Match")
        if if_match and (not existing or existing[0] != if_match):
            return self._send(412)
        self.world.put_object(slug, obj, body)
        self._send(204 if existing else 201)

    def do_dav_REPORT(self):
        self._body()
        slug, _ = self._split()
        cal = self.world.calendars.get(slug)
        if cal is None:
            return self._send(404)
        responses = []
        for name, (_etag, text) in cal["objects"].items():
            responses.append(
                f"<d:response><d:href>{HOME}{slug}/{name}</d:href><d:propstat><d:prop>"
                f"<c:calendar-data>{escape(text)}</c:calendar-data>"
                f"</d:prop></d:propstat></d:response>"
            )
        self._multistatus(responses)

    # --- Canvas ---
    def canvas_get(self):
        w = self.world
        parts = urlsplit(self.path)
        path = parts.path
        if path.endswith(".ics"):
            return self._send(200, w.ics_feed, {"Content-Type": "text/calendar"})
        if path == "/api/v1/courses":
            return self._send(200, json.dumps(w.courses))
        if path == "/api/v1/users/self":
            return self._send(200, json.dumps({"id": w.user_id}))
        m = re.match(r"^/api/v1/courses/(\d+)/assignments$", path)
        if m:
            return self._send(200, json.dumps(w.course_assignments.get(int(m.group(1)), [])))
        m = re.match(r"^/api/v1/courses/\d+/discussion_topics/\d+/entries$", path)
        if m:
            return self._send(200, "[]")
        self._send(404)


class FakeServer:
    def __init__(self, world):
        handler = type("Handler", (_Handler,), {"world": world})
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.base_url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.httpd.shutdown()
        self.httpd.server_close()


def object_uid(ics_text):
    m = UID_RE.search(ics_text)
    return m.group(1).strip() if m else None
