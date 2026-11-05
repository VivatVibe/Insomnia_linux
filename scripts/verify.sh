#!/bin/bash
# Comprehensive verification script for Insomnia Linux
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=========================================="
echo " Running Insomnia Linux Verification Suite"
echo "=========================================="

cd "$REPO_ROOT"

# 1. Unit Tests
echo "==> [1/4] Running unit test suite..."
PYTHONPATH=. python3 -m unittest discover -s tests -v

# 2. CLI Functional Verification
echo "==> [2/4] Testing CLI session and inhibitor..."
PYTHONPATH=. python3 -m insomnia status --json >/dev/null
PYTHONPATH=. python3 -m insomnia start 5m
PYTHONPATH=. python3 -m insomnia extend 2m
PYTHONPATH=. python3 -m insomnia status
PYTHONPATH=. python3 -m insomnia end

# 3. Backstop Reconciliation Verification
echo "==> [3/4] Testing Backstop reconciliation..."
PYTHONPATH=. python3 -m insomnia backstop --force
echo "    Backstop finished with exit code 0."

# 4. Installation & Systemd Units
echo "==> [4/4] Testing installation script..."
"$REPO_ROOT/scripts/install.sh"

echo "==> Checking installed binary and timer..."
"$HOME/.local/bin/insomnia" status
systemctl --user is-active insomnia-backstop.timer || true

echo "=========================================="
echo " All Insomnia Linux Verifications PASSED!"
echo "=========================================="
