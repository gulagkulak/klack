#!/usr/bin/env bash
set -euo pipefail

# Determine project root (directory containing this script)
PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
APP_NAME="Klack"
APP_ID="klack"
RUN_SCRIPT="$PROJECT_DIR/run.sh"
ICON_FILE="$PROJECT_DIR/icon.svg"
APPLICATIONS_DIR="$HOME/.local/share/applications"
AUTOSTART_DIR="$HOME/.config/autostart"
DESKTOP_FILE_PATH="$APPLICATIONS_DIR/${APP_ID}.desktop"
AUTOSTART_FILE_PATH="$AUTOSTART_DIR/${APP_ID}.desktop"

echo "Installing $APP_NAME..."

# Verify required files
if [[ ! -f "$RUN_SCRIPT" ]]; then
  echo "Error: run.sh not found at $RUN_SCRIPT" >&2
  exit 1
fi
if [[ ! -f "$ICON_FILE" ]]; then
  echo "Warning: icon.svg not found at $ICON_FILE. Proceeding without icon." >&2
fi

# Ensure run script is executable
chmod +x "$RUN_SCRIPT"

mkdir -p "$APPLICATIONS_DIR"

cat > "$DESKTOP_FILE_PATH" <<EOF
[Desktop Entry]
Type=Application
Name=$APP_NAME
Comment=Keyboard click sounds with system tray control
Exec=${RUN_SCRIPT}
Icon=${ICON_FILE}
Terminal=false
Categories=Utility;Audio;
StartupNotify=false
EOF

echo "Created desktop entry at: $DESKTOP_FILE_PATH"

# Refresh desktop databases if available
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "$APPLICATIONS_DIR" || true
fi
if command -v xdg-desktop-menu >/dev/null 2>&1; then
  xdg-desktop-menu forceupdate || true
fi

# GNOME Shell cache refresh (no-op if not GNOME)
if command -v gnome-shell >/dev/null 2>&1 && command -v gsettings >/dev/null 2>&1; then
  : # modern GNOME generally picks up .desktop changes automatically
fi

# KDE icon cache (only run if actually on KDE/Plasma)
if [[ "${XDG_CURRENT_DESKTOP:-}" == *"KDE"* ]]; then
  if command -v kbuildsycoca6 >/dev/null 2>&1; then
    kbuildsycoca6 2>/dev/null || true
  elif command -v kbuildsycoca5 >/dev/null 2>&1; then
    kbuildsycoca5 2>/dev/null || true
  fi
fi

echo
read -r -p "Start Klack automatically on login? [y/N] " REPLY
REPLY=${REPLY:-N}
case "$REPLY" in
  [yY][eE][sS]|[yY])
    mkdir -p "$AUTOSTART_DIR"
    cp -f "$DESKTOP_FILE_PATH" "$AUTOSTART_FILE_PATH"
    # Some desktops require this key to be present
    if ! grep -q "^X-GNOME-Autostart-enabled=" "$AUTOSTART_FILE_PATH" 2>/dev/null; then
      echo "X-GNOME-Autostart-enabled=true" >> "$AUTOSTART_FILE_PATH"
    fi
    echo "Autostart enabled: $AUTOSTART_FILE_PATH"
    ;;
  *)
    echo "Autostart not enabled."
    ;;
esac

echo
echo "Installation complete. You can now launch '$APP_NAME' from your application menu/launcher."
