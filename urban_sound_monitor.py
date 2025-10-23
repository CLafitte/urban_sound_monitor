#!/usr/bin/env python3
"""
urban_sound_monitor.py
Lightweight ambient noise logger for Raspberry Pi + driverless USB mic.
Captures 6-second bursts every 60 seconds, computes LAeq (A-weighted, dBFS),
and stores FLAC audio with XML metadata.
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
        if dev["max_input_channels"] > 0 and any(
            key in dev["name"].lower() for key in ("usb", "mic")
        ):
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
    b, a = butter(4, cutoff / (fs / 2), btype="highpass")
    return lfilter(b, a, x)

def a_weighting(fs=FS):
    """Des
    
