#!/usr/bin/env python3
"""
Oracle Labeller

Exhaustively searches policy space to generate optimal labels for training.
"""

import pandas as pd
import numpy as np
from typing import Tuple, List
from dataclasses import dataclass
import sys


@dataclass
class PolicyParams:
    """Flush policy parameters"""
    threshold: int  # packets
    max_delay_us: int  # microseconds


@dataclass
class WindowFeatures:
    """Telemetry features for a single window"""
    queue_depth: float
    enqueue_rate: float
    dequeue_rate: float
    latency_p50_us: float
    latency_p95_us: float
    bytes_in_per_sec: float
    bytes_out_per_sec: float
    packet_size_mean: float
    packet_size_var: float
    rtt_ewma_us: float


# Policy search space (from 60-chronome-case.md)
THRESHOLDS = [1, 4, 8, 16, 32, 64]
MAX_DELAYS_US = [50, 200, 1000, 4000]


def load_telemetry(csv_path: str) -> pd.DataFrame:
    """Load telemetry CSV"""
    return pd.read_csv(csv_path)


def simulate_policy(
    features: WindowFeatures,
    policy: PolicyParams,
    lambda_param: float = 0.1
) -> float:
    """
    Simulate a policy and compute objective function J.

    J = p95_latency + λ * batch_overhead

    Model:
    - Queue latency increases with queue depth AND batch threshold
    - Timer-based flush adds delay penalty
    - Overhead inversely proportional to batch size
    """
    # Base latency from current queue state
    base_latency = features.latency_p95_us

    # Additional queueing delay if threshold is too high relative to current queue depth
    queue_delay_factor = max(0, policy.threshold - features.queue_depth) * 10.0

    # Delay from timer-based flush
    timer_delay = policy.max_delay_us * 0.5  # 50% of max delay on average

    # Total latency estimate
    estimated_latency = base_latency + queue_delay_factor + timer_delay

    # Overhead: cost of flushing frequently (smaller batches = more CPU)
    flush_frequency = 1000.0 / max(policy.threshold, 1)  # flushes per 1000 packets
    batch_overhead = flush_frequency * 100.0  # cost per flush

    J = estimated_latency + lambda_param * batch_overhead
    return J


def find_optimal_policy(
    features: WindowFeatures,
    lambda_param: float = 0.1
) -> Tuple[PolicyParams, float]:
    """
    Exhaustively search policy space to find optimal parameters.

    Returns: (best_policy, best_J)
    """
    best_policy = None
    best_J = float('inf')

    for threshold in THRESHOLDS:
        for max_delay_us in MAX_DELAYS_US:
            policy = PolicyParams(threshold, max_delay_us)
            J = simulate_policy(features, policy, lambda_param)

            if J < best_J:
                best_J = J
                best_policy = policy

    return best_policy, best_J


def create_windows(df: pd.DataFrame, window_size_ms: int = 200, step_ms: int = 100) -> List[WindowFeatures]:
    """
    Create sliding windows from telemetry dataframe.

    For simplicity, we assume the CSV already has aggregated samples.
    """
    windows = []

    # Assume each row is already a sample
    for idx, row in df.iterrows():
        window = WindowFeatures(
            queue_depth=row.get('queue_depth', 0),
            enqueue_rate=row.get('enqueue_rate', 0),
            dequeue_rate=row.get('dequeue_rate', 0),
            latency_p50_us=row.get('latency_p50_us', 0),
            latency_p95_us=row.get('latency_p95_us', 0),
            bytes_in_per_sec=row.get('bytes_in_per_sec', 0),
            bytes_out_per_sec=row.get('bytes_out_per_sec', 0),
            packet_size_mean=row.get('packet_size_mean', 0),
            packet_size_var=row.get('packet_size_var', 0),
            rtt_ewma_us=row.get('rtt_ewma_us', 50),
        )
        windows.append(window)

    return windows


def label_dataset(telemetry_path: str, output_path: str, lambda_param: float = 0.1):
    """
    Load telemetry, run oracle, and save training dataset.
    """
    print(f"Loading telemetry from {telemetry_path}...")
    df = load_telemetry(telemetry_path)
    print(f"Loaded {len(df)} samples")

    print("Creating windows...")
    windows = create_windows(df)
    print(f"Created {len(windows)} windows")

    print("Running oracle (exhaustive search)...")
    training_data = []

    for i, window in enumerate(windows):
        if i % 100 == 0:
            print(f"  Processing window {i}/{len(windows)}...")

        optimal_policy, J = find_optimal_policy(window, lambda_param)

        training_data.append({
            # Features
            'queue_depth': window.queue_depth,
            'enqueue_rate': window.enqueue_rate,
            'dequeue_rate': window.dequeue_rate,
            'latency_p50_us': window.latency_p50_us,
            'latency_p95_us': window.latency_p95_us,
            'bytes_in_per_sec': window.bytes_in_per_sec,
            'bytes_out_per_sec': window.bytes_out_per_sec,
            'packet_size_mean': window.packet_size_mean,
            'packet_size_var': window.packet_size_var,
            'rtt_ewma_us': window.rtt_ewma_us,

            # Labels
            'optimal_threshold': optimal_policy.threshold,
            'optimal_delay_us': optimal_policy.max_delay_us,
            'objective_J': J,
        })

    print(f"Saving training dataset to {output_path}...")
    training_df = pd.DataFrame(training_data)
    training_df.to_csv(output_path, index=False)
    print(f"✓ Saved {len(training_df)} labeled samples")

    # Print statistics
    print("\n=== Label Distribution ===")
    print("Optimal thresholds:")
    print(training_df['optimal_threshold'].value_counts().sort_index())
    print("\nOptimal delays (µs):")
    print(training_df['optimal_delay_us'].value_counts().sort_index())


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: oracle.py <telemetry.csv> <output_training.csv> [lambda]")
        sys.exit(1)

    telemetry_path = sys.argv[1]
    output_path = sys.argv[2]
    lambda_param = float(sys.argv[3]) if len(sys.argv) > 3 else 0.1

    label_dataset(telemetry_path, output_path, lambda_param)
