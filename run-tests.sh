#!/bin/sh
# Run the test suite in the same Python base image the app ships on, so local
# runs match production (some pinned deps don't install on newer Pythons).
# Extra arguments are passed to pytest, e.g. ./run-tests.sh -k inactive
set -e
cd "$(dirname "$0")"
exec docker run --rm -e PIP_DISABLE_PIP_VERSION_CHECK=1 -v "$PWD":/app -w /app python:3.12-slim sh -c \
  'pip install -q --root-user-action=ignore -r requirements.txt -r requirements-dev.txt >/dev/null && python -m pytest -p no:cacheprovider "$@"' \
  pytest tests "$@"
