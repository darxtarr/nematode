#!/usr/bin/env python3
"""
Generate synthetic telemetry for testing the training pipeline.
"""

import pandas as pd
import numpy as np
import sys


def generate_steady_telemetry(n_samples=1000):
    """Generate steady workload telemetry"""
    np.random.seed(42)

    data = []
    for i in range(n_samples):
        # Steady: moderate queue, stable latency
        queue_depth = np.random.randint(10, 30)
        enqueue_rate = np.random.normal(1000, 50)
        dequeue_rate = np.random.normal(1000, 50)
        latency_p50_us = np.random.normal(300, 50)
        latency_p95_us = np.random.normal(600, 100)
        bytes_in_per_sec = enqueue_rate * 1024
        bytes_out_per_sec = dequeue_rate * 1024
        packet_size_mean = 1024.0
        packet_size_var = 100.0
        rtt_ewma_us = 50.0

        data.append({
            'queue_depth': queue_depth,
            'enqueue_rate': enqueue_rate,
            'dequeue_rate': dequeue_rate,
            'latency_p50_us': latency_p50_us,
            'latency_p95_us': latency_p95_us,
            'bytes_in_per_sec': bytes_in_per_sec,
            'bytes_out_per_sec': bytes_out_per_sec,
            'packet_size_mean': packet_size_mean,
            'packet_size_var': packet_size_var,
            'rtt_ewma_us': rtt_ewma_us,
        })

    return pd.DataFrame(data)


def generate_bursty_telemetry(n_samples=1000):
    """Generate bursty workload telemetry"""
    np.random.seed(43)

    data = []
    for i in range(n_samples):
        # Alternate between high and low load
        phase = (i // 50) % 2  # switch every 50 samples

        if phase == 0:  # High load
            queue_depth = np.random.randint(40, 80)
            enqueue_rate = np.random.normal(5000, 200)
            dequeue_rate = np.random.normal(4500, 200)
            latency_p50_us = np.random.normal(800, 150)
            latency_p95_us = np.random.normal(1500, 300)
        else:  # Low load
            queue_depth = np.random.randint(2, 10)
            enqueue_rate = np.random.normal(100, 20)
            dequeue_rate = np.random.normal(100, 20)
            latency_p50_us = np.random.normal(150, 30)
            latency_p95_us = np.random.normal(300, 60)

        bytes_in_per_sec = enqueue_rate * 1024
        bytes_out_per_sec = dequeue_rate * 1024
        packet_size_mean = 1024.0
        packet_size_var = 100.0
        rtt_ewma_us = 50.0

        data.append({
            'queue_depth': queue_depth,
            'enqueue_rate': enqueue_rate,
            'dequeue_rate': dequeue_rate,
            'latency_p50_us': latency_p50_us,
            'latency_p95_us': latency_p95_us,
            'bytes_in_per_sec': bytes_in_per_sec,
            'bytes_out_per_sec': bytes_out_per_sec,
            'packet_size_mean': packet_size_mean,
            'packet_size_var': packet_size_var,
            'rtt_ewma_us': rtt_ewma_us,
        })

    return pd.DataFrame(data)


def generate_mixed_telemetry(n_samples=2000):
    """Generate mixed workload (steady + bursty)"""
    steady = generate_steady_telemetry(n_samples // 2)
    bursty = generate_bursty_telemetry(n_samples // 2)
    return pd.concat([steady, bursty], ignore_index=True).sample(frac=1, random_state=42).reset_index(drop=True)


if __name__ == "__main__":
    workload = sys.argv[1] if len(sys.argv) > 1 else "mixed"
    output = sys.argv[2] if len(sys.argv) > 2 else f"data/telemetry/{workload}.csv"

    print(f"Generating {workload} telemetry...")

    if workload == "steady":
        df = generate_steady_telemetry()
    elif workload == "bursty":
        df = generate_bursty_telemetry()
    elif workload == "mixed":
        df = generate_mixed_telemetry()
    else:
        print(f"Unknown workload: {workload}")
        sys.exit(1)

    df.to_csv(output, index=False)
    print(f"✓ Saved {len(df)} samples to {output}")
