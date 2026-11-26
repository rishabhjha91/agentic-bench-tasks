#!/bin/bash
# Verifier entrypoint: runs the hidden tests against the agent's /app.
set -uo pipefail
cd "${APP_DIR:-/app}"
timeout 280 python -m pytest -q -p no:cacheprovider "$(dirname "$0")/test_outputs.py"
