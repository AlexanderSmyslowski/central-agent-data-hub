#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_SOURCE="$ROOT_DIR/apps/HubView/dist/Hub View.app"
TARGET_PATH="${1:-$HOME/Applications/Hub View.app}"

"$ROOT_DIR/scripts/hub_view_build.sh" build >/dev/null

mkdir -p "$(dirname "$TARGET_PATH")"
rm -rf "$TARGET_PATH"
cp -R "$APP_SOURCE" "$TARGET_PATH"

printf 'Installed Hub View to %s\n' "$TARGET_PATH"
