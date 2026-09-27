#!/bin/bash
# setup.sh - bootstrap a Raspberry Pi for Urban Sound Monitor
set -euo pipefail
IFS=$'\n\t'

EXPECTED_PATH="/home/pi/urban_sound_monitor"

# --- 1. Move to the script's directory ---
cd "$(dirname "$0")"

# --- 2. Sanity-check install location against the systemd service's assumptions ---
if [ "$(pwd)" != "$EXPECTED_PATH" ]; then
    echo "[WARN] Running from $(pwd), but urban_sound_monitor.service expects $EXPECTED_PATH"
    echo "       Either clone the repo to $EXPECTED_PATH, or edit WorkingDirectory/ExecStart"
    echo "       in urban_sound_monitor.service to match this path before enabling the service."
fi

# --- 3. Confirm requirements.txt is present before we get deep into setup ---
if [ ! -f "requirements.txt" ]; then
    echo "[ERROR] requirements.txt not found in $(pwd). Aborting."
    exit 1
fi

# --- 4. Update system ---
echo "[INFO] Updating package lists..."
sudo apt-get update -y
echo "[INFO] Skipping full 'apt-get upgrade' — run it manually and separately"
echo "       when you're ready to accept OS/kernel changes:"
echo "       sudo apt-get upgrade -y"

# --- 5. Install Python3, pip, and venv ---
echo "[INFO] Installing Python3, pip, and venv..."
sudo apt-get install -y python3 python3-pip python3-venv

# --- 6. Install system dependencies for sounddevice / soundfile ---
echo "[INFO] Installing ALSA dev libraries..."
sudo apt-get install -y libasound2-dev libsndfile1-dev

# --- 7. Create virtual environment ---
if [ -d "venv" ]; then
    echo "[INFO] Virtual environment already exists, skipping creation."
    echo "       (If setup previously failed partway through, run 'rm -rf venv' and re-run this script.)"
else
    echo "[INFO] Creating virtual environment..."
    python3 -m venv venv
fi

# --- 8. Install Python packages into the venv ---
echo "[INFO] Installing Python packages into venv..."
venv/bin/python3 -m pip install --upgrade pip
venv/bin/python3 -m pip install -r requirements.txt

# --- 9. Create recordings directory ---
echo "[INFO] Creating recordings directory..."
mkdir -p recordings

# --- 10. Add .gitkeep placeholder if missing ---
if [ ! -f "recordings/.gitkeep" ]; then
    touch recordings/.gitkeep
    echo "[INFO] Added .gitkeep to recordings/"
fi

# --- 11. Setup systemd service (optional) ---
SERVICE_FILE="urban_sound_monitor.service"
if [ -f "$SERVICE_FILE" ]; then
    echo "[INFO] Copying systemd service..."
    sudo cp "$SERVICE_FILE" /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl enable --now urban_sound_monitor.service
    echo "[INFO] Service enabled and started."
else
    echo "[WARN] $SERVICE_FILE not found, skipping systemd setup."
fi

echo
echo "[INFO] Setup complete."
echo "       You can run the monitor manually with:"
echo "       venv/bin/python3 urban_sound_monitor.py"
