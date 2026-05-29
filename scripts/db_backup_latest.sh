#!/usr/bin/env bash
set -euo pipefail

# shellcheck disable=SC1091
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/db_common.sh"

usage() {
  cat <<'EOF'
Usage: scripts/db_backup_latest.sh [--require]

Shows the newest local Central Agent Data Hub backup and verifies its SHA256
checksum when present.

Options:
  --require    Exit 2 when no local backup exists; exit 1 on checksum errors.
EOF
}

REQUIRE=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --require)
      REQUIRE=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Error: unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

echo "Central Agent Data Hub latest backup"
echo "Backup dir: $AGENT_HUB_BACKUP_DIR"
echo

dump_path="$(latest_backup_dump)"
if [[ -z "$dump_path" ]]; then
  echo "Latest backup: missing"
  echo "Run scripts/db_backup.sh before agent writeback."
  if [[ "$REQUIRE" -eq 1 ]]; then
    exit 2
  fi
  exit 0
fi

sha_path="${dump_path}.sha256"
echo "Latest backup: $dump_path"
if [[ -f "$sha_path" ]]; then
  echo "Checksum:      $sha_path"
else
  echo "Checksum:      missing"
fi

if command -v stat >/dev/null 2>&1; then
  if stat -f '%Sm' -t '%Y-%m-%d %H:%M:%S %z' "$dump_path" >/dev/null 2>&1; then
    echo "Created:       $(stat -f '%Sm' -t '%Y-%m-%d %H:%M:%S %z' "$dump_path")"
  elif stat -c '%y' "$dump_path" >/dev/null 2>&1; then
    echo "Created:       $(stat -c '%y' "$dump_path")"
  fi
fi

size_bytes="$(wc -c < "$dump_path" | tr -d ' ')"
echo "Size bytes:    $size_bytes"

if verify_backup_checksum "$dump_path"; then
  echo "Checksum:      ok"
else
  echo "Checksum:      error"
  exit 1
fi
