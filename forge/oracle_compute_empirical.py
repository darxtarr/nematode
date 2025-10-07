#!/usr/bin/env python3
"""
Empirical Oracle Labeller for Thread Pool Sizing

Instead of using analytical models, this oracle runs actual simulations
for each telemetry sample to find the empirically optimal pool size.

This produces ground-truth labels based on measured performance.
"""

import pandas as pd
import subprocess
import sys
import os
from typing import Tuple
import json

# Pool sizes to test
POOL_SIZES = [1, 2, 4, 8, 16, 32, 64]

# Path to sweep binary
SWEEP_BINARY = "./target/release/sweep"


def run_empirical_sweep(arrival_rate: float, task_us: int, duration_secs: int = 3) -> Tuple[int, float]:
    """
    Run simulator sweep to find empirically optimal N.

    Returns: (optimal_n, best_p95)
    """
    best_n = 1
    best_p95 = float('inf')

    try:
        # Run sweep binary
        result = subprocess.run(
            [SWEEP_BINARY, str(arrival_rate), str(task_us), str(duration_secs)],
            capture_output=True,
            text=True,
            timeout=60
        )

        if result.returncode != 0:
            print(f"  WARNING: Sweep failed for arrival_rate={arrival_rate}, task_us={task_us}")
            return 8, 10000.0  # default fallback

        # Parse output to extract optimal N
        for line in result.stdout.split('\n'):
            if line.startswith('Best N:'):
                parts = line.split()
                best_n = int(parts[2])
                # Extract p95 from "Best N: 8 (p95 = 10273 µs)"
                p95_str = parts[5]
                best_p95 = float(p95_str)
                break

    except subprocess.TimeoutExpired:
        print(f"  WARNING: Sweep timed out for arrival_rate={arrival_rate}, task_us={task_us}")
        return 8, 10000.0
    except Exception as e:
        print(f"  ERROR: {e}")
        return 8, 10000.0

    return best_n, best_p95


def label_dataset_empirical(
    telemetry_path: str,
    output_path: str,
    sample_limit: int = None,
    duration_secs: int = 3
):
    """
    Load telemetry, run empirical simulations, and save training dataset.

    Saves incrementally after each sample to preserve progress if interrupted.
    """
    print(f"Loading telemetry from {telemetry_path}...")
    df = pd.read_csv(telemetry_path)

    if sample_limit:
        df = df.head(sample_limit)
        print(f"Limited to {sample_limit} samples for testing")

    print(f"Loaded {len(df)} samples")

    # Check for existing partial results
    start_idx = 0
    if os.path.exists(output_path):
        existing = pd.read_csv(output_path)
        start_idx = len(existing)
        print(f"Found existing results: {start_idx} samples already processed")
        print(f"Resuming from sample {start_idx}")
    else:
        print(f"Starting fresh labelling")

    print(f"Running empirical simulations ({duration_secs}s per sample, {len(POOL_SIZES)} pool sizes)...")
    print(f"Estimated time: ~{(len(df) - start_idx) * duration_secs} seconds\n")

    samples_processed = 0

    for i, row in df.iterrows():
        # Skip already processed samples
        if i < start_idx:
            continue

        if samples_processed % 10 == 0:
            print(f"  Processing sample {i}/{len(df)} (batch progress: {samples_processed}/{len(df) - start_idx})...")

        # Extract workload parameters from telemetry
        arrival_rate = row.get('arrival_rate', 100.0)
        task_size_mean = row.get('task_size_mean', 500.0)

        # Convert to integers for simulator
        arrival_rate_int = max(1, int(arrival_rate))
        task_us = max(100, int(task_size_mean))

        # Run empirical sweep
        optimal_n, empirical_p95 = run_empirical_sweep(
            arrival_rate_int,
            task_us,
            duration_secs
        )

        sample_data = {
            # Features (from original telemetry)
            'runq_len': row.get('runq_len', 0),
            'arrival_rate': row.get('arrival_rate', 0),
            'completion_rate': row.get('completion_rate', 0),
            'task_time_p50_us': row.get('task_time_p50_us', 0),
            'task_time_p95_us': row.get('task_time_p95_us', 0),
            'worker_util': row.get('worker_util', 0),
            'ctx_switches_per_sec': row.get('ctx_switches_per_sec', 0),
            'task_size_mean': row.get('task_size_mean', 500),
            'task_size_var': row.get('task_size_var', 0),
            'idle_worker_count': row.get('idle_worker_count', 0),

            # Empirical labels
            'optimal_n_workers': optimal_n,
            'empirical_p95': empirical_p95,
        }

        # Save incrementally (append after each sample)
        sample_df = pd.DataFrame([sample_data])
        if samples_processed == 0 and start_idx == 0:
            # First sample ever: write with header
            sample_df.to_csv(output_path, index=False, mode='w')
        else:
            # Subsequent samples or resuming: append without header
            sample_df.to_csv(output_path, index=False, mode='a', header=False)

        samples_processed += 1

    print(f"\n✓ Completed! Processed {samples_processed} new samples")
    print(f"✓ Total samples in {output_path}: {start_idx + samples_processed}")

    # Print statistics
    final_df = pd.read_csv(output_path)
    print("\n=== Empirical Label Distribution ===")
    print("Optimal n_workers:")
    print(final_df['optimal_n_workers'].value_counts().sort_index())

    print("\n=== Empirical p95 Statistics ===")
    print(f"Mean p95: {final_df['empirical_p95'].mean():.2f} µs")
    print(f"Median p95: {final_df['empirical_p95'].median():.2f} µs")
    print(f"Min p95: {final_df['empirical_p95'].min():.2f} µs")
    print(f"Max p95: {final_df['empirical_p95'].max():.2f} µs")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: oracle_compute_empirical.py <telemetry.csv> <output_training.csv> [sample_limit|all] [duration_secs]")
        print("\nExample:")
        print("  oracle_compute_empirical.py data/telemetry/compute-training.csv data/telemetry/compute-empirical.csv 50 3")
        print("  oracle_compute_empirical.py data/telemetry/compute-training.csv data/telemetry/compute-empirical.csv all 2")
        sys.exit(1)

    telemetry_path = sys.argv[1]
    output_path = sys.argv[2]

    # Handle 'all' keyword or numeric limit
    if len(sys.argv) > 3:
        sample_limit = None if sys.argv[3] == 'all' else int(sys.argv[3])
    else:
        sample_limit = None

    duration_secs = int(sys.argv[4]) if len(sys.argv) > 4 else 3

    label_dataset_empirical(telemetry_path, output_path, sample_limit, duration_secs)
