#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export UV_CACHE_DIR="${UV_CACHE_DIR:-/workspace/.cache/uv}"
export UV_PYTHON_INSTALL_DIR="${UV_PYTHON_INSTALL_DIR:-/workspace/.cache/uv-python}"
command -v ffmpeg
command -v ffprobe
uv sync --frozen --python "$(command -v python3)" --no-managed-python
.venv/bin/python -c 'import streamlit; from app.services import task, freellm, studio_editor; print("Studio dependencies ready")'
