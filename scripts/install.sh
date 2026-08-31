#!/usr/bin/env bash
# Install the system monitor as a systemd user service.
#
#   ./scripts/install.sh            install + enable (starts on login)
#   ./scripts/install.sh --start    install + enable + start now
#
# Kill switch:  systemctl --user stop qs-system-monitor
# Uninstall:    systemctl --user disable --now qs-system-monitor
#               rm ~/.config/systemd/user/qs-system-monitor.service
set -euo pipefail

START=0
[[ "${1:-}" == "--start" ]] && START=1

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SHELL_DIR="${REPO_DIR}/shell"
QUICKSHELL_BIN="$(command -v quickshell || true)"

if [[ -z "${QUICKSHELL_BIN}" ]]; then
    echo "error: quickshell not found in PATH" >&2
    exit 1
fi
if [[ ! -f "${SHELL_DIR}/shell.qml" ]]; then
    echo "error: ${SHELL_DIR}/shell.qml not found" >&2
    exit 1
fi

UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
UNIT_FILE="${UNIT_DIR}/qs-system-monitor.service"

mkdir -p "${UNIT_DIR}"
sed -e "s|@QUICKSHELL_BIN@|${QUICKSHELL_BIN}|g" \
    -e "s|@SHELL_DIR@|${SHELL_DIR}|g" \
    "${REPO_DIR}/packaging/qs-system-monitor.service.in" > "${UNIT_FILE}"

systemctl --user daemon-reload
systemctl --user enable qs-system-monitor.service

if [[ "${START}" -eq 1 ]]; then
    systemctl --user restart qs-system-monitor.service
    echo "started: systemctl --user status qs-system-monitor"
else
    echo "installed: ${UNIT_FILE}"
    echo "start it with: systemctl --user start qs-system-monitor"
fi
echo "kill switch:  systemctl --user stop qs-system-monitor"
