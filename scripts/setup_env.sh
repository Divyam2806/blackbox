#!/usr/bin/env bash
# Creates a local virtualenv and prepares the simulation tools.
# Works on Linux, macOS and WSL2. On Windows use setup_env.ps1.
#
# Usage:
#   scripts/setup_env.sh [--with-wokwi] [--with-renode] [--with-gazebo] [--install-system]
#
# By default it installs only Python packages inside .venv and checks the rest.
# --install-system lets it use apt (Debian/Ubuntu) and needs sudo.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$ROOT/.venv"
WITH_WOKWI=0; WITH_RENODE=0; WITH_GAZEBO=0; INSTALL_SYSTEM=0

for arg in "$@"; do
  case "$arg" in
    --with-wokwi)  WITH_WOKWI=1 ;;
    --with-renode) WITH_RENODE=1 ;;
    --with-gazebo) WITH_GAZEBO=1 ;;
    --install-system) INSTALL_SYSTEM=1 ;;
    -h|--help) sed -n '2,10p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "Unknown option: $arg"; exit 2 ;;
  esac
done

say()  { printf '\n== %s\n' "$*"; }
have() { command -v "$1" >/dev/null 2>&1; }
apt_install() {
  if [ "$INSTALL_SYSTEM" -eq 1 ] && have apt-get; then
    sudo apt-get update && sudo apt-get install -y "$@"
  else
    echo "Not installing system packages automatically. Run:"
    echo "  sudo apt-get install -y $*"
  fi
}

say "1/6 Python"
PY="${PYTHON:-python3}"
have "$PY" || { echo "python3 not found. Install Python 3.10 or newer."; exit 1; }
"$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' \
  || { echo "Python 3.10+ is required."; exit 1; }
"$PY" --version

say "2/6 Virtual environment at $VENV"
if [ ! -d "$VENV" ]; then
  "$PY" -m venv "$VENV" || {
    echo "venv creation failed. On Ubuntu run: sudo apt-get install -y python3-venv"; exit 1; }
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"
python -m pip install --upgrade pip wheel >/dev/null

say "3/6 Python packages"
if [ -f "$ROOT/pyproject.toml" ]; then
  pip install -e "$ROOT" || pip install -r "$ROOT/requirements.txt"
else
  pip install -r "$ROOT/requirements.txt"
fi

say "4/6 Host-HAL toolchain (C++ compiler)"
if ! have g++ && ! have clang++; then
  apt_install build-essential
fi
have g++ && g++ --version | head -n 1 || true

say "5/6 Optional simulators"
if [ "$WITH_WOKWI" -eq 1 ]; then
  if ! have wokwi-cli; then
    echo "Installing Wokwi CLI with the official installer (check https://docs.wokwi.com/wokwi-ci/getting-started)."
    curl -fsSL https://wokwi.com/ci/install.sh | sh || echo "Wokwi installer failed. Install it by hand."
  fi
  if ! have arduino-cli; then
    echo "arduino-cli missing. Install from https://arduino.github.io/arduino-cli/latest/installation/"
  fi
  echo "Create a token at https://wokwi.com/dashboard/ci and put it in .env as WOKWI_CLI_TOKEN."
fi
if [ "$WITH_RENODE" -eq 1 ] && ! have renode; then
  echo "Renode is not installed. Download the portable build from"
  echo "  https://github.com/renode/renode/releases"
  echo "then add its folder to PATH."
fi
if [ "$WITH_GAZEBO" -eq 1 ] && ! have gz; then
  echo "Gazebo is not installed. Follow the install guide for your OS at"
  echo "  https://gazebosim.org/docs/latest/install/"
  echo "Linux or WSL2 is required."
fi

say "6/6 Config and check"
[ -f "$ROOT/.env" ] || { [ -f "$ROOT/.env.example" ] && cp "$ROOT/.env.example" "$ROOT/.env" && echo "Created .env from .env.example"; } || true
python "$ROOT/scripts/check_env.py" || true

cat <<MSG

Done. Activate the environment in any new terminal with:
  source .venv/bin/activate
Then run:
  fwagent run firmware_samples/cooling_fan_buggy --sim auto
MSG
