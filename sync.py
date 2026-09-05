#!/usr/bin/env python3
"""Upsert Canvas assignment due dates into a Davis CalDAV calendar as VTODOs.

Idempotent by design: each Canvas assignment UID maps to one deterministic CalDAV
object URL, so re-runs update in place instead of creating duplicates. Completion
state (STATUS/COMPLETED/PERCENT-COMPLETE) is always read back from the server and
carried forward untouched -- this script only ever writes Canvas-owned fields
(SUMMARY/DUE/URL/DESCRIPTION/CATEGORIES/PRIORITY/VALARM). PRIORITY is recomputed
from days-until-due on every run, so it escalates over time even if nothing else
changed. Assignments that disappear from the feed are left alone (no deletes).

If CANVAS_API_TOKEN is set, also auto-marks a task COMPLETED once Canvas shows it
submitted/graded/excused (see build_completion_map) -- one-directional only, never
reverts a completion you set yourself, and silently skipped entirely if the token
is missing or the API call fails.

If CANVAS_API_TOKEN_ISSUED_AT is also set (canvas-token-updater sets it whenever a
token is saved), also self-schedules a "Renew Canvas API token" reminder task --
see sync_token_renewal_reminder for why this has to be an estimate.
"""
import base64
import json
import os
import re
import ssl
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
import zoneinfo
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlencode, urljoin, urlsplit

# To trust a self-signed proxy/CA (e.g. a MITM-inspecting reverse proxy in front
# of Canvas), set EXTRA_CA_CERT_FILE to a mounted PEM file. Verification stays
# fully enabled; the CA is added on top of the system trust store. Left unset,
# requests use standard verified HTTPS with no changes.
_extra_ca_file = os.environ.get("EXTRA_CA_CERT_FILE")
if _extra_ca_file:
    _ssl_ctx = ssl.create_default_context()
    _ssl_ctx.load_verify_locations(cafile=_extra_ca_file)
    urllib.request.install_opener(
        urllib.request.build_opener(urllib.request.HTTPSHandler(context=_ssl_ctx))
    )

COURSE_CODE_RE = re.compile(r"^(.*)\s\[([^\[\]]+)\]$")
PLAIN_ASSIGNMENT_UID_RE = re.compile(r"^event-assignment-(\d+)$")
# Matches Canvas API course names like "202610_ASTP103N_18192 INTRO ASTRONOMY-SOLAR SYSTEM"
CANVAS_NAME_RE = re.compile(r"^\d+_\w+_\d+\s+(.*)$")
# Season segment present in ICS course codes but not in Canvas API name prefixes
ICS_SEASON_RE = re.compile(r"_(FALL|SPRING|SUMMER|WINTER)_", re.IGNORECASE)

# How far around "today" to bother asking Canvas about completion at all -- no
# point checking something due in 2 months (guaranteed not submitted yet), and
# if something's still not graded 30+ days after its due date, further polling
# isn't going to resolve it quickly. Deliberately narrow: keeps the per-run
# Canvas API footprint tiny and independent of how many assignments are synced.
COMPLETION_LOOKBACK_DAYS = int(os.environ.get("COMPLETION_LOOKBACK_DAYS", 30))
COMPLETION_LOOKAHEAD_DAYS = int(os.environ.get("COMPLETION_LOOKAHEAD_DAYS", 21))
CANVAS_API_TOKEN_ESTIMATED_LIFETIME_DAYS = int(os.environ.get("TOKEN_LIFETIME_DAYS", 90))
TOKEN_RENEWAL_LEAD_DAYS = int(os.environ.get("TOKEN_RENEWAL_LEAD_DAYS", 7))
ALARM_TRIGGER = os.environ.get("ALARM_TRIGGER", "PT6H")
CANVAS_TZ = zoneinfo.ZoneInfo(os.environ.get("CANVAS_TZ", "America/New_York"))

CANVAS_ICS_URL = os.environ["CANVAS_ICS_URL"]
CANVAS_API_TOKEN = os.environ.get("CANVAS_API_TOKEN", "")
CANVAS_API_TOKEN_ISSUED_AT = os.environ.get("CANVAS_API_TOKEN_ISSUED_AT", "")

# Fall back to token file written by the management app (Docker / bare-metal mode)
if not CANVAS_API_TOKEN:
    _token_file = os.environ.get("TOKEN_FILE", "/data/token.json")
    try:
        with open(_token_file) as _f:
            _td = json.load(_f)
            CANVAS_API_TOKEN = _td.get("token", "")
            if not CANVAS_API_TOKEN_ISSUED_AT:
                CANVAS_API_TOKEN_ISSUED_AT = _td.get("issued_at", "")
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        pass

DAV_BASE_URL = os.environ.get("DAV_BASE_URL", "http://davis:9000").rstrip("/")
DAV_USERNAME = os.environ["DAV_USERNAME"]
DAV_PASSWORD = os.environ["DAV_PASSWORD"]
DAV_CALENDAR_DISPLAYNAME = os.environ.get("DAV_CALENDAR_DISPLAYNAME", "Academics")

NS = {"d": "DAV:", "c": "urn:ietf:params:xml:ns:caldav"}
AUTH_HEADER = "Basic " + base64.b64encode(f"{DAV_USERNAME}:{DAV_PASSWORD}".encode()).decode()


def dav_request(method, url, body=None, headers=None):
    req_headers = {"Authorization": AUTH_HEADER}
    if headers:
        req_headers.update(headers)
    data = body.encode("utf-8") if isinstance(body, str) else body
    req = urllib.request.Request(url, data=data, method=method, headers=req_headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, resp.headers, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers, e.read()


def propfind(url, body, depth="0"):
    status, _headers, content = dav_request(
        "PROPFIND", url, body=body,
        headers={"Depth": depth, "Content-Type": "application/xml; charset=utf-8"},
    )
    if status != 207:
        raise RuntimeError(f"PROPFIND {url} failed: {status} {content[:300]!r}")
    return ET.fromstring(content)


def text_of(el, path):
    found = el.find(path, NS)
    return found.text if found is not None else None


def discover_calendar_home():
    """Return the calendar home collection URL for the authenticated user."""
    root = propfind(
        DAV_BASE_URL + "/dav/",
        '<?xml version="1.0" encoding="utf-8"?>'
        '<d:propfind xmlns:d="DAV:"><d:prop><d:current-user-principal/></d:prop></d:propfind>',
    )
    principal_href = text_of(root, ".//d:response/d:propstat/d:prop/d:current-user-principal/d:href")
    if not principal_href:
        raise RuntimeError("could not discover current-user-principal")
    root = propfind(
        urljoin(DAV_BASE_URL + "/", principal_href),
        '<?xml version="1.0" encoding="utf-8"?>'
        '<d:propfind xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">'
        '<d:prop><c:calendar-home-set/></d:prop></d:propfind>',
    )
    home_href = text_of(root, ".//d:response/d:propstat/d:prop/c:calendar-home-set/d:href")
    if not home_href:
        raise RuntimeError("could not discover calendar-home-set")
    return urljoin(DAV_BASE_URL + "/", home_href)


def list_calendars(home_href):
    """Return {displayname: absolute_href} for all calendars under home_href."""
    root = propfind(
        home_href,
        '<?xml version="1.0" encoding="utf-8"?>'
        '<d:propfind xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">'
        '<d:prop><d:displayname/><d:resourcetype/></d:prop></d:propfind>',
        depth="1",
    )
    result = {}
    for response in root.findall(".//d:response", NS):
        href = text_of(response, "d:href")
        displayname = text_of(response, ".//d:prop/d:displayname") or ""
        # Only include actual calendar collections, not the home collection itself
        is_calendar = response.find(".//c:calendar", NS) is not None
        if is_calendar and displayname and href:
            result[displayname] = urljoin(DAV_BASE_URL + "/", href)
    return result


def calendar_slug(displayname):
    """URL-safe path segment for a calendar display name."""
    slug = re.sub(r"[^a-z0-9]+", "-", displayname.lower().replace("&", "and"))
    return slug.strip("-") or "calendar"


def ensure_calendar(home_href, calendars, displayname):
    """Return href for an existing calendar, creating it if needed."""
    if displayname in calendars:
        return calendars[displayname]
    slug = calendar_slug(displayname)
    # Avoid slug collisions with existing calendars by appending a counter
    base_slug = slug
    counter = 2
    existing_slugs = {href.rstrip("/").rsplit("/", 1)[-1] for href in calendars.values()}
    while slug in existing_slugs:
        slug = f"{base_slug}-{counter}"
        counter += 1
    url = urljoin(home_href if home_href.endswith("/") else home_href + "/", slug + "/")
    body = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<c:mkcalendar xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">'
        "<d:set><d:prop>"
        f"<d:displayname>{displayname}</d:displayname>"
        "</d:prop></d:set>"
        "</c:mkcalendar>"
    )
    status, _, content = dav_request(
        "MKCALENDAR", url, body=body,
        headers={"Content-Type": "application/xml; charset=utf-8"},
    )
    if status not in (201, 204):
        raise RuntimeError(f"MKCALENDAR '{displayname}' failed: {status} {content[:200]!r}")
    print(f"created calendar '{displayname}'")
    calendars[displayname] = url
    return url


def archive_stale_calendars(home_href, calendars, current_names, all_managed_names):
    """Delete calendars for courses that are no longer in the current term.

    Only touches calendars whose displayname appears in all_managed_names (i.e. it
    was created by this script for a Canvas course). Never touches DAV_CALENDAR_DISPLAYNAME
    ('Academics') or any calendar with an unrecognised name.
    """
    protected = {DAV_CALENDAR_DISPLAYNAME}
    for name in list(calendars):
        if name in protected or name not in all_managed_names:
            continue
        if name in current_names:
            continue
        href = calendars[name]
        status, _, content = dav_request("DELETE", href)
        if status in (200, 204):
            print(f"archived calendar '{name}' (semester ended)")
            del calendars[name]
        else:
            print(f"WARNING: could not archive '{name}': {status} {content[:100]!r}", file=sys.stderr)


def clean_canvas_course_name(raw_name):
    """'202610_ASTP103N_18192 INTRO ASTRONOMY-SOLAR SYSTEM' -> 'INTRO ASTRONOMY-SOLAR SYSTEM'."""
    m = CANVAS_NAME_RE.match(raw_name or "")
    return m.group(1).strip() if m else (raw_name or "").strip()


def normalize_ics_code(ics_code):
    """Strip season segment so ICS codes align with Canvas API name prefixes.
    '202610_FALL_ASTP103N_18192' -> '202610_ASTP103N_18192'
    """
    return ICS_SEASON_RE.sub("_", ics_code)


def build_ics_to_course_map(courses):
    """Return {normalized_ics_prefix: clean_course_name} from Canvas API course list."""
    mapping = {}
    for c in courses:
        raw = c.get("name", "")
        # Canvas name: "202610_ASTP103N_18192 INTRO ASTRONOMY-SOLAR SYSTEM"
        m = re.match(r"^(\d+_\w+_\d+)\s+(.*)", raw)
        if not m:
            continue
        prefix = m.group(1)       # "202610_ASTP103N_18192"
        clean = m.group(2).strip()  # "INTRO ASTRONOMY-SOLAR SYSTEM"
        if clean:
            mapping[prefix] = clean
    return mapping


def fetch_canvas_ics():
    req = urllib.request.Request(CANVAS_ICS_URL, headers={"User-Agent": "homelab-canvas-sync/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


def canvas_api_base():
    parts = urlsplit(CANVAS_ICS_URL)
    return f"{parts.scheme}://{parts.netloc}"


def parse_next_link(link_header):
    """RFC 5988 Link header parsing -- just enough to find rel="next"."""
    if not link_header:
        return None
    for part in link_header.split(","):
        section = [p.strip() for p in part.split(";")]
        if len(section) < 2 or 'rel="next"' not in section[1:]:
            continue
        url_part = section[0]
        if url_part.startswith("<") and url_part.endswith(">"):
            return url_part[1:-1]
    return None


def current_term_courses(courses):
    """Canvas's enrollment_state=active includes concluded past-term courses too
    (confirmed live: Fall 2025 and Spring 2026 courses both still showed up
    alongside real current Fall 2026 ones -- and end_at isn't reliable either,
    the old course's was set a year out same as the current term's). Instead:
    current term = whichever enrollment_term_id belongs to the most-recently-
    *started* course, which adapts automatically each semester.
    """
    dated = [(c["start_at"], c) for c in courses if c.get("start_at") and c.get("enrollment_term_id")]
    if not dated:
        return courses
    current_term_id = max(dated, key=lambda pair: pair[0])[1]["enrollment_term_id"]
    return [c for c in courses if c.get("enrollment_term_id") == current_term_id]


def canvas_api_get_all(path, params=None):
    url = canvas_api_base() + path
    if params:
        url += "?" + urlencode(params, doseq=True)
    headers = {"Authorization": f"Bearer {CANVAS_API_TOKEN}"}
    results = []
    while url:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as resp:
            results.extend(json.loads(resp.read()))
            url = parse_next_link(resp.headers.get("Link"))
    return results


def within_completion_window(due_date):
    due = date(int(due_date[0:4]), int(due_date[4:6]), int(due_date[6:8]))
    days_left = (due - datetime.now(timezone.utc).date()).days
    return -COMPLETION_LOOKBACK_DAYS <= days_left <= COMPLETION_LOOKAHEAD_DAYS


def canvas_api_get(path):
    url = canvas_api_base() + path
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {CANVAS_API_TOKEN}"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def has_discussion_post(course_id, topic_id, user_id):
    """True if the current user has at least one top-level entry in the discussion."""
    try:
        entries = canvas_api_get_all(
            f"/api/v1/courses/{course_id}/discussion_topics/{topic_id}/entries",
            {"per_page": 100},
        )
        return any(str(e.get("user_id")) == str(user_id) for e in entries)
    except Exception:
        return False


def build_completion_map(pre_fetched_courses=None):
    """{assignment_id: is_done} from Canvas's own submission/grade data -- the
    ICS feed has no completion signal at all, so this is the only way to know.

    "Done" = submitted, graded, excused, OR (for discussion assignments) the
    user has at least one post on the board even if Canvas hasn't graded it yet.

    Best-effort and self-contained: any failure (missing/revoked token, API
    hiccup) just means auto-completion is skipped for this run -- it must
    never take down due-date syncing, which doesn't depend on this at all.
    """
    if not CANVAS_API_TOKEN:
        return {}
    try:
        completion = {}
        all_courses = pre_fetched_courses or canvas_api_get_all("/api/v1/courses", {"enrollment_state": "active", "per_page": 100})
        courses = current_term_courses(all_courses)

        # Get current user ID once for discussion post checks
        try:
            user_id = canvas_api_get("/api/v1/users/self").get("id")
        except Exception:
            user_id = None

        for course in courses:
            course_id = course.get("id")
            if course_id is None:
                continue
            assignments = canvas_api_get_all(
                f"/api/v1/courses/{course_id}/assignments",
                {"include[]": ["submission", "discussion_topic"], "per_page": 100},
            )
            for a in assignments:
                submission = a.get("submission") or {}
                done = bool(
                    submission.get("submitted_at")
                    or submission.get("excused")
                    or submission.get("grade") is not None
                )
                # For discussion assignments Canvas often doesn't set submitted_at
                # until after grading -- check if the user has actually posted instead.
                if not done and user_id and "discussion_topic" in (a.get("submission_types") or []):
                    topic = a.get("discussion_topic") or {}
                    topic_id = topic.get("id")
                    if topic_id:
                        done = has_discussion_post(course_id, topic_id, user_id)
                completion[str(a.get("id"))] = done
        return completion
    except Exception as exc:
        print(f"WARNING: Canvas API completion check failed, skipping auto-completion this run: {exc}", file=sys.stderr)
        return {}


def unfold(raw):
    lines = raw.replace("\r\n", "\n").split("\n")
    unfolded = []
    for line in lines:
        if line.startswith((" ", "\t")) and unfolded:
            unfolded[-1] += line[1:]
        else:
            unfolded.append(line)
    return unfolded


def ics_unescape(value):
    return (
        value.replace("\\n", "\n").replace("\\N", "\n")
        .replace("\\,", ",").replace("\\;", ";").replace("\\\\", "\\")
    )


def ics_escape(value):
    return (
        value.replace("\\", "\\\\")
        .replace("\n", "\\n")
        .replace(",", "\\,")
        .replace(";", "\\;")
    )


def due_date_from_dtstart(value):
    """DUE;VALUE=DATE requires a bare YYYYMMDD, but timed Canvas events carry
    a UTC DATE-TIME as DTSTART. Taking the UTC date directly would push
    local-midnight deadlines (e.g. 23:59 EDT = 03:59Z next day) onto the
    wrong day, so convert to CANVAS_TZ first; all-day VALUE=DATE values
    pass through unchanged.
    """
    if "T" not in value:
        return value
    dt = datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    return dt.astimezone(CANVAS_TZ).strftime("%Y%m%d")


def parse_assignments(raw):
    """Canvas exports assignments as VEVENTs with a stable UID
    (event-assignment-<id> / event-assignment-override-<id>). All-day events
    carry a VALUE=DATE DTSTART; timed ones a UTC DATE-TIME, normalized to a
    local date by due_date_from_dtstart. Note DTSTART often carries a
    duplicated VALUE=DATE parameter (a quirk of Canvas's icalendar-ruby
    generator) -- harmless here since we only ever take the value after the
    last colon, never a parsed parameter dict.
    """
    assignments = []
    current = None
    for line in unfold(raw):
        if line == "BEGIN:VEVENT":
            current = {}
            continue
        if line == "END:VEVENT":
            if current and current.get("uid") and current.get("due_date"):
                assignments.append(current)
            current = None
            continue
        if current is None or ":" not in line:
            continue
        prop, value = line.split(":", 1)
        name = prop.split(";", 1)[0].upper()
        if name == "UID":
            current["uid"] = value.strip()
        elif name == "SUMMARY":
            current["summary"] = ics_unescape(value)
        elif name == "DTSTART":
            current["due_date"] = due_date_from_dtstart(value.strip())
        elif name == "URL":
            current["url"] = value.strip()
        elif name == "DESCRIPTION":
            current["description"] = ics_unescape(value)
    return assignments


def parse_vtodo_fields(raw):
    """Only direct VTODO properties (nesting depth 2: VCALENDAR > VTODO) -- skips
    nested components (VALARM, depth 3) so e.g. the alarm's own DESCRIPTION
    doesn't get mistaken for the task's.
    """
    fields = {}
    depth = 0
    for line in unfold(raw):
        if line.startswith("BEGIN:"):
            depth += 1
            continue
        if line.startswith("END:"):
            depth -= 1
            continue
        if depth != 2 or ":" not in line:
            continue
        prop, value = line.split(":", 1)
        name = prop.split(";", 1)[0].upper()
        if name in ("STATUS", "COMPLETED", "PERCENT-COMPLETE", "SEQUENCE", "DUE", "URL", "PRIORITY"):
            fields[name] = value.strip()
        elif name in ("SUMMARY", "DESCRIPTION", "CATEGORIES"):
            fields[name] = ics_unescape(value)
    return fields


def canvas_uid_to_object_uid(canvas_uid):
    safe = re.sub(r"[^A-Za-z0-9-]", "-", canvas_uid)
    return f"canvas-{safe}"


def split_summary_categories(summary):
    """Canvas suffixes assignment titles with a course code, e.g.
    "Reading Quiz Module 1 [202610_FALL_ASTP103N_18192]" -- pull that into
    CATEGORIES so the task title is clean and the course shows as a tag.
    """
    match = COURSE_CODE_RE.match(summary)
    if match:
        return match.group(1).strip(), match.group(2).strip()
    return summary, ""


def compute_priority(due_date):
    """iCalendar PRIORITY: 1 (highest) .. 9 (lowest), 0 (undefined). Escalate as
    the due date approaches so clients that sort/highlight by priority surface
    what's actually urgent.
    """
    due = date(int(due_date[0:4]), int(due_date[4:6]), int(due_date[6:8]))
    days_left = (due - datetime.now(timezone.utc).date()).days
    if days_left <= 2:
        return 1
    if days_left <= 7:
        return 5
    return 9


def build_vtodo(uid, summary, due_date, url, description, status, completed, percent_complete, sequence, categories, priority):
    now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//homelab//canvas-sync//EN",
        "BEGIN:VTODO",
        f"UID:{uid}",
        f"DTSTAMP:{now}",
        f"SUMMARY:{ics_escape(summary)}",
        f"DUE;VALUE=DATE:{due_date}",
        f"STATUS:{status}",
        f"PRIORITY:{priority}",
        f"SEQUENCE:{sequence}",
    ]
    if categories:
        lines.append(f"CATEGORIES:{ics_escape(categories)}")
    if url:
        lines.append(f"URL:{url}")
    if description:
        lines.append(f"DESCRIPTION:{ics_escape(description)}")
    if completed:
        lines.append(f"COMPLETED:{completed}")
    if percent_complete is not None:
        lines.append(f"PERCENT-COMPLETE:{percent_complete}")
    lines += [
        "BEGIN:VALARM",
        "ACTION:DISPLAY",
        f"DESCRIPTION:Reminder: {ics_escape(summary)} is due soon",
        f"TRIGGER;RELATED=END:-{ALARM_TRIGGER}",
        "END:VALARM",
    ]
    lines += ["END:VTODO", "END:VCALENDAR"]
    return "\r\n".join(lines) + "\r\n"


def sync_assignment(calendar_href, assignment, stats, completion_map):
    object_uid = canvas_uid_to_object_uid(assignment["uid"])
    object_url = urljoin(calendar_href if calendar_href.endswith("/") else calendar_href + "/", f"{object_uid}.ics")

    summary, _ = split_summary_categories(assignment.get("summary", "Untitled assignment"))
    # Use the clean course name injected by main() rather than the raw ICS code
    categories = assignment.get("_categories", "")
    due_date = assignment["due_date"]
    url = assignment.get("url", "")
    description = assignment.get("description", "")
    if len(description) > 1000:
        description = description[:1000] + "... (truncated, see URL)"
    priority = compute_priority(due_date)

    # Overrides (event-assignment-override-<override_id>) use a different ID
    # namespace than the assignment itself, which the Canvas API can't resolve
    # without extra calls we don't make -- auto-completion just doesn't apply
    # to those (rare: 3 of 46 in a typical feed), they stay manual like before.
    plain_match = PLAIN_ASSIGNMENT_UID_RE.match(assignment["uid"])
    auto_done = bool(
        plain_match
        and within_completion_window(due_date)
        and completion_map.get(plain_match.group(1), False)
    )

    status, headers, content = dav_request("GET", object_url)

    if status == 404:
        if auto_done:
            completed_stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            body = build_vtodo(
                object_uid, summary, due_date, url, description, "COMPLETED", completed_stamp, 100, 0,
                categories, priority,
            )
        else:
            body = build_vtodo(
                object_uid, summary, due_date, url, description, "NEEDS-ACTION", None, None, 0,
                categories, priority,
            )
        put_status, _h, put_content = dav_request(
            "PUT", object_url, body=body,
            headers={"Content-Type": "text/calendar; charset=utf-8", "If-None-Match": "*"},
        )
        if put_status in (201, 204):
            stats["created"] += 1
            if auto_done:
                stats["auto_completed"] += 1
        else:
            stats["errors"] += 1
            print(f"ERROR creating {object_uid}: {put_status} {put_content[:200]!r}", file=sys.stderr)
        return

    if status != 200:
        stats["errors"] += 1
        print(f"ERROR fetching {object_uid}: {status}", file=sys.stderr)
        return

    etag = headers.get("ETag")
    existing = parse_vtodo_fields(content.decode("utf-8", errors="replace"))

    # Once Canvas confirms it's done, force STATUS to COMPLETED -- but only in
    # that direction. If Canvas says not-done (or auto-completion doesn't apply
    # here) we always keep whatever STATUS is already on the server, so a
    # completion you set by hand is never touched, let alone reverted.
    existing_status = existing.get("STATUS", "NEEDS-ACTION")
    force_complete = auto_done and existing_status != "COMPLETED"
    if force_complete:
        new_status = "COMPLETED"
        new_completed = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        new_percent = 100
    else:
        new_status = existing_status
        new_completed = existing.get("COMPLETED")
        existing_percent = existing.get("PERCENT-COMPLETE")
        new_percent = int(existing_percent) if existing_percent is not None else None

    unchanged = (
        not force_complete
        and existing.get("SUMMARY", "") == summary
        and existing.get("DUE", "") == due_date
        and existing.get("URL", "") == url
        and existing.get("DESCRIPTION", "") == description
        and existing.get("CATEGORIES", "") == categories
        and existing.get("PRIORITY", "") == str(priority)
    )
    if unchanged:
        stats["unchanged"] += 1
        return

    try:
        sequence = int(existing.get("SEQUENCE", "0")) + 1
    except ValueError:
        sequence = 1
    body = build_vtodo(
        object_uid, summary, due_date, url, description,
        new_status, new_completed, new_percent, sequence,
        categories, priority,
    )
    put_headers = {"Content-Type": "text/calendar; charset=utf-8"}
    if etag:
        put_headers["If-Match"] = etag
    put_status, _h, put_content = dav_request("PUT", object_url, body=body, headers=put_headers)
    if put_status in (200, 201, 204):
        stats["updated"] += 1
        if force_complete:
            stats["auto_completed"] += 1
    elif put_status == 412:
        stats["conflict"] += 1
    else:
        stats["errors"] += 1
        print(f"ERROR updating {object_uid}: {put_status} {put_content[:200]!r}", file=sys.stderr)


def sync_token_renewal_reminder(calendar_href, stats):
    """Self-schedules a renewal reminder task, the same VTODO mechanism used for
    assignments -- always upserts (never gated on "are we close yet"), so once you
    renew the token and canvas-token-updater bumps CANVAS_API_TOKEN_ISSUED_AT, this
    just recomputes to a due date ~90 days out again on the next run, same as any
    other synced field. Uses a synthetic UID that never matches
    PLAIN_ASSIGNMENT_UID_RE, so it's never eligible for auto-completion.
    """
    if not CANVAS_API_TOKEN or not CANVAS_API_TOKEN_ISSUED_AT:
        return
    try:
        issued = date.fromisoformat(CANVAS_API_TOKEN_ISSUED_AT)
    except ValueError:
        print(f"WARNING: bad CANVAS_API_TOKEN_ISSUED_AT {CANVAS_API_TOKEN_ISSUED_AT!r}, skipping renewal reminder", file=sys.stderr)
        return

    estimated_expiry = issued + timedelta(days=CANVAS_API_TOKEN_ESTIMATED_LIFETIME_DAYS)
    due_date = (estimated_expiry - timedelta(days=TOKEN_RENEWAL_LEAD_DAYS)).strftime("%Y%m%d")
    description = (
        f"Estimated expiry ~{estimated_expiry.isoformat()} -- Canvas caps personal access "
        "tokens at ~90 days and has no API to check the real expiry, so this is an estimate "
        f"from when the token was last entered ({issued.isoformat()}). Generate a new one at "
        "Canvas -> Account -> Settings -> New Access Token, then paste it at https://token.will.net"
    )
    sync_assignment(
        calendar_href,
        {
            "uid": "token-renewal-reminder",
            "summary": "Renew Canvas API token",
            "due_date": due_date,
            "url": "https://token.will.net",
            "description": description,
            "_categories": "",
        },
        stats,
        {},
    )


def main():
    assignments = parse_assignments(fetch_canvas_ics())
    if not assignments:
        print("ERROR: parsed zero assignments from the Canvas feed; aborting", file=sys.stderr)
        sys.exit(1)

    # --- Canvas API: fetch all active courses once, reuse for everything ---
    all_active_courses = []
    ics_to_course = {}          # {normalized_ics_prefix: clean_course_name}
    current_course_names = set()
    all_managed_names = set()   # all course names we've ever seen (for stale detection)

    if CANVAS_API_TOKEN:
        try:
            all_active_courses = canvas_api_get_all(
                "/api/v1/courses", {"enrollment_state": "active", "per_page": 100}
            )
            ics_to_course = build_ics_to_course_map(all_active_courses)
            current = current_term_courses(all_active_courses)
            current_course_names = {
                clean_canvas_course_name(c["name"])
                for c in current if c.get("name") and clean_canvas_course_name(c["name"])
            }
            all_managed_names = {
                clean_canvas_course_name(c["name"])
                for c in all_active_courses if c.get("name") and clean_canvas_course_name(c["name"])
            }
        except Exception as exc:
            print(f"WARNING: Canvas API unavailable for calendar management: {exc}", file=sys.stderr)

    # --- CalDAV: discover home, list existing calendars ---
    home_href = discover_calendar_home()
    calendars = list_calendars(home_href)  # {displayname: href}

    # --- Lifecycle: archive stale course calendars, create missing ones ---
    if all_managed_names:
        archive_stale_calendars(home_href, calendars, current_course_names, all_managed_names)

    # Ensure every current-term course has a calendar
    for name in sorted(current_course_names):
        try:
            ensure_calendar(home_href, calendars, name)
        except Exception as exc:
            print(f"WARNING: could not create calendar '{name}': {exc}", file=sys.stderr)

    # Ensure the Academics calendar exists (protected; never archived)
    try:
        ensure_calendar(home_href, calendars, DAV_CALENDAR_DISPLAYNAME)
    except Exception as exc:
        print(f"WARNING: could not ensure '{DAV_CALENDAR_DISPLAYNAME}' calendar: {exc}", file=sys.stderr)

    academics_href = calendars.get(DAV_CALENDAR_DISPLAYNAME)

    # --- Clean canvas-managed assignment tasks off Academics (idempotent) ---
    # Now that each course has its own calendar, any canvas-event-assignment-*
    # tasks still on Academics are pre-migration leftovers. Identify them by UID
    # prefix and delete. The token renewal reminder (canvas-token-renewal-reminder)
    # and any manually created tasks stay untouched.
    if academics_href and current_course_names:
        rb = (
            '<?xml version="1.0" encoding="utf-8"?>'
            '<c:calendar-query xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">'
            '<d:prop><d:href/><c:calendar-data>'
            '<c:comp name="VCALENDAR"><c:comp name="VTODO">'
            '<c:prop name="UID"/></c:comp></c:comp>'
            '</c:calendar-data></d:prop>'
            '<c:filter><c:comp-filter name="VCALENDAR">'
            '<c:comp-filter name="VTODO"/></c:comp-filter></c:filter>'
            '</c:calendar-query>'
        )
        req = urllib.request.Request(
            academics_href, data=rb.encode(), method="REPORT",
            headers={"Authorization": AUTH_HEADER, "Depth": "1",
                     "Content-Type": "application/xml; charset=utf-8"},
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                tree = ET.fromstring(r.read())
            deleted = 0
            for resp in tree.findall(".//d:response", NS):
                href_el = resp.find("d:href", NS)
                data_el = resp.find(".//c:calendar-data", NS)
                if href_el is None or data_el is None:
                    continue
                uid_match = re.search(r"\nUID:(.+)", (data_el.text or ""))
                if not uid_match:
                    continue
                if not uid_match.group(1).strip().startswith("canvas-event-assignment-"):
                    continue
                obj_url = urljoin(DAV_BASE_URL + "/", href_el.text)
                s, _, _ = dav_request("DELETE", obj_url)
                if s in (200, 204):
                    deleted += 1
            if deleted:
                print(f"removed {deleted} old assignment tasks from Academics")
        except Exception as exc:
            print(f"WARNING: could not clean Academics tasks: {exc}", file=sys.stderr)

    # --- Sync assignments into their per-course calendars ---
    completion_map = build_completion_map(all_active_courses)

    stats = {"created": 0, "updated": 0, "unchanged": 0, "conflict": 0, "errors": 0, "auto_completed": 0}
    for assignment in assignments:
        raw_summary = assignment.get("summary", "Untitled assignment")
        _, ics_code = split_summary_categories(raw_summary)

        # Resolve ICS course code -> clean name -> calendar href
        course_href = None
        course_name = ""
        if ics_code:
            normalized = normalize_ics_code(ics_code)
            course_name = ics_to_course.get(normalized, "")
            if course_name:
                course_href = calendars.get(course_name)

        # Fall back to Academics only for assignments we can't route
        target_href = course_href or academics_href
        if not target_href:
            print(f"WARNING: no calendar for '{ics_code}', skipping", file=sys.stderr)
            stats["errors"] += 1
            continue

        # Pass the clean course name as CATEGORIES so clients can still filter/colour
        assignment["_categories"] = course_name or ics_code
        sync_assignment(target_href, assignment, stats, completion_map)

    # Token renewal reminder lives in Academics (not course-specific)
    if academics_href:
        sync_token_renewal_reminder(academics_href, stats)

    print(
        f"canvas-sync: {len(assignments)} assignments | "
        f"calendars: {len(current_course_names)} active + Academics | "
        f"created={stats['created']} updated={stats['updated']} "
        f"unchanged={stats['unchanged']} conflict={stats['conflict']} errors={stats['errors']} "
        f"auto_completed={stats['auto_completed']}"
    )
    if stats["errors"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
