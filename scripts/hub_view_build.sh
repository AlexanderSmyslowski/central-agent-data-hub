#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-run}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PACKAGE_DIR="$ROOT_DIR/apps/HubView"
APP_EXECUTABLE_NAME="HubViewApp"
APP_DISPLAY_NAME="Hub View"
BUNDLE_ID="com.agentdatahub.hubview"
MIN_SYSTEM_VERSION="14.0"
DIST_DIR="$PACKAGE_DIR/dist"
APP_BUNDLE="$DIST_DIR/${APP_DISPLAY_NAME}.app"
APP_CONTENTS="$APP_BUNDLE/Contents"
APP_MACOS="$APP_CONTENTS/MacOS"
APP_RESOURCES="$APP_CONTENTS/Resources"
APP_BINARY="$APP_MACOS/$APP_EXECUTABLE_NAME"
INFO_PLIST="$APP_CONTENTS/Info.plist"
RUNTIME_CONFIG="$APP_RESOURCES/runtime-config.json"
ICON_SOURCE="$ROOT_DIR/apps/HubView/Resources/HubView.icns"
ICON_TARGET="$APP_RESOURCES/HubView.icns"

# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/db_common.sh"

ensure_xcode_ready() {
  if ! xcodebuild -checkFirstLaunchStatus >/dev/null 2>&1; then
    cat >&2 <<'EOF'
Hub View cannot build yet because Xcode first-launch setup is incomplete.

Please open Xcode once and finish the initial setup prompts.
If you prefer the terminal path, run:
  sudo xcodebuild -license accept
  sudo xcodebuild -runFirstLaunch
EOF
    exit 69
  fi

  if ! swift --version >/dev/null 2>&1; then
    cat >&2 <<'EOF'
Hub View cannot build because the Swift toolchain is not ready yet.

Please open Xcode once and finish the initial setup prompts.
EOF
    exit 69
  fi
}

pkill -x "$APP_EXECUTABLE_NAME" >/dev/null 2>&1 || true
ensure_xcode_ready

swift build --package-path "$PACKAGE_DIR"
BUILD_BINARY="$(swift build --package-path "$PACKAGE_DIR" --show-bin-path)/$APP_EXECUTABLE_NAME"

rm -rf "$APP_BUNDLE"
mkdir -p "$APP_MACOS"
mkdir -p "$APP_RESOURCES"
cp "$BUILD_BINARY" "$APP_BINARY"
chmod +x "$APP_BINARY"

if [[ -f "$ICON_SOURCE" ]]; then
  cp "$ICON_SOURCE" "$ICON_TARGET"
fi

cat >"$INFO_PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleExecutable</key>
  <string>$APP_EXECUTABLE_NAME</string>
  <key>CFBundleIdentifier</key>
  <string>$BUNDLE_ID</string>
  <key>CFBundleName</key>
  <string>$APP_DISPLAY_NAME</string>
  <key>CFBundleDisplayName</key>
  <string>$APP_DISPLAY_NAME</string>
  <key>CFBundleDevelopmentRegion</key>
  <string>de</string>
  <key>CFBundleLocalizations</key>
  <array>
    <string>de</string>
  </array>
  <key>CFBundleIconFile</key>
  <string>HubView.icns</string>
  <key>CFBundlePackageType</key>
  <string>APPL</string>
  <key>LSMinimumSystemVersion</key>
  <string>$MIN_SYSTEM_VERSION</string>
  <key>NSPrincipalClass</key>
  <string>NSApplication</string>
</dict>
</plist>
PLIST

cat >"$RUNTIME_CONFIG" <<JSON
{
  "repoRoot": "$ROOT_DIR",
  "pythonBin": "$PYTHON_BIN",
  "databaseURL": "$DATABASE_URL",
  "obsidianExportDir": "$OBSIDIAN_EXPORT_DIR"
}
JSON

open_app() {
  /usr/bin/open -n "$APP_BUNDLE"
}

case "$MODE" in
  build|--build)
    printf 'Built app bundle: %s\n' "$APP_BUNDLE"
    ;;
  run)
    printf 'Launching %s\n' "$APP_BUNDLE"
    open_app
    ;;
  --debug|debug)
    lldb -- "$APP_BINARY" --repo-root "$ROOT_DIR" --python-bin "$PYTHON_BIN" --database-url "$DATABASE_URL" --obsidian-export-dir "$OBSIDIAN_EXPORT_DIR"
    ;;
  --logs|logs)
    printf 'Launching %s\n' "$APP_BUNDLE"
    open_app
    /usr/bin/log stream --info --style compact --predicate "process == \"$APP_EXECUTABLE_NAME\""
    ;;
  --telemetry|telemetry)
    printf 'Launching %s\n' "$APP_BUNDLE"
    open_app
    /usr/bin/log stream --info --style compact --predicate "subsystem == \"$BUNDLE_ID\""
    ;;
  --verify|verify)
    open_app
    sleep 2
    APP_PID="$(pgrep -x "$APP_EXECUTABLE_NAME" | head -n 1)"
    printf 'Hub View running (pid %s) from %s\n' "$APP_PID" "$APP_BUNDLE"
    ;;
  *)
    echo "usage: $0 [build|run|--debug|--logs|--telemetry|--verify]" >&2
    exit 2
    ;;
esac
