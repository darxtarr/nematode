#!/usr/bin/env python3
"""
Generate Synthetic Compute Telemetry

Creates realistic thread-pool telemetry samples for training.
"""

import pandas as pd
import numpy as np
import sys


def generate_steady_workload(n_samples=1000):
    """
    Steady workload: constant arrival rate, predictable queue behavior.
    """
    samples = []

    # Steady state around 100 tasks/sec arrival
    arrival_rate = 100.0

    for i in range(n_samples):
        # Vary worker count to see different states
        n_workers = np.random.choice([4, 8, 16, 32])

        # Completion rate ~ n_workers * tasks_per_second_per_worker
        tasks_per_worker = 200.0  # ~5ms per task = 200 tasks/sec max
        completion_rate = min(arrival_rate, n_workers * tasks_per_worker)

        # Queue builds up if arrival > completion
        runq_len = max(0, int((arrival_rate - completion_rate) * np.random.uniform(0.5, 2.0)))

        # Task time depends on queue + execution
        queue_delay = runq_len * 10.0  # 10µs per queued task (simplified)
        exec_time = 500.0 + np.random.normal(0, 50)  # ~500µs execution
        task_time_p50 = queue_delay + exec_time
        task_time_p95 = task_time_p50 * 1.5 + np.random.normal(0, 100)

        # Worker utilization
        worker_util = min(1.0, arrival_rate / (n_workers * tasks_per_worker))

        # Context switches increase with worker count
        ctx_switches_per_sec = n_workers * 10.0 + np.random.normal(0, 20)

        # Task size stats
        task_size_mean = exec_time
        task_size_var = 2500.0 + np.random.normal(0, 500)

        # Idle workers
        idle_worker_count = max(0, int(n_workers * (1.0 - worker_util)))

        samples.append({
            'runq_len': runq_len,
            'arrival_rate': arrival_rate + np.random.normal(0, 5),
            'completion_rate': completion_rate + np.random.normal(0, 5),
            'task_time_p50_us': max(0, task_time_p50),
            'task_time_p95_us': max(0, task_time_p95),
            'worker_util': np.clip(worker_util, 0, 1),
            'ctx_switches_per_sec': max(0, ctx_switches_per_sec),
            'task_size_mean': task_size_mean,
            'task_size_var': max(0, task_size_var),
            'idle_worker_count': idle_worker_count,
        })

    return pd.DataFrame(samples)


def generate_bursty_workload(n_samples=1000):
    """
    Bursty workload: alternating high/low arrival rates.
    """
    samples = []

    for i in range(n_samples):
        # Alternate between high and low
        phase = (i // 50) % 2
        arrival_rate = 200.0 if phase == 0 else 50.0

        n_workers = np.random.choice([4, 8, 16, 32])

        tasks_per_worker = 200.0
        completion_rate = min(arrival_rate, n_workers * tasks_per_worker)

        # Queue builds during high phase
        runq_len = max(0, int((arrival_rate - completion_rate) * np.random.uniform(0.5, 3.0)))

        queue_delay = runq_len * 10.0
        exec_time = 500.0 + np.random.normal(0, 50)
        task_time_p50 = queue_delay + exec_time
        task_time_p95 = task_time_p50 * 1.5 + np.random.normal(0, 100)

        worker_util = min(1.0, arrival_rate / (n_workers * tasks_per_worker))
        ctx_switches_per_sec = n_workers * 10.0 + np.random.normal(0, 20)

        task_size_mean = exec_time
        task_size_var = 2500.0 + np.random.normal(0, 500)
        idle_worker_count = max(0, int(n_workers * (1.0 - worker_util)))

        samples.append({
            'runq_len': runq_len,
            'arrival_rate': arrival_rate + np.random.normal(0, 10),
            'completion_rate': completion_rate + np.random.normal(0, 10),
            'task_time_p50_us': max(0, task_time_p50),
            'task_time_p95_us': max(0, task_time_p95),
            'worker_util': np.clip(worker_util, 0, 1),
            'ctx_switches_per_sec': max(0, ctx_switches_per_sec),
            'task_size_mean': task_size_mean,
            'task_size_var': max(0, task_size_var),
            'idle_worker_count': idle_worker_count,
        })

    return pd.DataFrame(samples)


def generate_adversarial_workload(n_samples=1000):
    """
    Adversarial workload: random rate shifts, variable task sizes.
    """
    samples = []

    for i in range(n_samples):
        # Random arrival rate
        arrival_rate = np.random.uniform(20, 300)

        n_workers = np.random.choice([2, 4, 8, 16, 32, 64])

        # Variable task execution time
        exec_time = np.random.uniform(100, 2000)
        tasks_per_worker = 1_000_000.0 / exec_time  # tasks/sec per worker
        completion_rate = min(arrival_rate, n_workers * tasks_per_worker)

        runq_len = max(0, int(np.random.exponential(5)))

        queue_delay = runq_len * 10.0
        task_time_p50 = queue_delay + exec_time
        task_time_p95 = task_time_p50 * np.random.uniform(1.2, 2.5)

        worker_util = min(1.0, arrival_rate / (n_workers * tasks_per_worker))
        ctx_switches_per_sec = n_workers * np.random.uniform(5, 20)

        task_size_mean = exec_time
        task_size_var = exec_time * exec_time * np.random.uniform(0.1, 0.5)
        idle_worker_count = max(0, int(n_workers * (1.0 - worker_util)))

        samples.append({
            'runq_len': runq_len,
            'arrival_rate': arrival_rate,
            'completion_rate': completion_rate,
            'task_time_p50_us': max(0, task_time_p50),
            'task_time_p95_us': max(0, task_time_p95),
            'worker_util': np.clip(worker_util, 0, 1),
            'ctx_switches_per_sec': max(0, ctx_switches_per_sec),
            'task_size_mean': task_size_mean,
            'task_size_var': max(0, task_size_var),
            'idle_worker_count': idle_worker_count,
        })

    return pd.DataFrame(samples)


def generate_mixed_workload(output_path: str):
    """
    Generate mixed workload combining all three patterns.
    """
    print("Generating synthetic compute telemetry...")

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


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: gen_synthetic_telemetry_compute.py <output.csv>")
        sys.exit(1)

    output_path = sys.argv[1]
    generate_mixed_workload(output_path)
