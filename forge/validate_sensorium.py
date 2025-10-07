#!/usr/bin/env python3
"""
Validate Sensorium Reflex Performance

Compare three policies on fresh test signals:
1. Baseline: Fixed sampling rate
2. Nyquist: 2× dominant frequency heuristic
3. Reflex: ML model prediction

Measure energy consumption and reconstruction quality.
"""

import pandas as pd
import numpy as np
import json
import sys
from scipy import signal as scipy_signal, interpolate
from scipy.fft import fft, fftfreq
from sklearn.tree import DecisionTreeRegressor


# Same objective weights as training
ALPHA = 1.0
BETA = 0.05
GAMMA = 0.0001


def load_model_and_normalizer(reflex_path, normalizer_path):
    """Load trained model from .reflex file"""
    # For simplicity, just load from training script outputs
    # In production, we'd parse the binary .reflex format

    # Load normalizer
    with open(normalizer_path, 'r') as f:
        norm = json.load(f)

    mins = np.array(norm['mins'])
    maxs = np.array(norm['maxs'])

    print(f"Loaded normalizer with {len(mins)} features")
    return mins, maxs


def compute_telemetry_features(signal_window, sampling_rate=100.0, noise_std=0.1):
    """Compute telemetry features (same as oracle)"""
    n_samples = len(signal_window)

    signal_mean = np.mean(signal_window)
    signal_variance = np.var(signal_window)

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

    return np.array([
        signal_variance,
        signal_mean,
        dominant_freq_hz,
        freq_energy_ratio,
        zero_crossings_per_sec,
        sample_age_ms,
        reconstruction_error_ewma,
        power_budget_pct,
        event_rate_hz,
        signal_snr_db,
    ]), dominant_freq_hz


def sample_and_reconstruct(ground_truth_signal, ground_truth_times, sampling_rate):
    """Sample at given rate and reconstruct"""
    n_samples = max(2, int(sampling_rate * 1.0))
    sampled_times = np.linspace(0, 1.0, n_samples)
    sampled_values = np.interp(sampled_times, ground_truth_times, ground_truth_signal)

    interp_func = interpolate.interp1d(sampled_times, sampled_values, kind='linear', fill_value='extrapolate')
    reconstructed = interp_func(ground_truth_times)

    return reconstructed


def compute_metrics(ground_truth, reconstructed, sampling_rate):
    """Compute RMSE, energy, and objective"""
    rmse = np.sqrt(np.mean((ground_truth - reconstructed) ** 2))
    energy = sampling_rate * 1.0  # mJ
    staleness = 1000.0 / sampling_rate
    J = ALPHA * rmse + BETA * energy + GAMMA * staleness
    return rmse, energy, J


def generate_test_signal(signal_type, seed=None):
    """Generate a test signal (not in training set)"""
    if seed is not None:
        np.random.seed(seed)

    t = np.linspace(0, 1.0, 100)

    if signal_type == 'steady':
        freq = np.random.uniform(1.0, 8.0)
        amplitude = np.random.uniform(2.0, 4.0)
        clean = amplitude * np.sin(2 * np.pi * freq * t)
        snr_db = np.random.uniform(25, 35)

    elif signal_type == 'bursty':
        freq = np.random.uniform(3.0, 15.0)
        amplitude = np.random.uniform(2.0, 6.0)
        burst_start = np.random.uniform(0.3, 0.5)
        burst_width = np.random.uniform(0.2, 0.3)
        envelope = np.where((t >= burst_start) & (t < burst_start + burst_width), 1.0, 0.3)
        clean = amplitude * envelope * np.sin(2 * np.pi * freq * t)
        snr_db = np.random.uniform(20, 30)

    elif signal_type == 'chirp':
        f0 = np.random.uniform(1.0, 5.0)
        f1 = np.random.uniform(10.0, 20.0)
        amplitude = np.random.uniform(2.0, 5.0)
        clean = amplitude * scipy_signal.chirp(t, f0, 1.0, f1)
        snr_db = np.random.uniform(15, 35)

    else:
        raise ValueError(f"Unknown signal type: {signal_type}")

    signal_power = np.var(clean)
    noise_power = signal_power / (10 ** (snr_db / 10))
    noise_std = np.sqrt(noise_power)
    noise = np.random.normal(0, noise_std, len(t))

    return clean + noise, t, noise_std


def run_validation(n_samples=100):
    """Run validation comparing three policies"""

    print("=== Sensorium Reflex Validation ===\n")

    # Load normalizer (we'll retrain the model in-memory from labeled data)
    print("Loading model...")
    mins, maxs = load_model_and_normalizer(
        'data/models/sensorium.reflex',
        'data/models/normalizer-sensorium.json'
    )

    # Load labeled data and retrain (quick way to get model in Python)
    df = pd.read_csv('data/telemetry/sensorium-labeled.csv')
    feature_names = [
        'signal_variance', 'signal_mean', 'dominant_freq_hz',
        'freq_energy_ratio', 'zero_crossings_per_sec', 'sample_age_ms',
        'reconstruction_error_ewma', 'power_budget_pct', 'event_rate_hz',
        'signal_snr_db'
    ]
    X = df[feature_names].values
    y = df['optimal_sampling_rate_hz'].values

    # Normalize
    X_norm = (X - mins) / (maxs - mins)

    # Train model
    model = DecisionTreeRegressor(max_depth=4, min_samples_leaf=20, random_state=42)
    model.fit(X_norm, y)
    print(f"  Model loaded (depth {model.get_depth()})\n")

    # Test on fresh signals
    results = {
        'baseline_10hz': [],
        'baseline_20hz': [],
        'nyquist': [],
        'reflex': []
    }

    print("Generating and testing signals...\n")

    for i in range(n_samples):
        # Generate test signal
        signal_type = ['steady', 'bursty', 'chirp'][i % 3]
        signal, times, noise_std = generate_test_signal(signal_type, seed=1000+i)

        # Compute features
        features, dominant_freq = compute_telemetry_features(signal, 100.0, noise_std)

        # Normalize features
        features_norm = (features - mins) / (maxs - mins)

        # Policy 1: Baseline 10 Hz
        rate_10hz = 10.0
        recon_10hz = sample_and_reconstruct(signal, times, rate_10hz)
        rmse_10hz, energy_10hz, J_10hz = compute_metrics(signal, recon_10hz, rate_10hz)
        results['baseline_10hz'].append({'rmse': rmse_10hz, 'energy': energy_10hz, 'J': J_10hz})

        # Policy 2: Baseline 20 Hz
        rate_20hz = 20.0
        recon_20hz = sample_and_reconstruct(signal, times, rate_20hz)
        rmse_20hz, energy_20hz, J_20hz = compute_metrics(signal, recon_20hz, rate_20hz)
        results['baseline_20hz'].append({'rmse': rmse_20hz, 'energy': energy_20hz, 'J': J_20hz})

        # Policy 3: Nyquist (2× dominant frequency)
        rate_nyquist = np.clip(2.0 * dominant_freq, 1.0, 100.0)
        recon_nyquist = sample_and_reconstruct(signal, times, rate_nyquist)
        rmse_nyquist, energy_nyquist, J_nyquist = compute_metrics(signal, recon_nyquist, rate_nyquist)
        results['nyquist'].append({'rmse': rmse_nyquist, 'energy': energy_nyquist, 'J': J_nyquist})

        # Policy 4: Reflex (ML prediction)
        rate_reflex = model.predict([features_norm])[0]
        rate_reflex = np.clip(rate_reflex, 1.0, 100.0)
        recon_reflex = sample_and_reconstruct(signal, times, rate_reflex)
        rmse_reflex, energy_reflex, J_reflex = compute_metrics(signal, recon_reflex, rate_reflex)
        results['reflex'].append({'rmse': rmse_reflex, 'energy': energy_reflex, 'J': J_reflex})

    # Aggregate results
    print("=== Results ===\n")

    policies = ['baseline_10hz', 'baseline_20hz', 'nyquist', 'reflex']
    summary = {}

    for policy in policies:
        rmse_vals = [r['rmse'] for r in results[policy]]
        energy_vals = [r['energy'] for r in results[policy]]
        J_vals = [r['J'] for r in results[policy]]

        summary[policy] = {
            'rmse_mean': np.mean(rmse_vals),
            'rmse_std': np.std(rmse_vals),
            'energy_mean': np.mean(energy_vals),
            'energy_std': np.std(energy_vals),
            'J_mean': np.mean(J_vals),
            'J_std': np.std(J_vals)
        }

    # Print table
    print("| Policy         | RMSE (mean±std) | Energy (mJ) | Objective J |")
    print("|----------------|-----------------|-------------|-------------|")

    for policy in policies:
        s = summary[policy]
        label = policy.replace('_', ' ').title()
        print(f"| {label:14s} | {s['rmse_mean']:6.3f} ± {s['rmse_std']:5.3f} | {s['energy_mean']:6.1f} ± {s['energy_std']:4.1f} | {s['J_mean']:6.3f} ± {s['J_std']:5.3f} |")

    # Compute gains
    print("\n=== Gains vs Baseline 20 Hz ===\n")

    baseline = summary['baseline_20hz']

    for policy in ['baseline_10hz', 'nyquist', 'reflex']:
        s = summary[policy]
        energy_delta_pct = 100.0 * (s['energy_mean'] - baseline['energy_mean']) / baseline['energy_mean']
        rmse_delta_pct = 100.0 * (s['rmse_mean'] - baseline['rmse_mean']) / baseline['rmse_mean']
        J_delta_pct = 100.0 * (s['J_mean'] - baseline['J_mean']) / baseline['J_mean']

        label = policy.replace('_', ' ').title()
        print(f"{label:14s}:")
        print(f"  Energy:     {energy_delta_pct:+6.1f}%")
        print(f"  RMSE:       {rmse_delta_pct:+6.1f}%")
        print(f"  Objective:  {J_delta_pct:+6.1f}%")
        print()


if __name__ == "__main__":
    run_validation(n_samples=100)
