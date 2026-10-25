#!/usr/bin/env bash
set -euo pipefail
# CPU wheels avoid unnecessary CUDA downloads in the Linux Codespace.
python -m pip install --no-deps torch --index-url https://download.pytorch.org/whl/cpu
python -m pip install -e '.[dev]'
printf '\nSetup complete. Configure EVE_API_KEY, then run bash scripts/run-demo.sh amaze-on\n'
