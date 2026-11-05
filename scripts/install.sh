#!/bin/bash
# Install Insomnia Standalone GNOME Shell Extension
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
EXT_UUID="insomnia@vivatvibe.github.com"
TARGET_DIR="$HOME/.local/share/gnome-shell/extensions/$EXT_UUID"

echo "==> Installing Insomnia Standalone GNOME Shell Extension ($EXT_UUID)..."

cd "$REPO_ROOT"

# 1. Compile schemas
if command -v glib-compile-schemas >/dev/null 2>&1; then
  echo "==> Compiling GSettings schemas..."
  glib-compile-schemas schemas/
fi

# 2. Install extension files to user extension directory
echo "==> Copying extension files to $TARGET_DIR..."
rm -rf "$TARGET_DIR"
mkdir -p "$TARGET_DIR"

cp -r metadata.json extension.js prefs.js stylesheet.css lib schemas "$TARGET_DIR/"

# 3. Enable extension
if command -v gnome-extensions >/dev/null 2>&1; then
  echo "==> Enabling extension via gnome-extensions..."
  gnome-extensions enable "$EXT_UUID" >/dev/null 2>&1 || true
fi

# 4. Ensure enabled in gsettings
if command -v gsettings >/dev/null 2>&1; then
  python3 -c '
import subprocess, ast, sys
try:
    res = subprocess.check_output(["gsettings", "get", "org.gnome.shell", "enabled-extensions"], stderr=subprocess.DEVNULL).decode().strip()
    val = ast.literal_eval(res)
    uuid = sys.argv[1]
    if uuid not in val:
        val.append(uuid)
        subprocess.check_call(["gsettings", "set", "org.gnome.shell", "enabled-extensions", str(val)])
except Exception:
    pass
' "$EXT_UUID" || true
fi

echo "=========================================================="
echo " Insomnia GNOME Shell Extension installed successfully!"
echo " UUID: $EXT_UUID"
echo " Location: $TARGET_DIR"
echo "=========================================================="
