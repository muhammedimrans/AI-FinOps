#!/usr/bin/env bash
# COSTORAH Monitoring Agent — Linux installer.
#
# Installs costorah-agent into a dedicated virtualenv under /opt, creates
# a restricted system user, lays down config/state/log directories with
# correct ownership, and installs (but does not start) the systemd unit.
#
# Usage:
#   sudo ./install.sh
#   sudo systemctl edit costorah-agent --full   # or edit /etc/costorah-agent/config.yaml
#   sudo systemctl enable --now costorah-agent

set -euo pipefail

INSTALL_DIR="/opt/costorah-agent"
CONFIG_DIR="/etc/costorah-agent"
STATE_DIR="/var/lib/costorah-agent"
LOG_DIR="/var/log/costorah-agent"
SERVICE_USER="costorah-agent"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

if [[ "${EUID}" -ne 0 ]]; then
  echo "This installer must be run as root (sudo ./install.sh)." >&2
  exit 1
fi

if ! command -v python3.12 >/dev/null 2>&1 && ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3.12+ is required but was not found on PATH." >&2
  exit 1
fi
PYTHON_BIN="$(command -v python3.12 || command -v python3)"

echo "==> Creating system user '${SERVICE_USER}'"
if ! id -u "${SERVICE_USER}" >/dev/null 2>&1; then
  useradd --system --no-create-home --shell /usr/sbin/nologin "${SERVICE_USER}"
fi

echo "==> Installing to ${INSTALL_DIR}"
mkdir -p "${INSTALL_DIR}"
"${PYTHON_BIN}" -m venv "${INSTALL_DIR}/.venv"
"${INSTALL_DIR}/.venv/bin/pip" install --quiet --upgrade pip
"${INSTALL_DIR}/.venv/bin/pip" install --quiet "${REPO_ROOT}"

ln -sf "${INSTALL_DIR}/.venv/bin/costorah-agent" /usr/local/bin/costorah-agent

echo "==> Creating config/state/log directories"
mkdir -p "${CONFIG_DIR}" "${STATE_DIR}" "${LOG_DIR}"
if [[ ! -f "${CONFIG_DIR}/config.yaml" ]]; then
  cp "${REPO_ROOT}/config.example.yaml" "${CONFIG_DIR}/config.yaml"
  echo "    Wrote default config to ${CONFIG_DIR}/config.yaml — edit it and set organization.api_key"
fi
chown -R "${SERVICE_USER}:${SERVICE_USER}" "${CONFIG_DIR}" "${STATE_DIR}" "${LOG_DIR}"
chmod 750 "${CONFIG_DIR}"

echo "==> Installing systemd unit"
cp "${SCRIPT_DIR}/costorah-agent.service" /etc/systemd/system/costorah-agent.service
systemctl daemon-reload

cat <<EOF

Installed. Next steps:
  1. Edit ${CONFIG_DIR}/config.yaml and set organization.api_key
     (or export COSTORAH_AGENT_ORGANIZATION__API_KEY in the unit's
     Environment= instead of storing it in the file).
  2. sudo systemctl enable --now costorah-agent
  3. sudo systemctl status costorah-agent
  4. curl http://127.0.0.1:9091/health
EOF
