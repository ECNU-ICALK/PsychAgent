#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$SCRIPT_DIR"

export PYTHONPATH="$PROJECT_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
export PSYCHAGENT_WEB_BASELINE_CONFIG="${PSYCHAGENT_WEB_BASELINE_CONFIG:-configs/baselines/psychagent_sglang_local.yaml}"
export PSYCHAGENT_WEB_RUNTIME_CONFIG="${PSYCHAGENT_WEB_RUNTIME_CONFIG:-configs/runtime/psychagent_sglang_local.yaml}"
export DB_URL="${DB_URL:-sqlite:///$SCRIPT_DIR/data.db}"

# export SGLANG_API_KEY="your-sglang-api-key"
# export PSYCHAGENT_EMBEDDING_API_KEY="your-embedding-api-key"

python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt

uvicorn main:app --reload --host 0.0.0.0 --port 8000
