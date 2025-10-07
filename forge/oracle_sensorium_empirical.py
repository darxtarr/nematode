#!/usr/bin/env python3
"""
Empirical Oracle for Sensorium Adaptive Sampling

For each synthetic signal, sweep all sampling rates and measure actual RMSE + energy.
Labels each sample with the empirically optimal sampling rate.

This is computationally intensive but gives ground truth.
"""

import pandas as pd
import numpy as np
import sys
from scipy import signal as scipy_signal
from scipy.fft import fft, fftfreq
from scipy import interpolate


# Objective function weights
ALPHA = 1.0     # RMSE weight (primary metric - voltage units)
BETA = 0.05     # Energy weight (mJ penalty - makes high rates expensive)
GAMMA = 0.0001  # Staleness weight (ms penalty - minor tie-breaker)

# Available sampling rates
SAMPLING_RATES = [1, 2, 5, 10, 20, 50, 100]

# Signal generation parameters (same as gen_synthetic_telemetry_sensorium.py)
GROUND_TRUTH_RATE = 100.0  # Hz (high rate for ground truth)
WINDOW_DURATION = 1.0  # seconds


def compute_telemetry_features(signal_window, sampling_rate=100.0, noise_std=0.1):
    """Compute telemetry features from a signal window (same as generator)."""
    n_samples = len(signal_window)

    signal_mean = np.mean(signal_window)
    signal_variance = np.var(signal_window)

    # FFT analysis
    freqs = fftfreq(n_samples, 1.0 / sampling_rate)
    fft_vals = np.abs(fft(signal_window))

    pos_mask = freqs > 0
    freqs_pos = freqs[pos_mask]
    fft_pos = fft_vals[pos_mask]

    if len(fft_pos) > 0 and np.sum(fft_pos) > 0:
        dominant_idx = np.argmax(fft_pos)
        dominant_freq_hz = freqs_pos[dominant_idx]
        total_energy = np.sum(fft_pos ** 2)
        dominant_energy = fft_pos[dominant_idx] ** 2
        freq_energy_ratio = dominant_energy / total_energy if total_energy > 0 else 0.0
    else:
        dominant_freq_hz = 0.0
        freq_energy_ratio = 0.0

    zero_crossings = np.sum(np.diff(np.sign(signal_window - signal_mean)) != 0)
    zero_crossings_per_sec = zero_crossings

    sample_age_ms = np.random.uniform(5, 50)
    reconstruction_error_ewma = np.random.uniform(0.01, 0.1) * signal_variance ** 0.5
    power_budget_pct = np.random.uniform(30, 100)

    threshold = signal_mean + 1.5 * np.sqrt(signal_variance)
    events = np.sum(signal_window > threshold)
    event_rate_hz = events

    signal_power = signal_variance
    noise_power = noise_std ** 2
    if noise_power > 0:
        snr = signal_power / noise_power
        signal_snr_db = 10 * np.log10(max(snr, 1e-6))
    else:
        signal_snr_db = 40.0

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


def sample_signal(ground_truth_signal, ground_truth_times, target_rate):
    """
    Sample a ground truth signal at a lower rate and reconstruct via interpolation.

    Returns:
        sampled_times: Times at which samples were taken
        sampled_values: Signal values at those times
        reconstructed_signal: Signal reconstructed at ground truth resolution
    """
    # Sample at target rate
    n_samples = int(target_rate * WINDOW_DURATION)
    if n_samples < 2:
        n_samples = 2  # Need at least 2 points for interpolation

    sampled_times = np.linspace(0, WINDOW_DURATION, n_samples)
    sampled_values = np.interp(sampled_times, ground_truth_times, ground_truth_signal)

    # Reconstruct at ground truth resolution
    interp_func = interpolate.interp1d(sampled_times, sampled_values, kind='linear', fill_value='extrapolate')
    reconstructed_signal = interp_func(ground_truth_times)

    return sampled_times, sampled_values, reconstructed_signal


def compute_objective(ground_truth_signal, reconstructed_signal, sampling_rate):
    """
    Compute objective function J = α·RMSE + β·energy + γ·staleness

    Args:
        ground_truth_signal: High-resolution ground truth
        reconstructed_signal: Signal reconstructed from samples
        sampling_rate: Sampling rate used (Hz)

    Returns:
        J: Objective value
        rmse: Reconstruction error
        energy: Energy cost
        staleness: Staleness penalty
    """
    # RMSE
    rmse = np.sqrt(np.mean((ground_truth_signal - reconstructed_signal) ** 2))

    # Energy (mJ) - proportional to sampling rate
    # Assume 1 mJ per sample (realistic for sensor ADC + processing)
    energy = sampling_rate * 1.0  # mJ per second

    # Staleness (ms) - max time between samples
    staleness = 1000.0 / sampling_rate if sampling_rate > 0 else 1000.0

    # Objective
    J = ALPHA * rmse + BETA * energy + GAMMA * staleness

    return J, rmse, energy, staleness


def find_optimal_sampling_rate(ground_truth_signal, ground_truth_times):
    """
    Sweep all sampling rates and find the one with minimum objective.

    Returns:
        optimal_rate: Best sampling rate (Hz)
        results: Dictionary with per-rate metrics
    """
    results = {}

    for rate in SAMPLING_RATES:
        _, _, reconstructed = sample_signal(ground_truth_signal, ground_truth_times, rate)
        J, rmse, energy, staleness = compute_objective(ground_truth_signal, reconstructed, rate)

        results[rate] = {
            'J': J,
            'rmse': rmse,
            'energy': energy,
            'staleness': staleness,
        }

    # Find rate with minimum J
    optimal_rate = min(results.keys(), key=lambda r: results[r]['J'])

    return optimal_rate, results


def generate_signal_steady():
    """Generate steady sinusoid signal."""
    t = np.linspace(0, WINDOW_DURATION, int(GROUND_TRUTH_RATE))
    freq = np.random.uniform(0.5, 10.0)
    amplitude = np.random.uniform(1.0, 5.0)
    clean_signal = amplitude * np.sin(2 * np.pi * freq * t)

    snr_db = np.random.uniform(20, 40)
    signal_power = amplitude ** 2 / 2
    noise_power = signal_power / (10 ** (snr_db / 10))
    noise_std = np.sqrt(noise_power)
    noise = np.random.normal(0, noise_std, len(t))

    return clean_signal + noise, t, noise_std


def generate_signal_bursty(phase):
    """Generate bursty signal."""
    t = np.linspace(0, WINDOW_DURATION, int(GROUND_TRUTH_RATE))

    if phase == 0:  # Quiet
        freq = np.random.uniform(0.5, 2.0)
        amplitude = np.random.uniform(0.5, 1.5)
        snr_db = np.random.uniform(30, 40)
    else:  # Burst
        freq = np.random.uniform(5.0, 20.0)
        amplitude = np.random.uniform(3.0, 8.0)
        snr_db = np.random.uniform(15, 30)

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

    return clean_signal + noise, t, noise_std


def generate_signal_adversarial():
    """Generate adversarial chirp signal."""
    t = np.linspace(0, WINDOW_DURATION, int(GROUND_TRUTH_RATE))

    f0 = np.random.uniform(0.5, 5.0)
    f1 = np.random.uniform(5.0, 25.0)
    if np.random.rand() < 0.5:
        f0, f1 = f1, f0

    amplitude = np.random.uniform(1.0, 6.0)
    clean_signal = amplitude * scipy_signal.chirp(t, f0, 1.0, f1, method='linear')

    # Add impulses
    if np.random.rand() < 0.3:
        event_idx = np.random.randint(10, len(t) - 10)
        clean_signal[event_idx] += amplitude * 3.0

    snr_db = np.random.uniform(10, 40)
    signal_power = np.var(clean_signal)
    noise_power = signal_power / (10 ** (snr_db / 10))
    noise_std = np.sqrt(noise_power)
    noise = np.random.normal(0, noise_std, len(t))

    return clean_signal + noise, t, noise_std


def generate_and_label_workload(workload_type, n_samples):
    """Generate signals, compute features, and label with empirical oracle."""
    samples = []

    for i in range(n_samples):
        # Generate signal based on workload type
        if workload_type == 'steady':
            signal, times, noise_std = generate_signal_steady()
        elif workload_type == 'bursty':
            phase = (i // 50) % 2
            signal, times, noise_std = generate_signal_bursty(phase)
        elif workload_type == 'adversarial':
            signal, times, noise_std = generate_signal_adversarial()
        else:
            raise ValueError(f"Unknown workload type: {workload_type}")

        # Compute telemetry features
        features = compute_telemetry_features(signal, GROUND_TRUTH_RATE, noise_std)

        # Find optimal sampling rate (empirical oracle)
        optimal_rate, rate_results = find_optimal_sampling_rate(signal, times)

        # Add label
        features['optimal_sampling_rate_hz'] = optimal_rate

        # Store detailed results for analysis
        features['rmse_at_optimal'] = rate_results[optimal_rate]['rmse']
        features['energy_at_optimal'] = rate_results[optimal_rate]['energy']

        samples.append(features)

        # Progress indicator
        if (i + 1) % 100 == 0:
            print(f"  {workload_type:12s}: {i+1}/{n_samples} samples")

    return pd.DataFrame(samples)


def main(output_path: str):
    """Generate labeled dataset with empirical oracle."""
    print("Generating synthetic signals and labeling with empirical oracle...")
    print(f"Objective weights: α={ALPHA}, β={BETA}, γ={GAMMA}")
    print(f"Sampling rates tested: {SAMPLING_RATES}\n")

    steady = generate_and_label_workload('steady', 800)
    print(f"✓ Generated {len(steady)} steady samples\n")

    bursty = generate_and_label_workload('bursty', 600)
    print(f"✓ Generated {len(bursty)} bursty samples\n")

    adversarial = generate_and_label_workload('adversarial', 600)
    print(f"✓ Generated {len(adversarial)} adversarial samples\n")

    # Combine
    mixed = pd.concat([steady, bursty, adversarial], ignore_index=True)

    # Shuffle
    mixed = mixed.sample(frac=1, random_state=42).reset_index(drop=True)

    # Save
    mixed.to_csv(output_path, index=False)
    print(f"✓ Saved {len(mixed)} labeled samples to {output_path}\n")

    # Analysis
    print("=== Label Distribution ===")
    label_counts = mixed['optimal_sampling_rate_hz'].value_counts().sort_index()
    for rate, count in label_counts.items():
        pct = 100.0 * count / len(mixed)
        print(f"  {rate:3.0f} Hz: {count:4d} samples ({pct:5.1f}%)")

    print("\n=== Performance Variance Analysis ===")
    print(f"RMSE at optimal (mean ± std): {mixed['rmse_at_optimal'].mean():.4f} ± {mixed['rmse_at_optimal'].std():.4f}")
    print(f"RMSE CoV: {mixed['rmse_at_optimal'].std() / mixed['rmse_at_optimal'].mean():.3f}")

    print("\n=== Feature Statistics ===")
    feature_cols = ['signal_variance', 'dominant_freq_hz', 'freq_energy_ratio', 'signal_snr_db']
    print(mixed[feature_cols].describe())


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: oracle_sensorium_empirical.py <output.csv>")
        print("\nThis will generate signals and label them with empirical oracle.")
        print("This is computationally intensive (7 sweeps per sample).")
        sys.exit(1)

    output_path = sys.argv[1]
    main(output_path)
