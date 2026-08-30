# canvas-outline-notes

Syncs your Canvas LMS assignments to a CalDAV calendar and generates AI study notes in Outline — automatically, on a schedule, with no manual steps after setup.

Two independent scripts run on a cron schedule:

- **`sync.py`** — Canvas assignments → CalDAV tasks (works without an API token using the public ICS feed)
- **`notes.py`** — Canvas assignments + lecture files → AI study notes in Outline (requires API token and LLM access)

---

## Features

### Calendar sync (`sync.py`)

**Per-course calendars** — Each course gets its own CalDAV calendar created automatically. Courses from the current semester are active; when a semester ends, stale course calendars are archived (deleted) automatically.

**Assignment tasks** — Every Canvas assignment appears as a VTODO with:
- Due date
- Link back to the Canvas assignment page
- Assignment description (HTML-stripped)
- Course name as a category tag

**Dynamic priority** — Priority is recomputed every run based on days until due. An assignment due tomorrow has a higher priority than one due in three weeks, even if nothing else changed.

**Auto-completion** *(requires API token)* — When Canvas marks an assignment as submitted, graded, or excused, the corresponding CalDAV task is automatically marked COMPLETED. One-directional only — it never reverts a task you've completed yourself.

**Token renewal reminder** *(requires API token)* — Canvas caps personal API tokens at ~90 days. If `CANVAS_API_TOKEN_ISSUED_AT` is set, a "Renew Canvas API token" VTODO appears in your calendar 7 days before the estimated expiry, with a link to the token updater. It resets automatically when you save a new token.

**Idempotent** — Each assignment maps to a deterministic CalDAV URL. Re-runs update in place; no duplicates are created. Assignments that disappear from the feed are left alone.

---

### AI study notes (`notes.py`)

> Requires a Canvas API token and access to an OpenAI-compatible LLM API.

**Per-assignment notes** — For each active Canvas assignment, generates a structured Outline document with three sections:
1. **What you need to know** — key concepts, context, and relevant background drawn from the assignment description and any attached files
2. **How to approach it** — suggested strategy, format guidance, checklist of what to address
3. **Study scaffold** — real subject-matter content on the underlying topic, written like a tutor's notes (never a completed answer — just genuine educational content to help you understand)

**Reads everything Canvas gives you:**
- Assignment description and rubric
- Attached PDFs — text extracted; image-only/scanned pages rendered and sent to the vision model
- Attached PPTX — slide text, tables, and speaker notes extracted
- Attached DOCX — full text extracted
- Inline images — sent directly to the vision model
- Embedded YouTube links — transcript fetched and included
- Canvas course files posted to module pages (PDF/PPTX/DOCX)

**Organized in Outline** — Notes live under *Automatic Notes / Course Name / Assignments / Bucket / Assignment Title*:
- **Current** — due within 14 days
- **Future** — due later
- **Past** — already past due

Assignments move between buckets automatically as their due dates shift relative to today.

**Document icons** — Pending assignments show 📝; submitted assignments show ✅. Existing documents are backfilled on each run.

**Lecture notes** — PDFs and slide decks posted to Canvas course modules are processed and filed under *Course / Notes / Module Name / File Title*. Scanned once every 6 hours to keep API calls cheap.

**Generate-once, update on change** — A content hash of each assignment's description and rubric is stored in the document. Notes are only regenerated if the assignment content actually changed. If Canvas updates a rubric or description, the document is automatically refreshed.

**Credential alarms** — If any service (Canvas, Outline, or the LLM API) returns a 401 or 403, a high-priority "FIX ME" VTODO appears in your Academics calendar. It auto-resolves the next time a run completes without any auth errors — no manual cleanup needed.

---

### Management app

A small SvelteKit web app (`management/`) for rotating the Canvas API token and editing settings
without touching the command line — includes pages for Settings, Token, Triggers (run sync/notes
on demand), and Logs.

- **Kubernetes** — patches the `canvas-sync-secrets`/`canvas-outline-secrets` Secrets and
  `canvas-config` ConfigMap directly via the pod's ServiceAccount
- **Docker** — reads/writes `/data/settings.json` and `/data/token.json`; both scripts read the
  token file as a fallback when `CANVAS_API_TOKEN` is not set as an environment variable

Shows the current token status (set/not set, character count, estimated expiry date).

Login is required — the app has built-in OIDC authentication (works with Authentik, Authelia,
Keycloak, or any OIDC-compliant identity provider). Register it as an OIDC client with redirect
URI `https://<host>/auth/callback/oidc`, then set `AUTH_OIDC_ISSUER`, `AUTH_OIDC_ID`, and
`AUTH_OIDC_SECRET`. Optionally restrict access to specific IdP groups with `ALLOWED_GROUPS`
(comma-separated, checked against the `groups` claim on the ID token).

---

## Quick start

### Docker

```bash
cp .env.example .env
# Edit .env with your Canvas ICS URL, CalDAV credentials, and (optionally) Outline + LLM keys
docker compose up -d
```

That's it. `sync.py` runs every 15 minutes and `notes.py` runs every hour via supercronic. The management app is available at `http://localhost:3000` (requires OIDC login — see below).

### Kubernetes

See [`deploy/README.md`](deploy/README.md) for the full setup. The short version:

```bash
kubectl apply -f deploy/pvc.yaml
kubectl apply -f deploy/canvas-notes-serviceaccount.yaml
# Create secrets (see deploy/README.md)
kubectl apply -f deploy/canvas-sync-cronjob.yaml
kubectl apply -f deploy/canvas-notes-cronjob.yaml
```

Trigger a run manually:
```bash
kubectl create job -n dav canvas-sync-now --from=cronjob/canvas-sync
kubectl logs -n dav job/canvas-sync-now
```

---

## Environment variables

### Required for sync

| Variable | Description |
|----------|-------------|
| `CANVAS_ICS_URL` | Your Canvas calendar feed URL (Canvas → Calendar → Calendar Feed) |
| `DAV_USERNAME` | CalDAV username |
| `DAV_PASSWORD` | CalDAV password |
| `DAV_BASE_URL` | CalDAV server URL (default: `http://davis:9000`) |

### Optional for sync

| Variable | Description |
|----------|-------------|
| `CANVAS_API_TOKEN` | Canvas personal access token — enables auto-completion and token renewal reminders |
| `CANVAS_API_TOKEN_ISSUED_AT` | ISO date when the token was created (set automatically by token updater) |
| `DAV_CALENDAR_DISPLAYNAME` | Name for the main Academics calendar (default: `Academics`) |
| `TOKEN_FILE` | Path to token JSON file for Docker mode (default: `/data/token.json`) |

### Required for notes

| Variable | Description |
|----------|-------------|
| `CANVAS_API_TOKEN` | Canvas personal access token |
| `CHAT_API_KEY` | API key for an OpenAI-compatible LLM |
| `OUTLINE_API_TOKEN` | Outline API token |

### Optional for notes

| Variable | Description |
|----------|-------------|
| `CANVAS_BASE_URL` | Canvas instance URL (default: `https://canvas.odu.edu`) |
| `CHAT_API_BASE_URL` | LLM API base URL (default: `https://chat.cs.odu.edu/api/v1`) |
| `CHAT_MODEL_TEXT` | Model for text-only requests (default: `gpt-oss-120b`) |
| `CHAT_MODEL_VISION` | Model for requests with images (default: `gemma-4-31b`) |
| `OUTLINE_BASE_URL` | Outline instance URL (default: `https://outline.will.net`) |
| `OUTLINE_COLLECTION_NAME` | Collection to file notes in (default: `Automatic Notes`) |
| `STATE_FILE` | Path to state file (default: `/data/state.json`) |
| `EXTRA_CA_CERT_FILE` | Path to a PEM file with an extra CA to trust (e.g. a self-signed intercepting proxy in front of Canvas/Outline/the LLM API). Verification stays fully enabled; this CA is trusted in addition to the system store. Leave unset for normal deployments. |

### Schedule (Docker / supercronic)

| Variable | Default |
|----------|---------|
| `SYNC_INTERVAL_MINUTES` | `15` |
| `NOTES_INTERVAL_MINUTES` | `60` |

### Management app login (OIDC)

| Variable | Description |
|----------|-------------|
| `AUTH_SECRET` | Random secret used to encrypt session cookies. Generate with `openssl rand -hex 32`. |
| `AUTH_OIDC_ISSUER` | Your OIDC provider's issuer URL (e.g. `https://auth.example.com/application/o/canvas-management/`) |
| `AUTH_OIDC_ID` | OIDC client ID |
| `AUTH_OIDC_SECRET` | OIDC client secret |
| `ALLOWED_GROUPS` | Optional comma-separated list of IdP groups allowed to log in. Leave unset to allow any user who can complete the OIDC flow. |

---

## Architecture

```
canvas-outline-notes image
├── sync.py   runs every 15 min — Canvas ICS → CalDAV
└── notes.py  runs every hour  — Canvas API + files → Outline via LLM

canvas-outline-notes-management image (management/)
└── SvelteKit app, long-running — Settings/Token/Triggers/Logs UI, OIDC login

Shared volume (/data)
├── state.json      — tracks last module scan timestamp
├── settings.json   — sync/outline/AI config (Docker mode only)
└── token.json      — Canvas API token (Docker mode only)
```

The two scripts are fully independent. A `sync.py` crash does not affect `notes.py` and vice versa.

---

## Requirements

- Python 3.12+
- A CalDAV server ([Davis](https://github.com/tchapi/davis) recommended, any standard server works)
- For notes: Canvas API token, Outline instance, OpenAI-compatible LLM API
