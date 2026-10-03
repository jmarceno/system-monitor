#!/usr/bin/env bash
# Install the system monitor launcher, app-menu entry, and systemd user service.
#
#   ./scripts/install.sh            install + enable (starts on login)
#   ./scripts/install.sh --start    install + enable + start now
#   ./scripts/install.sh --menu     app-menu launcher only (no systemd unit)
#
# Kill switch:  systemctl --user stop system-monitor
# Uninstall:    systemctl --user disable --now system-monitor
#               rm ~/.config/systemd/user/system-monitor.service
#               rm ~/.local/share/applications/system-monitor.desktop
#               rm ~/.local/bin/system-monitor
set -euo pipefail

START=0
MENU_ONLY=0
case "${1:-}" in
    --start) START=1 ;;
    --menu) MENU_ONLY=1 ;;
esac

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${REPO_DIR}/.venv"
PYTHON="${VENV_DIR}/bin/python"

if [[ ! -x "${PYTHON}" ]]; then
    if command -v uv >/dev/null 2>&1; then
        uv venv --python python3.12 "${VENV_DIR}" || uv venv --python python3 "${VENV_DIR}"
        uv pip install --python "${PYTHON}" -e "${REPO_DIR}"
    else
        python3 -m venv "${VENV_DIR}"
        "${PYTHON}" -m pip install -e "${REPO_DIR}"
    fi
fi

if ! "${PYTHON}" -c "import PySide6" >/dev/null 2>&1; then
    echo "error: PySide6 is not installed in ${VENV_DIR}" >&2
    echo "hint: uv pip install --python ${PYTHON} PySide6" >&2
    exit 1
fi

chmod +x "${REPO_DIR}/scripts/system-monitor"

BIN_DIR="${HOME}/.local/bin"
APP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
LAUNCHER="${BIN_DIR}/system-monitor"
DESKTOP_FILE="${APP_DIR}/system-monitor.desktop"

mkdir -p "${BIN_DIR}" "${APP_DIR}"
ln -sfn "${REPO_DIR}/scripts/system-monitor" "${LAUNCHER}"

sed -e "s|@EXEC@|${LAUNCHER}|g" \
    -e "s|@REPO_DIR@|${REPO_DIR}|g" \
    "${REPO_DIR}/packaging/system-monitor.desktop.in" > "${DESKTOP_FILE}"
chmod 644 "${DESKTOP_FILE}"

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "${APP_DIR}" >/dev/null 2>&1 || true
fi
if command -v xdg-desktop-menu >/dev/null 2>&1; then
    xdg-desktop-menu forceupdate >/dev/null 2>&1 || true
fi

echo "app menu: ${DESKTOP_FILE}"
echo "launcher: ${LAUNCHER}"

if [[ "${MENU_ONLY}" -eq 1 ]]; then
    exit 0
fi

UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
UNIT_FILE="${UNIT_DIR}/system-monitor.service"
LEGACY_UNIT="${UNIT_DIR}/qs-system-monitor.service"

mkdir -p "${UNIT_DIR}"
sed -e "s|@PYTHON@|${PYTHON}|g" \
    -e "s|@REPO_DIR@|${REPO_DIR}|g" \
    "${REPO_DIR}/packaging/system-monitor.service.in" > "${UNIT_FILE}"

# Migrate the old Quickshell unit if it is still enabled.
if [[ -f "${LEGACY_UNIT}" ]]; then
    systemctl --user disable --now qs-system-monitor.service >/dev/null 2>&1 || true
    rm -f "${LEGACY_UNIT}"
fi

systemctl --user daemon-reload
systemctl --user enable system-monitor.service

if [[ "${START}" -eq 1 ]]; then
    systemctl --user restart system-monitor.service
    echo "started: systemctl --user status system-monitor"
else
    echo "installed: ${UNIT_FILE}"
    echo "start it with: systemctl --user start system-monitor"
fi
echo "kill switch:  systemctl --user stop system-monitor"
