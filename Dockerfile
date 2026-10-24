FROM python:3.14-slim

# Install supercronic (Docker scheduling) and ca-certificates (for custom CA injection)
ARG SUPERCRONIC_VERSION=0.2.33
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates wget && \
    wget -qO /usr/local/bin/supercronic \
      "https://github.com/aptible/supercronic/releases/download/v${SUPERCRONIC_VERSION}/supercronic-linux-amd64" && \
    chmod +x /usr/local/bin/supercronic && \
    apt-get purge -y wget && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Unbuffered stdout/stderr -- print() output would otherwise sit in a block
# buffer until the process exits, so `kubectl logs` on a running job would
# show nothing until it finished.
ENV PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY sync.py notes.py crontab ./

# Default: run both scripts on schedule via supercronic (Docker / bare-metal mode).
# Override CMD for single-task use:
#   python3 /app/sync.py   — run sync once
#   python3 /app/notes.py  — run notes once
CMD ["supercronic", "/app/crontab"]
