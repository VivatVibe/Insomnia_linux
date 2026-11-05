#!/bin/bash
# Uninstall Insomnia for Linux GNOME
set -euo pipefail

echo "==> Uninstalling Insomnia for Linux..."

BIN_DIR="$HOME/.local/bin"
DATA_DIR="$HOME/.local/share/insomnia"
CONFIG_DIR="$HOME/.config/insomnia"
APP_DIR="$HOME/.local/share/applications"
SYSTEMD_USER_DIR="$HOME/.config/systemd/user"
ICON_BASE="$HOME/.local/share/icons/hicolor"

PURGE=0
for arg in "$@"; do
  case "$arg" in
    --purge) PURGE=1 ;;
  esac
done

# 1. Run backstop with --force to release locks and restore settings
if [[ -x "$BIN_DIR/insomnia" ]]; then
  echo "==> Running backstop cleanup under recovery lock..."
  "$BIN_DIR/insomnia" backstop --force || true
fi

# 2. Stop and disable systemd user units
echo "==> Disabling systemd units..."
systemctl --user stop insomnia.service 2>/dev/null || true
systemctl --user stop insomnia-backstop.timer 2>/dev/null || true
systemctl --user disable insomnia-backstop.timer 2>/dev/null || true

rm -f "$SYSTEMD_USER_DIR/insomnia-backstop.service"
rm -f "$SYSTEMD_USER_DIR/insomnia-backstop.timer"
rm -f "$SYSTEMD_USER_DIR/insomnia.service"
systemctl --user daemon-reload || true

# 3. Remove executable and desktop entry
echo "==> Removing launcher and desktop entry..."
rm -f "$BIN_DIR/insomnia"
rm -f "$APP_DIR/insomnia.desktop"

# 3b. Disable and remove GNOME Shell extension
EXT_UUID="insomnia@vivatvibe.github.com"
EXT_DIR="$HOME/.local/share/gnome-shell/extensions/$EXT_UUID"
if command -v gnome-extensions >/dev/null 2>&1; then
  gnome-extensions disable "$EXT_UUID" 2>/dev/null || true
fi
rm -rf "$EXT_DIR"

# 4. Remove icons
for size in 16 24 32 48 64 128 256 512; do
  rm -f "$ICON_BASE/${size}x${size}/apps/insomnia.png"
done

# 5. Purge if requested
if [[ "$PURGE" -eq 1 ]]; then
  echo "==> Purging user data and configuration..."
  rm -rf "$DATA_DIR" "$CONFIG_DIR"
else
  rm -rf "$DATA_DIR/lib"
fi

echo "==> Insomnia uninstalled successfully."
