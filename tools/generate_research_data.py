"""Pure deterministic synthetic teaching tables for research display templates.

These examples are independently designed, not digitized from publications or
measured from people, animals, instruments, or fluorophores. They make no
scientific performance claim. Importing this module or calling its functions
does not write files, contact a network, or start Origin. Export, provenance
registration, and rendering are separate explicit caller responsibilities.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _teaching_frame(parts: list[pd.DataFrame], name: str) -> pd.DataFrame:
    frame = pd.concat(parts, ignore_index=True)
    frame.attrs.update(data_origin="synthetic_teaching_data", scientific_claim="none", dataset_name=name)
    return frame


def flim_phasor_data() -> pd.DataFrame:
    """Return 3 x 180 synthetic precomputed G/S points, not measured FLIM results.

    The three clouds are designed geometric examples. Their labels do not name
    real fluorophores, and their positions do not claim fitted lifetimes or
    mixture fractions. A local fixed seed controls all illustrative variation.
    """
    rng = np.random.default_rng(3031)
    parts = []
    for label, center_g, center_s in (
        ("Demo A", 0.25, 0.28), ("Demo B", 0.50, 0.40), ("Demo C", 0.76, 0.27)
    ):
        noise = rng.normal(size=(180, 2))
        parts.append(pd.DataFrame({
            "G": center_g + 0.025 * noise[:, 0],
            "S": center_s + 0.015 * (0.25 * noise[:, 0] + noise[:, 1]),
            "Group": label,
        }))
    return _teaching_frame(parts, "synthetic_flim_phasor")


def signal_stack_data() -> pd.DataFrame:
    """Return eight synthetic channels on a 1001-point, 0-4 second time grid.

    Designed oscillations span 8-14 Hz and share a brief artificial event near
    1.53 seconds. Small locally seeded nonperiodic noise provides texture. These
    are not real scalp recordings, electrode locations, or detected physiology.
    """
    rng = np.random.default_rng(3032)
    time = np.linspace(0.0, 4.0, 1001)
    frequencies = np.linspace(8.0, 14.0, 8)
    common_event = (
        11.0 * np.exp(-0.5 * ((time - 1.53) / 0.055) ** 2)
        - 5.5 * np.exp(-0.5 * ((time - 1.70) / 0.075) ** 2)
    )
    parts = []
    for channel, frequency in enumerate(frequencies):
        phase = channel * 0.36
        signal = (
            (2.7 + 0.12 * channel) * np.sin(2.0 * np.pi * frequency * time + phase)
            + 0.6 * np.sin(2.0 * np.pi * 1.7 * time + phase)
            + (0.85 + 0.04 * channel) * common_event
            + rng.normal(0.0, 0.22, len(time))
        )
        parts.append(pd.DataFrame({
            "Time (s)": time,
            "Channel": f"Demo channel {channel + 1:02d}",
            "Amplitude (uV)": signal,
        }))
    frame = _teaching_frame(parts, "synthetic_signal_stack")
    frame.attrs["designed_channel_frequencies_hz"] = tuple(float(value) for value in frequencies)
    return frame


def event_response_data() -> pd.DataFrame:
    """Return two synthetic responses with deliberately artificial intervals.

    The 401-point grid spans -0.2 to 0.8 seconds. Both response curves and their
    asymmetric bounds are authored mathematical examples, not estimated means,
    SEMs, confidence intervals, or effects from an experimental population.
    The interval label must remain 'Illustrative interval (not CI)' when used.
    """
    rng = np.random.default_rng(3033)
    time = np.linspace(-0.2, 0.8, 401)
    parts = []
    for condition in range(2):
        shift = condition * 0.035
        mean = (
            -2.4 * np.exp(-0.5 * ((time - 0.105 - shift) / 0.035) ** 2)
            + (5.8 - 1.4 * condition) * np.exp(-0.5 * ((time - 0.305 - shift) / 0.070) ** 2)
            + 0.10 * np.sin(2.0 * np.pi * 1.6 * time)
            + rng.normal(0.0, 0.035, len(time))
        )
        lower_width = 0.30 + condition * 0.08 + 0.45 * np.exp(-0.5 * ((time - 0.28) / 0.14) ** 2)
        upper_width = lower_width + 0.18 + 0.05 * np.exp(-0.5 * ((time - 0.34) / 0.17) ** 2)
        parts.append(pd.DataFrame({
            "Time (s)": time,
            "Condition": f"Demo condition {'AB'[condition]}",
            "Mean (uV)": mean,
            "Lower (uV)": mean - lower_width,
            "Upper (uV)": mean + upper_width,
        }))
    frame = _teaching_frame(parts, "synthetic_event_response")
    frame.attrs["interval_label"] = "Illustrative interval (not CI)"
    frame.attrs["interval_definition"] = "authored_asymmetric_display_bounds_not_statistical_estimates"
    return frame


def event_raster_data() -> pd.DataFrame:
    """Return synthetic, pre-generated events for 40 explicitly listed trials.

    These teaching events are not detected spikes or experimental observations.
    Four declared trials contain only a blank-time inventory row; no zero event
    is substituted for the blank. Each remaining trial contains locally seeded
    background and concentrated event times in -0.2 to 0.8 seconds. Rows follow
    trial number and then increasing time; no PSTH, rate, or statistic is derived.
    """
    rng = np.random.default_rng(3034)
    empty_trials = {5, 16, 28, 39}
    rows = []
    for trial in range(1, 41):
        condition = "Demo condition A" if trial <= 20 else "Demo condition B"
        trial_id = f"Demo trial {trial:02d}"
        if trial in empty_trials:
            rows.append({"Time (s)": None, "Trial": trial_id, "Condition": condition})
            continue
        background = rng.uniform(-0.2, 0.8, 4)
        alpha, beta = (2.0, 5.0) if trial <= 20 else (3.0, 3.0)
        concentrated = 0.02 + 0.45 * rng.beta(alpha, beta, 5 + trial % 7)
        for event_time in np.sort(np.concatenate((background, concentrated))):
            rows.append({"Time (s)": float(event_time), "Trial": trial_id, "Condition": condition})
    frame = _teaching_frame([pd.DataFrame(rows)], "synthetic_event_raster")
    frame.attrs["explicit_empty_trial_ids"] = tuple(
        f"Demo trial {trial:02d}" for trial in sorted(empty_trials)
    )
    return frame


def time_frequency_data() -> pd.DataFrame:
    """Return an authored 81-frequency x 121-time power illustration.

    The 3-43 Hz / -0.4 to 1.2 second cells are supplied teaching values in dB,
    not an FFT, STFT, wavelet result, or baseline correction of EEG recordings.
    Two smooth authored regions plus locally seeded variation demonstrate
    physical axes without inventing participant or instrument measurements.
    """
    rng = np.random.default_rng(20261019)
    time = np.linspace(-0.4, 1.2, 121)
    frequency = np.linspace(3.0, 43.0, 81)
    xx, yy = np.meshgrid(time, frequency)
    values = (
        0.12 * rng.normal(size=xx.shape)
        + 6.8 * np.exp(-((xx - 0.3) / 0.14) ** 2 - ((yy - 23) / 4.2) ** 2)
        + 3.6 * np.exp(-((xx - 0.7) / 0.25) ** 2 - ((yy - 9) / 2.5) ** 2)
        - 1.2 * np.exp(-((xx - 0.5) / 0.28) ** 2 - ((yy - 36) / 3.5) ** 2)
    )
    frame = _teaching_frame([pd.DataFrame({
        "Time (s)": np.tile(time, len(frequency)),
        "Frequency (Hz)": np.repeat(frequency, len(time)),
        "Power (dB)": values.ravel(),
    })], "synthetic_time_frequency")
    frame.attrs["processing"] = "authored_grid_not_a_transform_of_recorded_signals"
    frame.attrs["grid_shape"] = (81, 121)
    return frame
