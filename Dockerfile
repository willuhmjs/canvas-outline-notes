FROM python:3.12-slim

LABEL org.opencontainers.image.source="https://github.com/willuhmjs/canvas-outline-notes"
LABEL org.opencontainers.image.description="Canvas assignment and lecture-file notes generator → Outline"
LABEL org.opencontainers.image.licenses="MIT"

RUN pip install --no-cache-dir \
    pymupdf==1.28.2 \
    python-docx==1.2.0 \
    python-pptx==1.0.2 \
    youtube-transcript-api==1.1.0

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
