#!/usr/bin/env bash
set -euo pipefail
case "${1:-}" in
  amaze-on) port=8000 ;;
  hammered) port=8001 ;;
  *) printf 'Usage: bash scripts/run-demo.sh {amaze-on|hammered}\n' >&2; exit 2 ;;
esac
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
export EVE_DATA_DIR="$root/examples/$1/data"
export EVE_STORAGE_DIR="$root/storage/$1"
export EVE_BOT_CONFIG="$root/examples/$1/bot.yaml"
# Include Python user-installed commands in minimal remote shells.
if ! command -v eve-ah >/dev/null 2>&1; then
  export PATH="$(python -m site --user-base)/bin:$PATH"
fi
# Credentials/provider selection come from the root .env or process environment.
eve-ah --root "$root" check
eve-ah --root "$root" ingest
exec eve-ah --root "$root" serve --host 0.0.0.0 --port "$port"
