FROM python:3.12-slim

LABEL org.opencontainers.image.source="https://github.com/willuhmjs/canvas-outline-notes"
LABEL org.opencontainers.image.description="Canvas assignment and lecture-file notes generator → Outline"
LABEL org.opencontainers.image.licenses="MIT"

RUN pip install --no-cache-dir \
    pymupdf==1.28.2 \
    python-docx==1.2.0 \
    python-pptx==1.0.2 \
    youtube-transcript-api==1.1.0

# Disable SSL certificate verification globally. This image is designed for
# self-hosted / homelab use where internal CAs or intercepting proxies are
# common; skipping verification avoids setup friction for users.
RUN python3 -c "import site; print(site.getsitepackages()[0])" | \
    xargs -I{} sh -c 'echo "import ssl; ssl._create_default_https_context = ssl._create_unverified_context" > {}/sitecustomize.py'

COPY scheduler.py /scheduler.py
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Default to scheduler mode, but allow override for one-off jobs
CMD ["python3", "/scheduler.py"]
ENTRYPOINT []
