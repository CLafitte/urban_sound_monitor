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
import csv
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

# ---------- LOCATION ----------
# Static per-deployment values. This unit is assumed stationary; if units
# become mobile, replace with a GPS read at capture time instead.
SITE_NAME = "Unnamed Site"     # e.g. "5th & Main - NE corner"
DEVICE_LAT = 0.0               # decimal degrees, e.g. 41.8781
DEVICE_LON = 0.0               # decimal degrees, e.g. -87.6298

# ---------- CSV INDEX ----------
CSV_INDEX_FILENAME = "index.csv"   # per-unit running summary of all bursts
CSV_FIELDS = ["timestamp", "site_name", "latitude", "longitude", "laeq_dbfs", "flac_file"]

# ---------- RETENTION ----------
MAX_STORAGE_MB = 500        # delete oldest bursts once OUTPUT_DIR exceeds this
RETENTION_CHECK_EVERY = 10  # run the retention sweep every N loop cycles (not every burst)

# ---------- MIC RECOVERY ----------
MIC_FAILURE_THRESHOLD = 3   # consecutive burst failures before attempting re-detection
MIC_RETRY_BACKOFF = 5       # seconds between re-detection attempts while mic is missing

# ---------- CONFIG VALIDATION ----------
def validate_location_config():
    """Refuse to run with placeholder location values.

    A unit left at defaults would silently tag every burst with a fake
    site name and (0, 0) coordinates, polluting any downstream hotspot
    analysis with unattributable data. Fail loudly instead.
    """
    problems = []
    if SITE_NAME == "Unnamed Site":
        problems.append("SITE_NAME is still the placeholder value")
    if DEVICE_LAT == 0.0 and DEVICE_LON == 0.0:
        problems.append("DEVICE_LAT/DEVICE_LON are still 0.0, 0.0")

    if problems:
        print("[FATAL] Location config not set for this deployment:")
        for p in problems:
            print(f"  - {p}")
        print("  Set SITE_NAME, DEVICE_LAT, and DEVICE_LON before running.")
        exit(1)

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

# ---------- FILTERS ----------
def highpass_filter(x, fs=FS, cutoff=20.0):
    """Apply 4th-order highpass filter at 20 Hz using float64 precision."""
    x = x.astype(np.float64, copy=False)
    b, a = butter(4, cutoff / (fs / 2), btype="highpass")
    return lfilter(b, a, x)

def a_weighting(fs=FS):
    """Design digital A-weighting filter for sample rate fs."""
    f1, f2, f3, f4 = 20.598997, 107.65265, 737.86223, 12194.217
    A1000 = 1.9997
    nums = [(2 * np.pi * f4) ** 2 * (10 ** (A1000 / 20)), 0, 0, 0, 0]
    dens = np.polymul([1, 4 * np.pi * f4, (2 * np.pi * f4) ** 2],
                      [1, 4 * np.pi * f1, (2 * np.pi * f1) ** 2])
    dens = np.polymul(np.polymul(dens, [1, 2 * np.pi * f3]),
                      [1, 2 * np.pi * f2])
    b, a = bilinear(nums, dens, fs)
    return b, a

B_A, A_A = a_weighting(FS)

# ---------- DSP CORE ----------
def compute_LAeq(x):
    """Compute A-weighted equivalent continuous level (dBFS) in float64."""
    x = x.astype(np.float64, copy=False)
    x = highpass_filter(x, FS)
    x = np.asarray(lfilter(B_A, A_A, x), dtype=np.float64)
    rms = np.sqrt(np.mean(x ** 2))
    if rms < 1e-10:
        return -np.inf  # effectively silence
    return 20 * np.log10(rms)

# ---------- CAPTURE ----------
def record_burst(input_device):
    """Record a single burst of audio from USB microphone."""
    rec = sd.rec(int(DURATION * FS), samplerate=FS, channels=1,
                 dtype="float32", device=input_device)
    sd.wait()
    return rec.flatten()

# ---------- XML LOGGING ----------
def write_xml(metadata_path, flac_file, laeq, timestamp):
    """Write XML metadata for one burst, atomically to disk."""
    root = ET.Element("NoiseBurst")
    device = ET.SubElement(root, "Device", id=DEVICE_ID)
    ET.SubElement(device, "Platform").text = platform.platform()

    location = ET.SubElement(device, "Location")
    ET.SubElement(location, "SiteName").text = SITE_NAME
    ET.SubElement(location, "Latitude").text = f"{DEVICE_LAT:.6f}"
    ET.SubElement(location, "Longitude").text = f"{DEVICE_LON:.6f}"

    audio = ET.SubElement(root, "AudioSettings")
    ET.SubElement(audio, "SampleRate").text = str(FS)
    ET.SubElement(audio, "Channels").text = "1"
    ET.SubElement(audio, "BitDepth").text = "FLAC (PCM_24)"

    session = ET.SubElement(root, "Session")
    ET.SubElement(session, "Timestamp").text = timestamp
    ET.SubElement(session, "FlacFile").text = flac_file
    ET.SubElement(session, "Duration").text = str(DURATION)
    ET.SubElement(session, "LAeq_dBFS").text = (
        f"{laeq:.2f}" if np.isfinite(laeq) else "NaN"
    )

    tree = ET.ElementTree(root)
    tmp_path = metadata_path + ".tmp"
    tree.write(tmp_path, encoding="utf-8", xml_declaration=True)
    os.replace(tmp_path, metadata_path)

# ---------- CSV INDEX ----------
def append_csv_index(output_dir, timestamp, laeq, flac_path):
    """Append one row summarizing this burst to the per-unit CSV index.

    Writes the header once, on first creation. This is a flat, greppable
    summary alongside the detailed per-burst XML/FLAC files — not a
    replacement for them.
    """
    csv_path = os.path.join(output_dir, CSV_INDEX_FILENAME)
    write_header = not os.path.exists(csv_path)
    with open(csv_path, "a", newline="") as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(CSV_FIELDS)
        writer.writerow([
            timestamp,
            SITE_NAME,
            f"{DEVICE_LAT:.6f}",
            f"{DEVICE_LON:.6f}",
            f"{laeq:.2f}" if np.isfinite(laeq) else "NaN",
            os.path.basename(flac_path),
        ])

# ---------- RETENTION ----------
def enforce_retention(output_dir=OUTPUT_DIR, max_mb=MAX_STORAGE_MB):
    """Delete oldest (flac, xml) burst pairs until directory usage is under max_mb.

    Pairs are matched by shared basename (timestamp) so a burst's audio and
    metadata are always removed together, never orphaning one or the other.
    """
    try:
        entries = os.listdir(output_dir)
    except OSError as e:
        print(f"[WARN] Retention check could not list {output_dir}: {e}")
        return

    flacs = {os.path.splitext(f)[0]: f for f in entries if f.endswith(".flac")}
    xmls = {os.path.splitext(f)[0]: f for f in entries if f.endswith(".xml")}
    stems = sorted(
        set(flacs) & set(xmls),
        key=lambda s: os.path.getmtime(os.path.join(output_dir, flacs[s])),
    )

    all_files = list(flacs.values()) + list(xmls.values())
    usage = sum(os.path.getsize(os.path.join(output_dir, f)) for f in all_files) / 1e6
    if usage <= max_mb:
        return

    print(f"[INFO] Retention: {usage:.1f} MB used, over {max_mb} MB limit — trimming oldest bursts")
    removed = 0
    for stem in stems:
        if usage <= max_mb:
            break
        for fname in (flacs[stem], xmls[stem]):
            path = os.path.join(output_dir, fname)
            try:
                size = os.path.getsize(path)
                os.remove(path)
                usage -= size / 1e6
            except OSError as e:
                print(f"[WARN] Could not remove {path}: {e}")
        removed += 1
    print(f"[INFO] Retention: removed {removed} burst(s), now ~{usage:.1f} MB")

# ---------- SELF-CHECK ----------
def self_check(input_device):
    """Perform a quick system check before entering the monitoring loop."""
    print("[SELF-CHECK] Running preflight diagnostics...")

    results = {"mic": False, "dsp": False, "disk": False}

    # Generated once, up front, so a failure in one test can't leave
    # a later test referencing an undefined variable.
    test_signal = np.random.randn(int(0.5 * FS)) * 0.01

    # --- Microphone test ---
    try:
        test = sd.rec(int(0.5 * FS), samplerate=FS, channels=1,
                      dtype="float32", device=input_device)
        sd.wait()
        if np.abs(test).max() > 1e-5:
            results["mic"] = True
        else:
            print("[WARN] Microphone captured near-silence. Check input level.")
    except Exception as e:
        print(f"[ERROR] Mic test failed: {e}")

    # --- DSP test ---
    try:
        laeq = compute_LAeq(test_signal)
        if np.isfinite(laeq):
            results["dsp"] = True
        else:
            print("[WARN] DSP pipeline returned NaN or -inf.")
    except Exception as e:
        print(f"[ERROR] DSP pipeline failed: {e}")

    # --- Disk test ---
    try:
        tmp_flac = os.path.join(OUTPUT_DIR, "_test.flac.tmp")
        sf.write(tmp_flac, test_signal, FS, format="FLAC", subtype="PCM_24")
        os.replace(tmp_flac, tmp_flac.replace(".tmp", ""))
        os.remove(tmp_flac.replace(".tmp", ""))
        free_mb = os.statvfs(OUTPUT_DIR).f_bavail * os.statvfs(OUTPUT_DIR).f_frsize / 1e6
        print(f"[INFO] Disk space available: {free_mb:.1f} MB")
        results["disk"] = True
    except Exception as e:
        print(f"[ERROR] Disk write test failed: {e}")

    # --- Summary ---
    if all(results.values()):
        print("[SELF-CHECK] PASSED: mic=OK, dsp=OK, disk=OK\n")
        return True
    else:
        print(f"[SELF-CHECK] FAILED: {results}\n")
        return False

# ---------- MAIN LOOP ----------
def acquire_device():
    """Block, retrying with backoff, until a USB microphone is found."""
    while True:
        try:
            return find_usb_microphone()
        except RuntimeError as e:
            print(f"[WARN] {e} — retrying in {MIC_RETRY_BACKOFF}s")
            time.sleep(MIC_RETRY_BACKOFF)


def main():
    validate_location_config()

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print("Starting urban sound monitor loop...")

    input_device = acquire_device()

    if not self_check(input_device):
        print("[FATAL] Preflight failed. Exiting.")
        exit(1)

    consecutive_failures = 0
    cycle_count = 0

    while True:
        try:
            burst = record_burst(input_device)
            laeq = compute_LAeq(burst)

            timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
            flac_path = os.path.join(OUTPUT_DIR, f"{timestamp}.flac")
            xml_path = os.path.join(OUTPUT_DIR, f"{timestamp}.xml")

            # Save as FLAC atomically
            tmp_flac = flac_path + ".tmp"
            sf.write(tmp_flac, burst, FS, format="FLAC", subtype="PCM_24")
            os.replace(tmp_flac, flac_path)

            write_xml(xml_path, flac_path, laeq, timestamp)

            try:
                append_csv_index(OUTPUT_DIR, timestamp, laeq, flac_path)
            except OSError as e:
                print(f"[WARN] Could not update CSV index: {e}")

            msg = (
                f"[{timestamp}] LAeq (dBFS): {laeq:.2f}"
                if np.isfinite(laeq)
                else f"[{timestamp}] Silence detected."
            )
            print(msg)
            consecutive_failures = 0

        except Exception as e:
            consecutive_failures += 1
            print(f"[ERROR] {datetime.utcnow().isoformat()} - {str(e)} "
                  f"(consecutive failures: {consecutive_failures})")

            if consecutive_failures >= MIC_FAILURE_THRESHOLD:
                print("[WARN] Repeated capture failures — assuming the microphone "
                      "was disconnected. Attempting re-detection...")
                input_device = acquire_device()
                print("[INFO] Microphone re-acquired. Resuming monitoring.")
                consecutive_failures = 0

        cycle_count += 1
        if cycle_count % RETENTION_CHECK_EVERY == 0:
            enforce_retention()

        # Wait for the next burst cycle
        sleep_time = max(0, INTERVAL - DURATION)
        time.sleep(sleep_time)


if __name__ == "__main__":
    main()
