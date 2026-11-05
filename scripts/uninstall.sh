#!/bin/bash
# Uninstall Insomnia Standalone GNOME Shell Extension
set -euo pipefail

EXT_UUID="insomnia@vivatvibe.github.com"
TARGET_DIR="$HOME/.local/share/gnome-shell/extensions/$EXT_UUID"

echo "==> Uninstalling Insomnia GNOME Shell Extension ($EXT_UUID)..."

if command -v gnome-extensions >/dev/null 2>&1; then
  gnome-extensions disable "$EXT_UUID" 2>/dev/null || true
fi

# Remove from gsettings enabled-extensions
if command -v gsettings >/dev/null 2>&1; then
  python3 -c '
import subprocess, ast, sys
try:
    res = subprocess.check_output(["gsettings", "get", "org.gnome.shell", "enabled-extensions"], stderr=subprocess.DEVNULL).decode().strip()
    val = ast.literal_eval(res)
    uuid = sys.argv[1]
    if uuid in val:
        val.remove(uuid)
        subprocess.check_call(["gsettings", "set", "org.gnome.shell", "enabled-extensions", str(val)])
except Exception:
    pass
' "$EXT_UUID" || true
fi

rm -rf "$TARGET_DIR"

echo "==> Insomnia GNOME Shell Extension uninstalled successfully."
