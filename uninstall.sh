#!/usr/bin/env bash
set -euo pipefail

APP_ID="klack"
APPLICATIONS_DIR="$HOME/.local/share/applications"
AUTOSTART_DIR="$HOME/.config/autostart"
DESKTOP_FILE_PATH="$APPLICATIONS_DIR/${APP_ID}.desktop"
AUTOSTART_FILE_PATH="$AUTOSTART_DIR/${APP_ID}.desktop"

echo "Uninstalling Klack..."

if [[ -f "$DESKTOP_FILE_PATH" ]]; then
  rm -f "$DESKTOP_FILE_PATH"
  echo "Removed: $DESKTOP_FILE_PATH"
else
  echo "No desktop file found at $DESKTOP_FILE_PATH"
fi

if [[ -f "$AUTOSTART_FILE_PATH" ]]; then
  rm -f "$AUTOSTART_FILE_PATH"
  echo "Removed autostart entry: $AUTOSTART_FILE_PATH"
else
  echo "No autostart entry found at $AUTOSTART_FILE_PATH"
fi

# Refresh menus/caches if tools are available
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "$APPLICATIONS_DIR" || true
fi
if command -v xdg-desktop-menu >/dev/null 2>&1; then
  xdg-desktop-menu forceupdate || true
fi
# Only refresh KDE cache if on KDE/Plasma
if [[ "${XDG_CURRENT_DESKTOP:-}" == *"KDE"* ]]; then
  if command -v kbuildsycoca6 >/dev/null 2>&1; then
    kbuildsycoca6 2>/dev/null || true
  elif command -v kbuildsycoca5 >/dev/null 2>&1; then
    kbuildsycoca5 2>/dev/null || true
  fi
fi

echo "Uninstall complete."
