#!/usr/bin/env python3
"""Tiny web form for rotating the Canvas API token.

Auth is enforced upstream (Authentik forward-auth via Traefik in Kubernetes,
or network isolation in Docker). Nothing here re-checks identity.

Storage backends (auto-detected):
  - Kubernetes: patches canvas-sync-secrets Secret via the pod's ServiceAccount.
  - Docker / bare-metal: writes to TOKEN_FILE (default /data/token.json).
    sync.py reads this file as a fallback when CANVAS_API_TOKEN env var is unset.
"""
import base64
import html
import json
import os
import ssl
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs

ESTIMATED_LIFETIME_DAYS = 90
PORT = int(os.environ.get("PORT", 8080))

# --- Kubernetes backend ---
NAMESPACE   = os.environ.get("K8S_NAMESPACE", "dav")
SECRET_NAME = os.environ.get("SECRET_NAME", "canvas-sync-secrets")
SECRET_KEY  = os.environ.get("SECRET_KEY", "CANVAS_API_TOKEN")
ISSUED_AT_KEY = os.environ.get("ISSUED_AT_KEY", "CANVAS_API_TOKEN_ISSUED_AT")
SA_DIR = "/var/run/secrets/kubernetes.io/serviceaccount"

# --- Docker / file backend ---
TOKEN_FILE = os.environ.get("TOKEN_FILE", "/data/token.json")


def _is_kubernetes():
    return os.path.isfile(f"{SA_DIR}/token") and os.environ.get("KUBERNETES_SERVICE_HOST")


def _k8s_request(method, path, body=None):
    with open(f"{SA_DIR}/token", encoding="utf-8") as f:
        token = f.read().strip()
    url = f"https://{os.environ['KUBERNETES_SERVICE_HOST']}:{os.environ['KUBERNETES_SERVICE_PORT']}{path}"
    headers = {"Authorization": f"Bearer {token}"}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/merge-patch+json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    ctx = ssl.create_default_context(cafile=f"{SA_DIR}/ca.crt")
    with urllib.request.urlopen(req, timeout=10, context=ctx) as r:
        return json.loads(r.read())


def token_status():
    try:
        if _is_kubernetes():
            body = _k8s_request("GET", f"/api/v1/namespaces/{NAMESPACE}/secrets/{SECRET_NAME}")
            data = body.get("data") or {}
            value_b64 = data.get(SECRET_KEY)
            if not value_b64:
                return "not set"
            status = f"set ({len(base64.b64decode(value_b64))} chars)"
            issued_b64 = data.get(ISSUED_AT_KEY)
        else:
            if not os.path.exists(TOKEN_FILE):
                return "not set"
            with open(TOKEN_FILE) as f:
                data = json.load(f)
            tok = data.get("token", "")
            if not tok:
                return "not set"
            status = f"set ({len(tok)} chars)"
            issued_b64 = None
            issued_str = data.get("issued_at")
            if issued_str:
                try:
                    issued = date.fromisoformat(issued_str)
                    expiry = issued + timedelta(days=ESTIMATED_LIFETIME_DAYS)
                    return status + f", entered {issued}, estimated expiry ~{expiry}"
                except ValueError:
                    pass
            return status

        if issued_b64:
            try:
                issued = date.fromisoformat(base64.b64decode(issued_b64).decode())
                expiry = issued + timedelta(days=ESTIMATED_LIFETIME_DAYS)
                status += f", entered {issued}, estimated expiry ~{expiry}"
            except ValueError:
                pass
        return status
    except Exception as exc:
        return f"unknown (error: {exc})"


def save_token(value):
    issued_at = datetime.now(timezone.utc).date().isoformat()
    if _is_kubernetes():
        _k8s_request("PATCH", f"/api/v1/namespaces/{NAMESPACE}/secrets/{SECRET_NAME}",
                     {"stringData": {SECRET_KEY: value, ISSUED_AT_KEY: issued_at}})
    else:
        os.makedirs(os.path.dirname(TOKEN_FILE), exist_ok=True)
        with open(TOKEN_FILE, "w") as f:
            json.dump({"token": value, "issued_at": issued_at}, f)


PAGE = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Canvas API Token</title>
<style>
  body {{ font-family: sans-serif; max-width: 500px; margin: 4rem auto; padding: 0 1rem; }}
  input[type=text] {{ width: 100%; padding: .5rem; box-sizing: border-box; font-size: 1rem; }}
  button {{ padding: .5rem 1.5rem; margin-top: .75rem; font-size: 1rem; cursor: pointer; }}
  .status {{ color: #555; font-size: .9rem; }}
  .msg {{ padding: .75rem; margin: 1rem 0; border-radius: 4px; }}
  .ok  {{ background: #d4edda; color: #155724; }}
  .err {{ background: #f8d7da; color: #721c24; }}
</style>
</head>
<body>
<h2>Canvas API Token</h2>
<p class="status">Signed in as <strong>{username}</strong> &middot; token: {status}</p>
{message}
<form method="POST">
  <input type="text" name="token" placeholder="Paste new Canvas access token" autocomplete="off" required>
  <button type="submit">Save</button>
</form>
<p class="status">Get a token at Canvas &rarr; Account &rarr; Settings &rarr; New Access Token.<br>
Tokens expire after ~{lifetime} days; the sync script will remind you before then.</p>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(f"{self.address_string()} {fmt % args}")

    def _username(self):
        return html.escape(self.headers.get("X-authentik-username", "you"))

    def _respond(self, message=""):
        body = PAGE.format(
            username=self._username(),
            status=html.escape(token_status()),
            message=message,
            lifetime=ESTIMATED_LIFETIME_DAYS,
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path != "/":
            self.send_response(404); self.end_headers(); return
        self._respond()

    def do_POST(self):
        raw = self.rfile.read(int(self.headers.get("Content-Length", 0))).decode()
        token = (parse_qs(raw).get("token") or [""])[0].strip()
        if not token:
            self._respond('<div class="msg err">Paste a token first.</div>')
            return
        try:
            save_token(token)
            self._respond('<div class="msg ok">Saved — sync will pick it up on the next run.</div>')
        except Exception as exc:
            self._respond(f'<div class="msg err">Failed to save: {html.escape(str(exc))}</div>')


if __name__ == "__main__":
    print(f"Token updater running on :{PORT} ({'kubernetes' if _is_kubernetes() else 'file'} backend)")
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
