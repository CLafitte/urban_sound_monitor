"""
dsp.py
Pure signal-processing helpers for urban_sound_monitor.

No hardware imports (sounddevice/soundfile) live here, so everything in this
module can be unit tested on any machine.
"""

import numpy as np
from scipy.signal import bilinear, lfilter, butter

DEFAULT_FS = 48000


def highpass_filter(x, fs=DEFAULT_FS, cutoff=20.0):
    """Apply 4th-order highpass filter at `cutoff` Hz using float64 precision."""
    x = x.astype(np.float64, copy=False)
    b, a = butter(4, cutoff / (fs / 2), btype="highpass")
    return lfilter(b, a, x)


def a_weighting(fs=DEFAULT_FS):
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


def compute_LAeq(x, fs=DEFAULT_FS):
    """Compute A-weighted equivalent continuous level (dBFS) in float64.

    Returns -inf for effectively silent input.
    """
    x = x.astype(np.float64, copy=False)
    x = highpass_filter(x, fs)
    b_a, a_a = a_weighting(fs)
    x = np.asarray(lfilter(b_a, a_a, x), dtype=np.float64)
    rms = np.sqrt(np.mean(x ** 2))
    if rms < 1e-10:
        return -np.inf  # effectively silence
    return 20 * np.log10(rms)
