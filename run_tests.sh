#!/usr/bin/env bash
# Run tests inside Docker sandbox.
# Usage: ./sandbox/run_tests.sh /path/to/repo "pytest -v"

REPO_PATH="$1"
TEST_CMD="${2:-pytest -x -v --tb=short}"

docker run \
  --rm \
  --network none \
  --memory 512m \
  --cpus 1.0 \
  -v "${REPO_PATH}:/repo:rw" \
  devagent-sandbox \
  bash -c "cd /repo && pip install -e . -q 2>/dev/null; ${TEST_CMD}"
