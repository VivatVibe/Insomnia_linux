#!/bin/bash
# Verification script for Insomnia Standalone GNOME Shell Extension
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=========================================================="
echo " Running Insomnia Standalone Extension Verification Suite"
echo "=========================================================="

cd "$REPO_ROOT"

# 1. Compile Schema
echo "==> [1/4] Compiling GSettings schema..."
glib-compile-schemas schemas/
echo "    Schema compiled cleanly."

# 2. Run GJS Unit Tests
echo "==> [2/5] Running standalone JavaScript unit tests..."
gjs -m tests/test_standalone.js

# 3. Run Safety & Security Gauntlet
echo "==> [3/5] Running Runtime Safety & Security Gauntlet..."
"$REPO_ROOT/scripts/check-safety.sh"

# 4. Pack Extension Validation
echo "==> [4/5] Testing extension bundle packing..."
gnome-extensions pack . --force
rm -f insomnia@vivatvibe.github.com.shell-extension.zip
echo "    Bundle packaging verified."

# 5. Install & Verification
echo "==> [5/5] Testing extension installer..."
"$REPO_ROOT/scripts/install.sh"

echo "=========================================================="
echo " All Insomnia Standalone Extension Verifications PASSED!"
echo "=========================================================="
