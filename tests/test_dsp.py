import numpy as np
import pytest

from dsp import compute_LAeq

FS = 48000
AMPLITUDE = 0.1
BURST_SECONDS = 6  # matches DURATION in the monitor

# IEC 61672 nominal A-weighting values (dB) at octave-band centres.
A_WEIGHT_REF = {
    125: -16.1,
    250: -8.6,
    500: -3.2,
    1000: 0.0,
    2000: 1.2,
    4000: 1.0,
    8000: -1.1,
}


def sine(freq, amplitude=AMPLITUDE, seconds=BURST_SECONDS, fs=FS):
    t = np.arange(int(seconds * fs)) / fs
    return amplitude * np.sin(2 * np.pi * freq * t)


# Allowed deviation (dB) from the nominal value. 8 kHz is looser because the
# bilinear transform warps the response near Nyquist (measured ~-0.6 dB at
# 48 kHz). That is still well inside the IEC 61672 class 1 limits, but it is a
# known systematic error rather than noise: tighten this if the design improves.
TOLERANCE_DB = {8000: 1.0}
DEFAULT_TOLERANCE_DB = 0.5


@pytest.mark.parametrize("freq,a_db", A_WEIGHT_REF.items())
def test_a_weighting_matches_reference(freq, a_db):
    expected = 20 * np.log10(AMPLITUDE / np.sqrt(2)) + a_db
    tol = TOLERANCE_DB.get(freq, DEFAULT_TOLERANCE_DB)
    assert compute_LAeq(sine(freq), FS) == pytest.approx(expected, abs=tol)


def test_full_scale_sine_at_1khz_is_minus_3_dbfs():
    # RMS of a full-scale sine is 1/sqrt(2) -> -3.01 dBFS; A-weight at 1 kHz is 0.
    assert compute_LAeq(sine(1000, amplitude=1.0), FS) == pytest.approx(-3.01, abs=0.1)


def test_level_scales_6_db_per_doubling():
    quiet = compute_LAeq(sine(1000, amplitude=0.05), FS)
    loud = compute_LAeq(sine(1000, amplitude=0.10), FS)
    assert loud - quiet == pytest.approx(6.02, abs=0.1)


def test_silence_returns_minus_inf():
    assert compute_LAeq(np.zeros(BURST_SECONDS * FS), FS) == -np.inf


def test_dc_offset_is_strongly_attenuated():
    # A constant 0.5 offset is -6 dBFS unfiltered. The highpass should remove
    # almost all of it. It is not -inf: filter state starts at zero on every
    # burst, so the step at the start leaves a decaying transient (~-52 dBFS).
    dc = np.full(BURST_SECONDS * FS, 0.5)
    assert compute_LAeq(dc, FS) < -40


def test_accepts_float32_input():
    # sounddevice delivers float32; result must match the float64 path closely.
    x64 = sine(1000)
    assert compute_LAeq(x64.astype(np.float32), FS) == pytest.approx(
        compute_LAeq(x64, FS), abs=0.01
    )


def test_low_frequency_is_heavily_attenuated():
    # 31.5 Hz A-weight is about -39 dB; allow generous tolerance, the point is "very quiet".
    level = compute_LAeq(sine(31.5), FS)
    assert level < 20 * np.log10(AMPLITUDE / np.sqrt(2)) - 30
