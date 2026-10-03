# Urban Sound Monitor

A proof-of-concept ambient field noise recorder for Raspberry Pi using any driverless USB microphone. It captures short bursts of urban sound, computes A-weighted LAeq levels, and saves audio and metadata for offline processing. Built for expansion into embedded applications for ecological research and urban planning.

## Features

- Captures 6-second bursts every 60 seconds
- Computes A-weighted LAeq (dBFS) per burst
- Stores FLAC audio with XML metadata
- Detects USB microphones dynamically

## Architecture

```
systemd: urban_sound_monitor.service (venv Python, Restart=always)
   |
   v
urban_sound_monitor.py -- capture, self-check, file output
   |                  \
   | calls             v
   v               recordings/*.flac + *.xml
dsp.py -- high-pass, A-weighting, LAeq (no hardware imports)
   ^
   | tested by
tests/test_dsp.py -- pytest, no microphone needed
```

## Installation

```bash
git clone https://github.com/<your-username>/urban_sound_monitor.git
cd urban_sound_monitor
chmod +x setup.sh && ./setup.sh
```

The setup script updates package lists (a full `apt-get upgrade` stays a manual step), installs Python3, pip, venv and system libraries, creates `venv/` with the dependencies from requirements.txt plus the recordings/ folder, and optionally installs and enables the systemd service.

## Systemd Service

The service runs the script on boot and restarts it if it crashes. Point ExecStart and WorkingDirectory at your clone, using the venv's Python. `dsp.py` must sit beside the script.

```ini
ExecStart=/home/pi/urban_sound_monitor/venv/bin/python3 /home/pi/urban_sound_monitor/urban_sound_monitor.py
WorkingDirectory=/home/pi/urban_sound_monitor
```

```bash
sudo cp urban_sound_monitor.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now urban_sound_monitor.service
journalctl -u urban_sound_monitor.service -f   # logs
```

## Usage

Run manually with `venv/bin/python3 urban_sound_monitor.py`. Each burst writes `recordings/<timestamp>.flac` (audio) and `recordings/<timestamp>.xml` (device ID, timestamp, duration, LAeq).

## Configuration

Edit the config block in urban_sound_monitor.py:

- `DEVICE_ID`: unique per unit (default `USM-001`), to tell units apart in a volunteer network.
- `SITE_NAME`, `DEVICE_LAT`, `DEVICE_LON`: units are stationary and geotagged so readings aggregate into hotspot maps. **Set these before first run** or the script refuses to start.

## Testing

`tests/test_dsp.py` checks A-weighting against IEC 61672 reference values, level scaling, silence, DC rejection and float32 input. No microphone or PortAudio is required.

```bash
venv/bin/pip install -r requirements-dev.txt
venv/bin/pytest
```

Known limits: 8 kHz reads about 0.6 dB low (bilinear warping), and filter state resets every burst, causing a startup transient.

## Dependencies

requirements.txt holds runtime packages (sounddevice, soundfile, numpy, scipy). requirements-dev.txt adds pytest and isn't needed on deployed units. System libraries for ALSA/FLAC:

```bash
sudo apt-get install -y libasound2-dev libsndfile1-dev
```

## License

MIT License – see LICENSE file.

## Additional Notes

This static, offline recorder is a proof-of-concept with non-calibrated, non-Type microphones capturing raw, unreferenced data. In its current state it is not intended for scientific data collection or research in the service of public policy.

## Future Work

urban_sound_monitor aims to scale decentralized ambient noise collection, as a core for more precise applications:

1. Heavy-duty, weatherproof, autonomous offline field recorders, similar to existing acoustic loggers.
2. A mobile app collecting ambient sound continuously from smartphones, for more scalable, decentralized gathering while keeping the low-power design of the Raspberry Pi version.

This project is an offshoot of Connor Lafitte Audio and is in the basic iteration stage. For ideas and feature suggestions, please email connor@connorlafitte.com
