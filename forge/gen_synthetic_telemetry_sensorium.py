#!/usr/bin/env python3
"""
Generate Synthetic Sensorium Telemetry

Creates realistic sensor telemetry samples for adaptive sampling rate reflex training.
Each sample represents a 1-second observation window with computed features.
"""

import pandas as pd
import numpy as np
import sys
from scipy import signal as scipy_signal
from scipy.fft import fft, fftfreq


def compute_telemetry_features(signal_window, sampling_rate=100.0, noise_std=0.1):
    """
    Compute telemetry features from a signal window.

    Args:
        signal_window: 1D array of signal samples (assumed 1 second at sampling_rate Hz)
        sampling_rate: Current sampling rate (Hz)
        noise_std: Standard deviation of noise in signal

    Returns:
        Dictionary of telemetry features
    """
    n_samples = len(signal_window)

    # Basic statistics
    signal_mean = np.mean(signal_window)
    signal_variance = np.var(signal_window)

    # FFT for frequency analysis
    freqs = fftfreq(n_samples, 1.0 / sampling_rate)
    fft_vals = np.abs(fft(signal_window))

    # Only consider positive frequencies
    pos_mask = freqs > 0
    freqs_pos = freqs[pos_mask]
    fft_pos = fft_vals[pos_mask]

    # Dominant frequency (ignore DC component)
    if len(fft_pos) > 0 and np.sum(fft_pos) > 0:
        dominant_idx = np.argmax(fft_pos)
        dominant_freq_hz = freqs_pos[dominant_idx]

        # Energy ratio (dominant peak vs total)
        total_energy = np.sum(fft_pos ** 2)
        dominant_energy = fft_pos[dominant_idx] ** 2
        freq_energy_ratio = dominant_energy / total_energy if total_energy > 0 else 0.0
    else:
        dominant_freq_hz = 0.0
        freq_energy_ratio = 0.0

    # Zero crossings (activity metric)
    zero_crossings = np.sum(np.diff(np.sign(signal_window - signal_mean)) != 0)
    zero_crossings_per_sec = zero_crossings  # window is 1 second

    # Sample age (simulated - random for synthetic data)
    sample_age_ms = np.random.uniform(5, 50)

    # Reconstruction error (simulated feedback - starts near zero)
    reconstruction_error_ewma = np.random.uniform(0.01, 0.1) * signal_variance ** 0.5

    # Power budget (simulated - varies between samples)
    power_budget_pct = np.random.uniform(30, 100)

    # Event rate (significant threshold crossings)
    threshold = signal_mean + 1.5 * np.sqrt(signal_variance)
    events = np.sum(signal_window > threshold)
    event_rate_hz = events  # window is 1 second

    # SNR estimate
    signal_power = signal_variance
    noise_power = noise_std ** 2
    if noise_power > 0:
        snr = signal_power / noise_power
        signal_snr_db = 10 * np.log10(max(snr, 1e-6))
    else:
        signal_snr_db = 40.0  # high SNR if no noise

    return {
        'signal_variance': signal_variance,
        'signal_mean': signal_mean,
        'dominant_freq_hz': dominant_freq_hz,
        'freq_energy_ratio': freq_energy_ratio,
        'zero_crossings_per_sec': zero_crossings_per_sec,
        'sample_age_ms': sample_age_ms,
        'reconstruction_error_ewma': reconstruction_error_ewma,
        'power_budget_pct': power_budget_pct,
        'event_rate_hz': event_rate_hz,
        'signal_snr_db': signal_snr_db,
    }


def generate_steady_workload(n_samples=800):
    """
    Steady workload: single sinusoid with consistent frequency and amplitude.
    """
    samples = []
    sampling_rate = 100.0  # Hz (for generating signals)

    for i in range(n_samples):
        # Generate 1-second signal window
        t = np.linspace(0, 1.0, int(sampling_rate))

        # Sinusoid with fixed frequency (0.5-10 Hz range)
        freq = np.random.uniform(0.5, 10.0)
        amplitude = np.random.uniform(1.0, 5.0)

        # Clean signal
        clean_signal = amplitude * np.sin(2 * np.pi * freq * t)

        # Add noise (SNR 20-40 dB)
        snr_db = np.random.uniform(20, 40)
        signal_power = amplitude ** 2 / 2
        noise_power = signal_power / (10 ** (snr_db / 10))
        noise_std = np.sqrt(noise_power)
        noise = np.random.normal(0, noise_std, len(t))

        signal_window = clean_signal + noise

        # Compute telemetry
        features = compute_telemetry_features(signal_window, sampling_rate, noise_std)
        samples.append(features)

    return pd.DataFrame(samples)


def generate_bursty_workload(n_samples=600):
    """
    Bursty workload: alternating quiet periods and high-activity bursts.
    """
    samples = []
    sampling_rate = 100.0

    for i in range(n_samples):
        t = np.linspace(0, 1.0, int(sampling_rate))

        # Burst phase (alternating every ~50 samples)
        phase = (i // 50) % 2

        if phase == 0:  # Quiet period
            freq = np.random.uniform(0.5, 2.0)
            amplitude = np.random.uniform(0.5, 1.5)
            snr_db = np.random.uniform(30, 40)
        else:  # Burst period
            freq = np.random.uniform(5.0, 20.0)
            amplitude = np.random.uniform(3.0, 8.0)
            snr_db = np.random.uniform(15, 30)

        # Envelope modulation (sudden bursts)
        envelope = np.ones_like(t)
        if phase == 1:
            burst_start = np.random.uniform(0.2, 0.5)
            burst_width = np.random.uniform(0.2, 0.4)
            envelope = np.where((t >= burst_start) & (t < burst_start + burst_width), 1.0, 0.2)

        clean_signal = amplitude * envelope * np.sin(2 * np.pi * freq * t)

        signal_power = np.var(clean_signal)
        noise_power = signal_power / (10 ** (snr_db / 10))
        noise_std = np.sqrt(noise_power)
        noise = np.random.normal(0, noise_std, len(t))

        signal_window = clean_signal + noise

        features = compute_telemetry_features(signal_window, sampling_rate, noise_std)
        samples.append(features)

    return pd.DataFrame(samples)


def generate_adversarial_workload(n_samples=600):
    """
    Adversarial workload: non-stationary frequency sweeps, random SNR, sudden events.
    """
    samples = []
    sampling_rate = 100.0

    for i in range(n_samples):
        t = np.linspace(0, 1.0, int(sampling_rate))

        # Frequency sweep (linear chirp)
        f0 = np.random.uniform(0.5, 5.0)
        f1 = np.random.uniform(5.0, 25.0)
        if np.random.rand() < 0.5:
            f0, f1 = f1, f0  # Reverse sweep

        amplitude = np.random.uniform(1.0, 6.0)

        # Chirp signal
        clean_signal = amplitude * scipy_signal.chirp(t, f0, 1.0, f1, method='linear')

        # Add sudden events (impulses)
        if np.random.rand() < 0.3:
            event_idx = np.random.randint(10, len(t) - 10)
            clean_signal[event_idx] += amplitude * 3.0

        # Random SNR
        snr_db = np.random.uniform(10, 40)
        signal_power = np.var(clean_signal)
        noise_power = signal_power / (10 ** (snr_db / 10))
        noise_std = np.sqrt(noise_power)
        noise = np.random.normal(0, noise_std, len(t))

        signal_window = clean_signal + noise

        features = compute_telemetry_features(signal_window, sampling_rate, noise_std)
        samples.append(features)

    return pd.DataFrame(samples)


def generate_mixed_workload(output_path: str):
    """
    Generate mixed workload combining all three patterns.
    """
    print("Generating synthetic sensorium telemetry...")

    steady = generate_steady_workload(800)
    print(f"  Generated {len(steady)} steady samples")

    bursty = generate_bursty_workload(600)
    print(f"  Generated {len(bursty)} bursty samples")

    adversarial = generate_adversarial_workload(600)
    print(f"  Generated {len(adversarial)} adversarial samples")

    # Combine
    mixed = pd.concat([steady, bursty, adversarial], ignore_index=True)

    # Shuffle
    mixed = mixed.sample(frac=1, random_state=42).reset_index(drop=True)

    # Save
    mixed.to_csv(output_path, index=False)
    print(f"✓ Saved {len(mixed)} samples to {output_path}")

    # Print statistics
    print("\n=== Sample Statistics ===")
    print(mixed.describe())

    print("\n=== Feature Ranges ===")
    for col in mixed.columns:
        print(f"{col:30s}: [{mixed[col].min():8.2f}, {mixed[col].max():8.2f}]")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: gen_synthetic_telemetry_sensorium.py <output.csv>")
        sys.exit(1)

    output_path = sys.argv[1]
    generate_mixed_workload(output_path)
