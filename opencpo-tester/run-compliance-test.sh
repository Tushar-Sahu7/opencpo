#!/usr/bin/env bash
# run-compliance-test.sh — Run OCPP compliance test against a live charger
#
# Handles the full lifecycle:
#   1. Enable watchdog maintenance mode
#   2. Stop OCPP Core
#   3. Run the tester
#   4. Restart OCPP Core
#   5. Disable maintenance mode
#
# Usage:
#   ./run-compliance-test.sh [--version 1.6|2.0.1] [--host IP] [--port PORT]
#
# Output goes to ./output/compliance-latest.{pdf,pdf.html,json}

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
OUTPUT_DIR="${SCRIPT_DIR}/output"
VENV="${SCRIPT_DIR}/.venv/bin/python"
MAINTENANCE_FLAG="/tmp/ocpp-tester-maintenance"

# Optional: if you have a CSMS service running on the same port, set PROD_SERVICE to its
# systemd unit name. The script will stop it before testing and restart it after.
# Leave empty to skip service stop/start.
PROD_SERVICE="${OCPP_SERVICE:-}"
VERSION="${1:-auto}"
HOST="${2:-0.0.0.0}"
PORT="${3:-9300}"

mkdir -p "${OUTPUT_DIR}"

cleanup() {
    if [ -n "${PROD_SERVICE}" ]; then
        echo "🔄 Restarting CSMS service: ${PROD_SERVICE}..."
        systemctl --user start "${PROD_SERVICE}" 2>/dev/null || true
    fi
    rm -f "${MAINTENANCE_FLAG}"
    echo "✅ Cleanup complete"
}

trap cleanup EXIT

echo "🧪 OCPP Compliance Test — $(date '+%Y-%m-%d %H:%M:%S')"
echo "   Version: ${VERSION}"
echo "   Listen:  ws://${HOST}:${PORT}"
echo ""

# Step 1: Maintenance flag (optional — can be used by watchdog to suppress alerts)
touch "${MAINTENANCE_FLAG}"

# Step 2: Stop CSMS service if configured (to free the port)
if [ -n "${PROD_SERVICE}" ]; then
    echo "⏸️  Stopping CSMS service: ${PROD_SERVICE}..."
    systemctl --user stop "${PROD_SERVICE}"
    sleep 3
fi
fuser -k "${PORT}/tcp" 2>/dev/null || true
sleep 1

# Step 3: Run the tester
echo "🚀 Running compliance tester on port ${PORT}..."
"${VENV}" "${SCRIPT_DIR}/main.py" \
    --host "${HOST}" \
    --port "${PORT}" \
    --version "${VERSION}" \
    --full \
    --no-interactive \
    --timeout 300 \
    --report both \
    --output "${OUTPUT_DIR}/compliance-latest.pdf"

EXIT_CODE=$?

echo ""
if [ ${EXIT_CODE} -eq 0 ]; then
    echo "✅ Test complete — reports in ${OUTPUT_DIR}/"
    ls -la "${OUTPUT_DIR}/compliance-latest"* 2>/dev/null
else
    echo "❌ Tester exited with code ${EXIT_CODE}"
fi

# cleanup restores prod via trap
