#!/bin/bash
# Build Debian package (.deb) for Insomnia Linux
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

PKG_NAME="insomnia"
PKG_VERSION="1.0.0"
PKG_ARCH="all"
DEB_NAME="${PKG_NAME}_${PKG_VERSION}_${PKG_ARCH}.deb"

BUILD_DIR="$REPO_ROOT/build/deb-staging"
DIST_DIR="$REPO_ROOT/dist"

echo "==> Preparing Debian package build for $PKG_NAME $PKG_VERSION ($PKG_ARCH)..."

# Clean previous build artifacts
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR" "$DIST_DIR"

# 1. Create target directory structure
mkdir -p "$BUILD_DIR/DEBIAN"
mkdir -p "$BUILD_DIR/usr/bin"
mkdir -p "$BUILD_DIR/usr/lib/insomnia"
mkdir -p "$BUILD_DIR/usr/lib/systemd/user"
mkdir -p "$BUILD_DIR/usr/share/applications"

# 2. Copy application code and resources
cp -r "$REPO_ROOT/insomnia" "$BUILD_DIR/usr/lib/insomnia/"
cp -r "$REPO_ROOT/Resources" "$BUILD_DIR/usr/lib/insomnia/"

# Remove bytecode or caches if any
find "$BUILD_DIR/usr/lib/insomnia" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find "$BUILD_DIR/usr/lib/insomnia" -name "*.py[co]" -delete 2>/dev/null || true

# 3. Create /usr/bin/insomnia launcher
cat > "$BUILD_DIR/usr/bin/insomnia" << 'EOF'
#!/bin/bash
export PYTHONPATH="/usr/lib/insomnia:${PYTHONPATH:-}"
exec /usr/bin/python3 -m insomnia "$@"
EOF
chmod 0755 "$BUILD_DIR/usr/bin/insomnia"

# 4. Install systemd user units (adjusting ExecStart to /usr/bin/insomnia)
sed 's|%h/.local/bin/insomnia|/usr/bin/insomnia|g' \
  "$REPO_ROOT/systemd/insomnia-backstop.service" > "$BUILD_DIR/usr/lib/systemd/user/insomnia-backstop.service"

sed 's|%h/.local/bin/insomnia|/usr/bin/insomnia|g' \
  "$REPO_ROOT/systemd/insomnia.service" > "$BUILD_DIR/usr/lib/systemd/user/insomnia.service"

cp "$REPO_ROOT/systemd/insomnia-backstop.timer" "$BUILD_DIR/usr/lib/systemd/user/"

chmod 0644 "$BUILD_DIR/usr/lib/systemd/user/"*

# 5. Desktop entry
cp "$REPO_ROOT/systemd/insomnia.desktop" "$BUILD_DIR/usr/share/applications/"
chmod 0644 "$BUILD_DIR/usr/share/applications/insomnia.desktop"

# 6. Icons
for size in 16 24 32 48 64 128 256 512; do
  icon_dir="$BUILD_DIR/usr/share/icons/hicolor/${size}x${size}/apps"
  mkdir -p "$icon_dir"
  if [[ -f "$REPO_ROOT/Resources/icons/insomnia-${size}.png" ]]; then
    cp "$REPO_ROOT/Resources/icons/insomnia-${size}.png" "$icon_dir/insomnia.png"
    chmod 0644 "$icon_dir/insomnia.png"
  fi
done

# 7. Calculate Installed-Size in KB
INSTALLED_SIZE=$(du -sk "$BUILD_DIR" | cut -f1)

# 8. Create DEBIAN/control
cat > "$BUILD_DIR/DEBIAN/control" << EOF
Package: $PKG_NAME
Version: $PKG_VERSION
Section: utils
Priority: optional
Architecture: $PKG_ARCH
Depends: python3, python3-gi, python3-dbus, python3-psutil, python3-dasbus, gir1.2-gtk-3.0
Maintainer: VivatVibe <contact@vivatvibe.com>
Installed-Size: $INSTALLED_SIZE
Homepage: https://github.com/VivatVibe/Insomnia_linux
Description: Keep-awake session manager and lid-close engine for Ubuntu GNOME
 Insomnia prevents sleep, idle, and lid-close suspension using native
 systemd logind D-Bus inhibitors without root or sudo permissions.
 Features GNOME AppIndicator tray menu, journaled recovery lock, and
 abnormal termination backstop timer.
EOF
chmod 0644 "$BUILD_DIR/DEBIAN/control"

# 9. Create DEBIAN/postinst
cat > "$BUILD_DIR/DEBIAN/postinst" << 'EOF'
#!/bin/sh
set -e

case "$1" in
    configure)
        if command -v update-desktop-database >/dev/null 2>&1; then
            update-desktop-database -q || true
        fi
        if command -v gtk-update-icon-cache >/dev/null 2>&1; then
            gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor || true
        fi
        if command -v systemctl >/dev/null 2>&1; then
            systemctl daemon-reload || true
        fi
        ;;
esac

exit 0
EOF
chmod 0755 "$BUILD_DIR/DEBIAN/postinst"

# 10. Create DEBIAN/postrm
cat > "$BUILD_DIR/DEBIAN/postrm" << 'EOF'
#!/bin/sh
set -e

case "$1" in
    remove|purge)
        if command -v update-desktop-database >/dev/null 2>&1; then
            update-desktop-database -q || true
        fi
        if command -v gtk-update-icon-cache >/dev/null 2>&1; then
            gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor || true
        fi
        if command -v systemctl >/dev/null 2>&1; then
            systemctl daemon-reload || true
        fi
        ;;
esac

exit 0
EOF
chmod 0755 "$BUILD_DIR/DEBIAN/postrm"

# Enforce clean directory permissions
find "$BUILD_DIR" -type d -exec chmod 0755 {} +

# 11. Build Debian package
echo "==> Building $DIST_DIR/$DEB_NAME..."
dpkg-deb --build --root-owner-group "$BUILD_DIR" "$DIST_DIR/$DEB_NAME"

echo "==> Package build completed: $DIST_DIR/$DEB_NAME"
