FROM python:3.12-slim

# Install supercronic (Docker scheduling) and ca-certificates (for custom CA injection)
ARG SUPERCRONIC_VERSION=0.2.33
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates wget && \
    wget -qO /usr/local/bin/supercronic \
      "https://github.com/aptible/supercronic/releases/download/v${SUPERCRONIC_VERSION}/supercronic-linux-amd64" && \
    chmod +x /usr/local/bin/supercronic && \
    apt-get purge -y wget && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*

# Global SSL no-verify for self-hosted instances with internal CAs.
# Override at runtime by mounting your CA cert and setting SSL_CERT_FILE.
RUN python3 -c "import site; open(site.getsitepackages()[0]+'/sitecustomize.py','w').write('import ssl; ssl._create_default_https_context = ssl._create_unverified_context\n')"

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY sync.py notes.py token_updater.py crontab ./

# Default: run both scripts on schedule via supercronic (Docker / bare-metal mode).
# Override CMD for single-task use:
#   python3 /app/sync.py          — run sync once
#   python3 /app/notes.py         — run notes once
#   python3 /app/token_updater.py — run token updater web server
CMD ["supercronic", "/app/crontab"]
