<p align="center">
  <img src="docs/assets/eye-open.svg" alt="Insomnia: an open eye with a round pupil and five lashes above it" width="112">
</p>

<h1 align="center">Insomnia (Standalone GNOME Shell Extension)</h1>

<p align="center">
  <strong>Keep your machine awake. Give the session an end time.</strong>
</p>

<p align="center">
  A native 100% standalone GNOME Shell Extension for timed keep-awake sessions and safe lid-close inhibition.
  Insomnia lives directly in your Ubuntu / GNOME Top Bar. It inhibits systemd logind sleep and lid-close suspension
  in-process without any background Python daemons, sudoers rules, or systemd services.
</p>

<p align="center">
  <a href="https://github.com/VivatVibe/Insomnia_linux"><strong>Repository</strong></a> ·
  <a href="#quick-install"><strong>Quick Install</strong></a> ·
  <a href="#features"><strong>Features</strong></a> ·
  <a href="#ux-states"><strong>UX States</strong></a> ·
  <a href="LICENSE"><strong>License</strong></a>
</p>

<p align="center">
  <a href="LICENSE"><img alt="MIT license" src="https://img.shields.io/badge/License-MIT-536D78?style=flat-square"></a>
  <img alt="GNOME Shell 45-51" src="https://img.shields.io/badge/GNOME-45%20%7C%2046%20%7C%2047%20%7C%2048%20%7C%2050%20%7C%2051-E95420?style=flat-square">
  <img alt="Status" src="https://img.shields.io/badge/Status-verified-brightgreen?style=flat-square">
</p>

<p align="center">
  <img src="docs/assets/session-flow.svg" alt="Illustrated menu-bar controls: enter Days, Hours, and Minutes, watch the countdown, and hold the end control to finish early." width="880">
</p>

---

## Features

- **100% Standalone GNOME Shell Extension:** Self-contained JavaScript (ESM) extension for GNOME 45 through 51. Zero background daemon, zero extra python dependencies.
- **Native systemd logind Inhibition:** Calls `org.freedesktop.login1.Manager.Inhibit` directly from GJS, acquiring a raw Unix File Descriptor to block `sleep:idle:handle-lid-switch`.
- **Zero Root / Sudo Required:** Runs completely within user session privileges.
- **Pixel-Perfect Top Bar Controls (session-flow.svg):**
  1. **Idle:** Closed eye vector icon with shaded lid and lashes below.
  2. **Set a duration:** Clicking the eye reveals three inline pill inputs (`Days`, `Hours`, `Mins`) with Hours automatically focused.
  3. **Watch the countdown:** Eye blinks open revealing pupil, with live ticking countdown and `✕` end button.
  4. **Hold to end:** Pressing and holding `✕` fills a circular progress ring over 0.6s to end the session early.
- **Hardware Power Protection (UPower & PowerProfiles):**
  - Monitors battery capacity via `org.freedesktop.UPower`.
  - Automatically switches `net.hadess.PowerProfiles` to `power-saver` when battery falls below the configured threshold (default 40%).
  - Optional emergency floor threshold to terminate the session if the battery runs low.
- **Adwaita Preferences Window (`prefs.js`):** Native settings page for threshold tuning and lid-switch behavior.

---

## Quick Install

### One-line Install from Source
```bash
git clone https://github.com/VivatVibe/Insomnia_linux.git
cd Insomnia_linux
./scripts/install.sh
```

After installation:
- **On Wayland:** Log out and log back in to load the extension into GNOME Shell's in-memory registry.
- **On X11:** Press `Alt + F2`, type `r`, and hit `Enter` to restart GNOME Shell.

### Packaging for extensions.gnome.org (EGO)
To create a clean distribution bundle for uploading to [extensions.gnome.org](https://extensions.gnome.org):
```bash
gnome-extensions pack . --force
# Generates: insomnia@vivatvibe.github.com.shell-extension.zip
```

---

## Verification & Testing

Insomnia includes an automated verification and safety testing suite:

```bash
# Complete suite
./scripts/verify.sh

# Dedicated safety and crash gauntlet
./scripts/check-safety.sh
```

The scripts verify:
1. GSettings schema compilation (`glib-compile-schemas`).
2. Duration string math and time formatters.
3. Live acquisition and release of `systemd logind` inhibit locks (FD check).
4. SIGKILL crash safety proving the Linux kernel automatically releases logind locks with zero orphans.
5. Extension packaging and installation.

---

## Uninstall

```bash
./scripts/uninstall.sh
```

---

## License

[MIT](LICENSE)
