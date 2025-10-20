#!/usr/bin/env python3
"""
urban_sound_monitor.py
Lightweight ambient noise logger for Raspberry Pi + driverless USB mic.
Captures 6-second bursts every 60 seconds, computes LAeq (A-weighted, dBFS),
and stores FLAC audio with XML metadata.
Now uses float64 precision throughout DSP for improved low-level accuracy.
"""

import sounddevice as sd
import soundfile as sf
import numpy as np
from scipy.signal import bilinear, lfilter, butter
import xml.etree.ElementTree as ET
from datetime import datetime
import platform
import os
import time

# ---------- CONFIG ----------
DEVICE_ID = "USM-001"
OUTPUT_DIR = "recordings"
DURATION = 6            # seconds per burst
INTERVAL = 60           # seconds between burst starts
FS = 48000              # Hz sample rate

os.makedirs(OUTPUT_DIR, exist_ok=True)

# ---------- DEVICE DETECTION ----------
def find_usb_microphone():
    """Detect first USB microphone input device by name."""
    devices = sd.query_devices()
    for idx, dev in enumerate(devices):
        if dev['max_input_channels'] > 0 and 'usb' in dev['name'].lower():
            print(f"[INFO] Using USB mic: {dev['name']} (index {idx})")
            return idx
    raise RuntimeError("No USB microphone detected.")

try:
    INPUT_DEVICE = find_usb_microphone()
except RuntimeError as e:
    print(f"[FATAL] {e}")
    exit(1)

# ---------- FILTERS ----------
def highpass_filter(x, fs=FS, cutoff=20.0):
    """Apply 4th-order highpass filter at 20 Hz using float64 precision."""
    x = x.astype(np.float64, copy=False)
    b, a = butter(4, cutoff/(fs/2), btype='highpass')
    return lfilter(b, a, x)

def a_weighting(fs=FS):
    """Design digital A-weighting filter for sample rate fs."""
    f1, f2, f3, f4 = 20.598997, 107.65265, 737.86223, 12194.217
    A1000 = 1.9997
    nums = [(2*np.pi*f4)**2 * (10**(A1000/20)), 0, 0, 0, 0]
    dens = np.polymul([1, 4*np.pi*f4, (2*np.pi*f4)**2],
                      [1, 4*np.pi*f1, (2*np.pi*f1)**2])
    dens = np.polymul(np.polymul(dens, [1, 2*np.pi*f3]),
                      [1, 2*np.pi*f2])
    b, a = bilinear(nums, dens, fs)
    return b, a

B_A, A_A = a_weighting(FS)

# ---------- DSP CORE ----------
def compute_LAeq(x):
    """Compute A-weighted equivalent continuous level (dBFS) in float64."""
    # Convert to float64 for all DSP math
    x = x.astype(np.float64, copy=False)

    # Apply highpass and A-weighting filters
    x = highpass_filter(x, FS)
    x = lfilter(B_A, A_A, x)

    # Compute RMS and convert to dBFS
    rms = np.sqrt(np.mean(x**2))
    if rms < 1e-10:
        return -np.inf  # effectively silence
    return 20 * np.log10(rms)

# ---------- CAPTURE ----------
def record_burst():
    """Record a single burst of audio from USB microphone."""
    rec = sd.rec(int(DURATION * FS), samplerate=FS, channels=1,
                 dtype='float32', device=INPUT_DEVICE)
    sd.wait()
    return rec.flatten()

# ---------- XML LOGGING ----------
def write_xml(metadata_path, wav_file, laeq):
    root = ET.Element("NoiseBurst")
    ET.SubElement(root, "Device", id=DEVICE_ID).text = platform.platform()
    audio = ET.SubElement(root, "AudioSettings")
    ET.SubElement(audio, "SampleRate").text = str(FS)
    ET.SubElement(audio, "Channels").text = "1"
    ET.SubElement(audio, "BitDepth").text = "FLAC (float32)"
    session = ET.SubElement(root, "Session")
    now = datetime.utcnow().isoformat() + "Z"
    ET.SubElement(session, "Timestamp").text = now
    ET.SubElement(session, "WavFile").text = wav_file
    ET.SubElement(session, "Duration").text = str(DURATION)
    ET.SubElement(session, "LAeq_dBFS").text = f"{laeq:.2f}" if np.isfinite(laeq) else "NaN"
    tree = ET.ElementTree(root)
    tree.write(metadata_path, encoding="utf-8", xml_declaration=True)

# ---------- MAIN LOOP ----------
if __name__ == "__main__":
    print("Starting urban sound monitor loop...")

    while True:
        try:
            burst = record_burst()
            laeq = compute_LAeq(burst)

            timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
            wav_path = os.path.join(OUTPUT_DIR, f"{timestamp}.flac")
            xml_path = os.path.join(OUTPUT_DIR, f"{timestamp}.xml")

            # Save as FLAC (float32 to save space)
            sf.write(wav_path, burst, FS, format='FLAC', subtype='PCM_24')

            write_xml(xml_path, wav_path, laeq)

            msg = f"[{timestamp}] LAeq (dBFS): {laeq:.2f}" if np.isfinite(laeq) else f"[{timestamp}] Silence detected."
            print(msg)

        except Exception as e:
            print(f"[ERROR] {datetime.utcnow().isoformat()} - {str(e)}")
        
        # Wait for the next burst cycle
        sleep_time = max(0, INTERVAL - DURATION)
        time.sleep(sleep_time)
