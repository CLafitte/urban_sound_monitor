#!/bin/bash
# setup.sh - bootstrap a Raspberry Pi for Urban Sound Monitor

set -euo pipefail
IFS=$'\n\t'

# --- 1. Move to the script's directory ---
cd "$(dirname "$0")"

# --- 2. Update system ---
echo "[INFO] Updating system..."
sudo apt-get update -y
sudo apt-get upgrade -y

# --- 3. Install Python3 and pip ---
echo "[INFO] Installing Python3 and pip..."
sudo apt-get install -y python3 python3-pip

# --- 4. Install system dependencies for sounddevice / soundfile ---
echo "[INFO] Installing ALSA dev libraries..."
sudo apt-get install -y libasound2-dev libsndfile1-dev

# --- 5. Install Python packages ---
echo "[INFO] Installing Python packages..."
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt

# --- 6. Create recordings directory ---
echo "[INFO] Creating recordings directory..."
mkdir -p recordings

# --- 7. Add .gitkeep placeholder if missing ---
if [ ! -f "recordings/.gitkeep" ]; then
    touch recordings/.gitkeep
    echo "[INFO] Added .gitkeep to recordings/"
fi

# --- 8. Setup systemd service (optional) ---
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
echo "       python3 urban_sound_monitor.py"
