#!/usr/bin/env python3
"""
Oracle Labeller for Thread Pool Sizing

Exhaustively searches pool size space to generate optimal labels for training.
"""

import pandas as pd
import numpy as np
from typing import Tuple
from dataclasses import dataclass
import sys


@dataclass
class PoolSizePolicy:
    """Thread pool size policy"""
    n_workers: int


@dataclass
class ComputeFeatures:
    """Telemetry features for compute workload"""
    runq_len: float
    arrival_rate: float
    completion_rate: float
    task_time_p50_us: float
    task_time_p95_us: float
    worker_util: float
    ctx_switches_per_sec: float
    task_size_mean: float
    task_size_var: float
    idle_worker_count: float


# Policy search space: N workers
POOL_SIZES = [1, 2, 4, 8, 16, 32, 64]


def load_telemetry(csv_path: str) -> pd.DataFrame:
    """Load telemetry CSV"""
    return pd.read_csv(csv_path)


def simulate_policy(
    features: ComputeFeatures,
    policy: PoolSizePolicy,
    alpha: float = 1.0,
    beta: float = 0.05,
    gamma: float = 0.1
) -> float:
    """
    Simulate a thread pool sizing policy and compute objective function J.

    J = α·p95_task_time + β·ctx_switch_cost + γ·idle_waste

    Model:
    - Task time = queue_delay + execution_time
    - Queue delay increases if workers < arrival rate / throughput_per_worker
    - Context switches scale with worker count
    - Idle waste = idle_workers * cost_per_idle
    """
    # Base task time from current state
    base_task_time = features.task_time_p95_us

    # Estimate throughput capacity
    # Assume each worker can handle ~200 tasks/sec (5ms per task)
    throughput_per_worker = 1_000_000.0 / features.task_size_mean if features.task_size_mean > 0 else 200.0
    total_capacity = policy.n_workers * throughput_per_worker

    # Queueing delay if under-provisioned
    if total_capacity < features.arrival_rate:
        # Queue builds up
        queue_growth = (features.arrival_rate - total_capacity) / total_capacity
        queue_delay_penalty = queue_growth * 1000.0  # µs penalty per unit shortage
    else:
        # Queue drains
        queue_delay_penalty = -min(features.runq_len * 50.0, 500.0)  # benefit from draining

    estimated_task_time = base_task_time + queue_delay_penalty

    # Context switch cost (scales with worker count)
    # More workers = more scheduling overhead
    ctx_switch_cost = policy.n_workers * 10.0  # µs per worker

    # Idle waste (over-provisioning penalty)
    # Estimate idle workers based on utilization
    expected_util = min(1.0, features.arrival_rate / total_capacity) if total_capacity > 0 else 1.0
    expected_idle = policy.n_workers * (1.0 - expected_util)
    idle_waste = expected_idle * 50.0  # cost per idle worker

    # Stability penalty: penalize extreme pool sizes
    if policy.n_workers < 2:
        stability_penalty = 200.0  # single worker is fragile
    elif policy.n_workers > 48:
        stability_penalty = (policy.n_workers - 48) * 20.0  # diminishing returns
    else:
        stability_penalty = 0.0

    J = alpha * estimated_task_time + beta * ctx_switch_cost + gamma * idle_waste + stability_penalty
    return J


def find_optimal_policy(
    features: ComputeFeatures,
    alpha: float = 1.0,
    beta: float = 0.05,
    gamma: float = 0.1
) -> Tuple[PoolSizePolicy, float]:
    """
    Exhaustively search pool size space to find optimal parameters.

    Returns: (best_policy, best_J)
    """
    best_policy = None
    best_J = float('inf')

    for n_workers in POOL_SIZES:
        policy = PoolSizePolicy(n_workers)
        J = simulate_policy(features, policy, alpha, beta, gamma)

        if J < best_J:
            best_J = J
            best_policy = policy

    return best_policy, best_J


def create_windows(df: pd.DataFrame):
    """
    Create feature windows from telemetry dataframe.
    Assumes each row is already a sample.
    """
    windows = []

    for idx, row in df.iterrows():
        window = ComputeFeatures(
            runq_len=row.get('runq_len', 0),
            arrival_rate=row.get('arrival_rate', 0),
            completion_rate=row.get('completion_rate', 0),
            task_time_p50_us=row.get('task_time_p50_us', 0),
            task_time_p95_us=row.get('task_time_p95_us', 0),
            worker_util=row.get('worker_util', 0),
            ctx_switches_per_sec=row.get('ctx_switches_per_sec', 0),
            task_size_mean=row.get('task_size_mean', 500),
            task_size_var=row.get('task_size_var', 0),
            idle_worker_count=row.get('idle_worker_count', 0),
        )
        windows.append(window)

    return windows


def label_dataset(
    telemetry_path: str,
    output_path: str,
    alpha: float = 1.0,
    beta: float = 0.05,
    gamma: float = 0.1
):
    """
    Load telemetry, run oracle, and save training dataset.
    """
    print(f"Loading telemetry from {telemetry_path}...")
    df = load_telemetry(telemetry_path)
    print(f"Loaded {len(df)} samples")

    print("Creating windows...")
    windows = create_windows(df)
    print(f"Created {len(windows)} windows")

    print(f"Running oracle (exhaustive search over {len(POOL_SIZES)} pool sizes)...")
    print(f"Objective weights: α={alpha}, β={beta}, γ={gamma}")
    training_data = []

    for i, window in enumerate(windows):
        if i % 100 == 0:
            print(f"  Processing window {i}/{len(windows)}...")

        optimal_policy, J = find_optimal_policy(window, alpha, beta, gamma)

        training_data.append({
            # Features
            'runq_len': window.runq_len,
            'arrival_rate': window.arrival_rate,
            'completion_rate': window.completion_rate,
            'task_time_p50_us': window.task_time_p50_us,
            'task_time_p95_us': window.task_time_p95_us,
            'worker_util': window.worker_util,
            'ctx_switches_per_sec': window.ctx_switches_per_sec,
            'task_size_mean': window.task_size_mean,
            'task_size_var': window.task_size_var,
            'idle_worker_count': window.idle_worker_count,

            # Labels
            'optimal_n_workers': optimal_policy.n_workers,
            'objective_J': J,
        })

    print(f"Saving training dataset to {output_path}...")
    training_df = pd.DataFrame(training_data)
    training_df.to_csv(output_path, index=False)
    print(f"✓ Saved {len(training_df)} labeled samples")

    # Print statistics
    print("\n=== Label Distribution ===")
    print("Optimal n_workers:")
    print(training_df['optimal_n_workers'].value_counts().sort_index())

    print("\n=== Objective Statistics ===")
    print(f"Mean J: {training_df['objective_J'].mean():.2f}")
    print(f"Median J: {training_df['objective_J'].median():.2f}")
    print(f"Min J: {training_df['objective_J'].min():.2f}")
    print(f"Max J: {training_df['objective_J'].max():.2f}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: oracle_compute.py <telemetry.csv> <output_training.csv> [alpha] [beta] [gamma]")
        sys.exit(1)

    telemetry_path = sys.argv[1]
    output_path = sys.argv[2]
    alpha = float(sys.argv[3]) if len(sys.argv) > 3 else 1.0
    beta = float(sys.argv[4]) if len(sys.argv) > 4 else 0.05
    gamma = float(sys.argv[5]) if len(sys.argv) > 5 else 0.1

    label_dataset(telemetry_path, output_path, alpha, beta, gamma)
