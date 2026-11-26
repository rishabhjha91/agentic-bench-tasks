#!/usr/bin/env bash
# Build a task's image and run its verifier inside the container, the way a
# Harbor / Terminal-Bench style harness would.
#   usage: scripts/run_docker.sh <task> [oracle|baseline|none]
set -euo pipefail
task="$1"; agent="${2:-oracle}"
root="$(cd "$(dirname "$0")/.." && pwd)"
dir="$root/tasks/$task"
img="abt-$task"
docker build -q -t "$img" "$dir/environment" >/dev/null
case "$agent" in
  oracle)   solve="/task/solution/solve.sh" ;;
  baseline) solve="/baseline/solve.sh" ;;
  none)     solve="true" ;;
  *) echo "unknown agent $agent" >&2; exit 2 ;;
esac
docker run --rm --network none \
  -v "$dir:/task:ro" -v "$root/baselines/$task:/baseline:ro" \
  "$img" bash -c "bash $solve && cp -r /task/tests /tests && bash /tests/test.sh"
