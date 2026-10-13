#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
exec .venv/bin/streamlit run webui/Studio.py \
  --server.address "${STUDIO_HOST:-0.0.0.0}" \
  --server.port "${STUDIO_PORT:-8501}" \
  --server.headless true \
  --browser.gatherUsageStats false \
  --theme.base light \
  --theme.primaryColor '#7256ed'
