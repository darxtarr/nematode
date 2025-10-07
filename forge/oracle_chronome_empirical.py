#!/usr/bin/env python3
"""
Empirical Oracle for Chronome Adaptive Batching

For each traffic trace, sweep all batching configurations (24 total) and measure
actual p95 latency + overhead. Labels each sample with the empirically optimal config.
"""

import pandas as pd
import numpy as np
import sys
from collections import deque
from dataclasses import dataclass
from typing import List
import pickle


# Objective function weights
ALPHA = 1.0      # p95 latency weight (primary metric, µs)
BETA = 20.0      # Overhead weight (flush rate penalty - very high syscall cost)
GAMMA = 0.0      # Throughput loss penalty (disabled for now)

# Available configurations
BATCH_THRESHOLDS = [1, 4, 8, 16, 32, 64]
MAX_DELAYS_US = [50, 200, 1000, 4000]


@dataclass
class Message:
    """A single message in the queue"""
    arrival_time: float
    size: int
    enqueue_time: float = 0.0
    flush_time: float = 0.0

    @property
    def latency(self) -> float:
        return self.flush_time - self.arrival_time


class BatchingSimulator:
    """Simulate message batching with configurable threshold and delay"""

    def __init__(self, batch_threshold: int, max_delay_us: float):
        self.batch_threshold = batch_threshold
        self.max_delay_us = max_delay_us / 1_000_000.0  # convert to seconds
        self.queue = deque()
        self.flushed_messages = []
        self.flush_count = 0

    def enqueue(self, msg: Message, current_time: float):
        msg.enqueue_time = current_time
        self.queue.append(msg)

    def maybe_flush(self, current_time: float):
        if len(self.queue) == 0:
            return

        # Flush if threshold reached
        if len(self.queue) >= self.batch_threshold:
            self._flush_batch(current_time)
            return

        # Flush if delay exceeded
        time_since_first = current_time - self.queue[0].enqueue_time
        if time_since_first >= self.max_delay_us:
            self._flush_batch(current_time)

    def _flush_batch(self, current_time: float):
        # Simulate transmission time: each message takes time to send
        # Assume 1 Gbps link, 1000 bytes/msg average → ~8µs per message
        batch_size = len(self.queue)
        transmission_time_us = batch_size * 8.0  # µs
        flush_completion_time = current_time + (transmission_time_us / 1_000_000.0)

        while self.queue:
            msg = self.queue.popleft()
            msg.flush_time = flush_completion_time
            self.flushed_messages.append(msg)
        self.flush_count += 1

    def force_flush(self, current_time: float):
        if self.queue:
            self._flush_batch(current_time)

    def get_latencies_us(self) -> List[float]:
        return [msg.latency * 1_000_000 for msg in self.flushed_messages]


def generate_traffic_trace(workload_type: str, params: dict, seed: int) -> List[Message]:
    """
    Regenerate traffic trace from parameters.

    params contains: arrival_rate_hz, msg_size_mean, burstiness, etc.
    """
    np.random.seed(seed)

    messages = []
    current_time = 0.0
    duration = 1.0

    arrival_rate = params['arrival_rate_hz']
    msg_size_mean = params['msg_size_mean']

    if workload_type == 'steady':
        while current_time < duration:
            inter_arrival = np.random.exponential(1.0 / arrival_rate)
            current_time += inter_arrival
            if current_time >= duration:
                break
            size = int(max(64, np.random.normal(msg_size_mean, msg_size_mean * 0.2)))
            messages.append(Message(current_time, size))

    elif workload_type == 'bursty':
        phase_duration = 0.1
        phase = 0

        while current_time < duration:
            if phase % 2 == 0:  # Burst
                rate = arrival_rate * 2.0
                size_mean = msg_size_mean * 1.5
            else:  # Quiet
                rate = arrival_rate * 0.3
                size_mean = msg_size_mean * 0.5

            phase_end = min(current_time + phase_duration, duration)

            while current_time < phase_end:
                inter_arrival = np.random.exponential(1.0 / rate)
                current_time += inter_arrival
                if current_time >= phase_end:
                    break
                size = int(max(64, np.random.normal(size_mean, size_mean * 0.3)))
                messages.append(Message(current_time, size))

            phase += 1

    elif workload_type == 'adversarial':
        rate = arrival_rate
        size_mean = msg_size_mean

        while current_time < duration:
            if len(messages) % 25 == 0:
                rate = np.random.uniform(arrival_rate * 0.5, arrival_rate * 1.5)
                size_mean = np.random.exponential(msg_size_mean)

            inter_arrival = np.random.exponential(1.0 / rate)
            current_time += inter_arrival
            if current_time >= duration:
                break
            size = int(max(64, np.random.exponential(size_mean)))
            messages.append(Message(current_time, size))

    return messages


def simulate_with_config(trace: List[Message], threshold: int, delay_us: float) -> dict:
    """
    Simulate trace with given config and return metrics.
    """
    sim = BatchingSimulator(threshold, delay_us)

    for msg in trace:
        sim.enqueue(msg, msg.arrival_time)
        sim.maybe_flush(msg.arrival_time)

    duration = trace[-1].arrival_time if trace else 1.0
    sim.force_flush(duration)

    latencies = sim.get_latencies_us()

    if len(latencies) == 0:
        return None

    p50 = np.percentile(latencies, 50)
    p95 = np.percentile(latencies, 95)
    p99 = np.percentile(latencies, 99)

    flushes_per_sec = sim.flush_count / duration
    throughput = len(sim.flushed_messages) / duration

    return {
        'latency_p50_us': p50,
        'latency_p95_us': p95,
        'latency_p99_us': p99,
        'flushes_per_sec': flushes_per_sec,
        'throughput_msgs_per_sec': throughput,
    }


def find_optimal_config(trace: List[Message]) -> tuple:
    """
    Sweep all configurations and find optimal.

    Returns:
        (optimal_threshold, optimal_delay_us, results_dict)
    """
    results = {}
    best_J = float('inf')
    best_config = None

    for threshold in BATCH_THRESHOLDS:
        for delay_us in MAX_DELAYS_US:
            metrics = simulate_with_config(trace, threshold, delay_us)

            if metrics is None:
                continue

            # Objective function
            p95_latency = metrics['latency_p95_us']

            # Overhead: penalty for high flush rates (want to batch more)
            overhead = metrics['flushes_per_sec'] * BETA

            throughput_penalty = 0.0

            J = ALPHA * p95_latency + overhead + throughput_penalty

            results[(threshold, delay_us)] = {
                **metrics,
                'J': J
            }

            if J < best_J:
                best_J = J
                best_config = (threshold, delay_us)

    return best_config[0], best_config[1], results


def label_dataset(input_csv: str, output_csv: str):
    """
    Load telemetry, regenerate traces, sweep configs, add labels.
    """
    print("Loading telemetry...")
    df = pd.read_csv(input_csv)
    print(f"  Loaded {len(df)} samples\n")

    print(f"Objective weights: α={ALPHA}, β={BETA}, γ={GAMMA}")
    print(f"Configurations to test: {len(BATCH_THRESHOLDS) * len(MAX_DELAYS_US)}\n")

    labeled_samples = []

    for idx, row in df.iterrows():
        # Infer workload type from index (same order as generation)
        if idx < 800:
            workload_type = 'steady'
        elif idx < 1400:
            workload_type = 'bursty'
        else:
            workload_type = 'adversarial'

        # Regenerate trace (use original seed + index offset)
        seed = 1000 + idx
        params = {
            'arrival_rate_hz': row['arrival_rate_hz'],
            'msg_size_mean': row['msg_size_mean']
        }

        trace = generate_traffic_trace(workload_type, params, seed)

        if len(trace) < 2:
            continue

        # Find optimal config
        opt_threshold, opt_delay_us, config_results = find_optimal_config(trace)

        # Store original features + optimal labels
        labeled_row = row.to_dict()
        labeled_row['optimal_batch_threshold'] = opt_threshold
        labeled_row['optimal_max_delay_us'] = opt_delay_us

        # Store metrics at optimal config
        opt_metrics = config_results[(opt_threshold, opt_delay_us)]
        labeled_row['J_at_optimal'] = opt_metrics['J']
        labeled_row['latency_p95_at_optimal'] = opt_metrics['latency_p95_us']

        labeled_samples.append(labeled_row)

        if (idx + 1) % 100 == 0:
            print(f"  Processed {idx+1}/{len(df)} samples")

    # Save
    labeled_df = pd.DataFrame(labeled_samples)
    labeled_df.to_csv(output_csv, index=False)
    print(f"\n✓ Saved {len(labeled_df)} labeled samples to {output_csv}\n")

    # Analysis
    print("=== Label Distribution ===")
    print("Batch Thresholds:")
    threshold_counts = labeled_df['optimal_batch_threshold'].value_counts().sort_index()
    for threshold, count in threshold_counts.items():
        pct = 100.0 * count / len(labeled_df)
        print(f"  {threshold:3d}: {count:4d} samples ({pct:5.1f}%)")

    print("\nMax Delays (µs):")
    delay_counts = labeled_df['optimal_max_delay_us'].value_counts().sort_index()
    for delay, count in delay_counts.items():
        pct = 100.0 * count / len(labeled_df)
        print(f"  {delay:4.0f}: {count:4d} samples ({pct:5.1f}%)")

    print("\n=== Performance Variance ===")
    print(f"p95 latency at optimal (mean ± std): {labeled_df['latency_p95_at_optimal'].mean():.1f} ± {labeled_df['latency_p95_at_optimal'].std():.1f} µs")
    print(f"p95 CoV: {labeled_df['latency_p95_at_optimal'].std() / labeled_df['latency_p95_at_optimal'].mean():.3f}")

    print("\n=== Feature Statistics ===")
    feature_cols = ['arrival_rate_hz', 'latency_p95_us', 'burstiness', 'batch_size_mean']
    print(labeled_df[feature_cols].describe())


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: oracle_chronome_empirical.py <input.csv> <output_labeled.csv>")
        print("\nThis will regenerate traces and sweep all 24 configurations.")
        print("Estimated runtime: ~5-10 minutes for 2000 samples.")
        sys.exit(1)

    input_csv = sys.argv[1]
    output_csv = sys.argv[2]

    label_dataset(input_csv, output_csv)
