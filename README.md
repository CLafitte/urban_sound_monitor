# Urban Sound Monitor

urban_sound_monitor is a proof-of-concept ambient field noise recorder for Raspberry Pi using any driverless USB microphone. 
It captures short bursts of urban sound, computes A-weighted LAeq levels, and saves audio + metadata in a dedicated folder for offline data processing. 
This lightweight program is built for expansion into embedded applications for ecological research and urban planning.

## Features


- Captures 6-second bursts every 60 seconds.
- Computes A-weighted LAeq (dBFS) per burst.
- Stores audio in FLAC format with XML metadata.
- Supports dynamic USB microphone detection.

---

## Architecture Overview


            +----------------------------+
             |  Raspberry Pi (OS/ALSA)   |
             +----------------------------+
                           |
                           | systemd reads configuration
                           v
             +----------------------------+
             | urban_sound_monitor.service|  <--- systemd unit
             |----------------------------|
             | ExecStart -> runs Python   |
             | Restart=always, etc.       |
             +----------------------------+
                           |
                           | executes
                           v
             +----------------------------+
             | urban_sound_monitor.py     |  <--- Python script
             |----------------------------|
             |  - Records bursts via USB mic
             |  - Applies high-pass & A-weighting DSP
             |  - Computes LAeq (dBFS)
             |  - Saves audio (FLAC) and XML metadata
             +----------------------------+
                           |
            +--------------+--------------+
            |                             |
            v                             v
   +----------------+             +----------------+
   | recordings/*.flac |          | recordings/*.xml|
   | Audio files       |          | Metadata logs   |
   +----------------+             +----------------+


---

## Installation

1. Clone the repository:

```bash
git clone https://github.com/<your-username>/urban_sound_monitor.git
cd urban_sound_monitor
```
2. Run the setup script:

```bash
chmod +x setup.sh
./setup.sh
```
This will:
- Update the Pi
- Install Python3, pip, and required system libraries
- Install Python dependencies from requirements.txt
- Create the recordings/ folder
- Optionally copy the systemd service and enable it

## Systemd Service Setup Notes

The urban_sound_monitor.service allows the script to run automatically on boot.
Paths: Ensure ExecStart and WorkingDirectory point to where you cloned the repo.

Example:

```ini
ExecStart=/usr/bin/python3 /home/pi/urban_sound_monitor/urban_sound_monitor.py
WorkingDirectory=/home/pi/urban_sound_monitor
```

Enable and start service:

```bash
sudo cp urban_sound_monitor.service /etc/systemd/system/
sudo systemctl daemon-reexec
sudo systemctl enable --now urban_sound_monitor.service
```

Check logs:

```bash
journalctl -u urban_sound_monitor.service -f
```

- The service automatically restarts if the script crashes.
- See inline comments in urban_sound_monitor.service for fine-tuning. 

## Usage

Run manually for testing:

```bash
python3 urban_sound_monitor.py
```

Outputs:

`recordings/<timestamp>.flac` → Audio file
`recordings/<timestamp>.xml` → Metadata including device ID, timestamp, duration, LAeq

## Device ID

Each unit should have a unique DEVICE_ID in urban_sound_monitor.py (default `USM-001`).
This helps differentiate units when running a volunteer network of devices.
 
## Dependencies

All dependencies are listed in requirements.txt:

```txt
sounddevice>=0.4.6
soundfile>=0.12.1
numpy>=1.24.0
scipy>=1.11.0
```

System libraries required for ALSA/FLAC support:

```bash
sudo apt-get install -y libasound2-dev libsndfile1-dev
```

## License
MIT License – see LICENSE file.

## Additional Notes

This static, offline recorder box is a proof-of-concept with non-calibrated, non-Type microphones capturing raw, unreferenced data. It is not intended, in its current state, for scientific data collection or research in the service of public policy. 

## Future Work

urban_sound_monitor aims to scale decentralized data collection for ambient noise. This script intends to function as a core for later adaptation to more precise applications: 
1. heavy-duty, weatherproof, autonymous offline field recording, similar to existing acoustic loggers.
2. a mobile application to collect ambient sound data continuously from smartphones. This would allow more scalable, decentralized data gathering while preserving the lightweight, low-power design of the current Raspberry Pi implementation.

This project is an offshoot of Connor Lafitte Audio and is in the basic iteration stage. For ideas and feature suggestions, please email connor@connorlafitte.com

******
