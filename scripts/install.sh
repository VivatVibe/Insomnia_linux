#!/bin/bash
# Install Insomnia for Linux GNOME
# Safe, idempotent, non-root per-user installation.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "==> Installing Insomnia for Linux..."

BIN_DIR="$HOME/.local/bin"
DATA_DIR="$HOME/.local/share/insomnia"
APP_DIR="$HOME/.local/share/applications"
SYSTEMD_USER_DIR="$HOME/.config/systemd/user"
ICON_BASE="$HOME/.local/share/icons/hicolor"

mkdir -p "$BIN_DIR" "$DATA_DIR/lib" "$APP_DIR" "$SYSTEMD_USER_DIR"

# 1. Copy application files
echo "==> Installing python package to $DATA_DIR/lib..."
rm -rf "$DATA_DIR/lib/insomnia"
cp -r "$REPO_ROOT/insomnia" "$DATA_DIR/lib/"
cp -r "$REPO_ROOT/Resources" "$DATA_DIR/"

# 2. Install executable launcher
echo "==> Installing launcher to $BIN_DIR/insomnia..."
cat > "$BIN_DIR/insomnia" << 'EOF'
#!/bin/bash
export PYTHONPATH="$HOME/.local/share/insomnia/lib:${PYTHONPATH:-}"
exec /usr/bin/python3 -m insomnia "$@"
EOF
chmod 0755 "$BIN_DIR/insomnia"

# Ensure ~/.local/bin is in PATH in ~/.bashrc if not already present
if [[ ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
  if [[ -f "$HOME/.bashrc" ]] && ! grep -q 'PATH=.*\.local/bin' "$HOME/.bashrc"; then
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.bashrc"
  fi
fi

# 3. Install desktop launcher
echo "==> Installing desktop application entry..."
cp "$REPO_ROOT/systemd/insomnia.desktop" "$APP_DIR/insomnia.desktop"

# 4. Install icons into hicolor icon theme
echo "==> Installing hicolor icons..."
for size in 16 24 32 48 64 128 256 512; do
  icon_dir="$ICON_BASE/${size}x${size}/apps"
  mkdir -p "$icon_dir"
  if [[ -f "$REPO_ROOT/Resources/icons/insomnia-${size}.png" ]]; then
    cp "$REPO_ROOT/Resources/icons/insomnia-${size}.png" "$icon_dir/insomnia.png"
  fi
done

if command -v gtk-update-icon-cache >/dev/null 2>&1; then
  gtk-update-icon-cache -f -t "$ICON_BASE" >/dev/null 2>&1 || true
fi

# 5. Install systemd user service and timer
echo "==> Configuring systemd user units..."
cp "$REPO_ROOT/systemd/insomnia-backstop.service" "$SYSTEMD_USER_DIR/"
cp "$REPO_ROOT/systemd/insomnia-backstop.timer" "$SYSTEMD_USER_DIR/"
cp "$REPO_ROOT/systemd/insomnia.service" "$SYSTEMD_USER_DIR/"

systemctl --user daemon-reload
systemctl --user enable --now insomnia-backstop.timer

echo "==> Insomnia installed successfully!"
echo "    Executable:     $BIN_DIR/insomnia"
echo "    Backstop Timer: systemctl --user status insomnia-backstop.timer"
echo "    Run tray:       insomnia run (or systemctl --user start insomnia.service)"
