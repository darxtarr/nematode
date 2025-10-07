#!/usr/bin/env python3
"""
Validate Chronome Reflex Performance

Compare batching policies on fresh test traces:
1. Baseline: Fixed (threshold=8, delay=1000µs)
2. Reflex: ML model predictions

Measure p95 latency and flush rate.
"""

import pandas as pd
import numpy as np
import json
import sys
from collections import deque
from dataclasses import dataclass
from typing import List
from sklearn.tree import DecisionTreeRegressor


@dataclass
class Message:
    arrival_time: float
    size: int
    enqueue_time: float = 0.0
    flush_time: float = 0.0

    @property
    def latency(self) -> float:
        return self.flush_time - self.arrival_time


class BatchingSimulator:
    def __init__(self, batch_threshold: int, max_delay_us: float):
        self.batch_threshold = batch_threshold
        self.max_delay_us = max_delay_us / 1_000_000.0
        self.queue = deque()
        self.flushed_messages = []
        self.flush_count = 0

    def enqueue(self, msg: Message, current_time: float):
        msg.enqueue_time = current_time
        self.queue.append(msg)

    def maybe_flush(self, current_time: float):
        if len(self.queue) == 0:
            return

        if len(self.queue) >= self.batch_threshold:
            self._flush_batch(current_time)
            return

        time_since_first = current_time - self.queue[0].enqueue_time
        if time_since_first >= self.max_delay_us:
            self._flush_batch(current_time)

    def _flush_batch(self, current_time: float):
        batch_size = len(self.queue)
        transmission_time_us = batch_size * 8.0
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


def generate_traffic_trace(workload_type: str, seed: int) -> List[Message]:
    np.random.seed(seed)
    messages = []
    current_time = 0.0
    duration = 1.0

    if workload_type == 'steady':
        rate = np.random.uniform(400, 900)
        msg_size_mean = np.random.uniform(512, 1024)

        while current_time < duration:
            inter_arrival = np.random.exponential(1.0 / rate)
            current_time += inter_arrival
            if current_time >= duration:
                break
            size = int(max(64, np.random.normal(msg_size_mean, msg_size_mean * 0.2)))
            messages.append(Message(current_time, size))

    elif workload_type == 'bursty':
        phase_duration = 0.1
        phase = 0

        while current_time < duration:
            if phase % 2 == 0:
                rate = np.random.uniform(1000, 1800)
                msg_size_mean = np.random.uniform(768, 1536)
            else:
                rate = np.random.uniform(100, 300)
                msg_size_mean = np.random.uniform(256, 512)

            phase_end = min(current_time + phase_duration, duration)

            while current_time < phase_end:
                inter_arrival = np.random.exponential(1.0 / rate)
                current_time += inter_arrival
                if current_time >= phase_end:
                    break
                size = int(max(64, np.random.normal(msg_size_mean, msg_size_mean * 0.3)))
                messages.append(Message(current_time, size))

            phase += 1

    return messages


def compute_telemetry_features(trace: List[Message]) -> np.ndarray:
    """Compute features for a trace (simplified)"""
    duration = trace[-1].arrival_time if trace else 1.0
    arrival_rate_hz = len(trace) / duration

    sizes = [msg.size for msg in trace]
    msg_size_mean = np.mean(sizes)
    msg_size_var = np.var(sizes)

    # Simplified features for testing
    return np.array([
        len(trace),  # queue_depth
        arrival_rate_hz,
        arrival_rate_hz,  # dequeue_rate (approx)
        1000.0,  # latency_p50 (placeholder)
        3000.0,  # latency_p95 (placeholder)
        5000.0,  # latency_p99 (placeholder)
        msg_size_mean,
        msg_size_var,
        2.5,  # batch_size_mean (placeholder)
        arrival_rate_hz / 4.0,  # batch_flushes_per_sec (guess)
        0.8,  # burstiness (placeholder)
        3000.0,  # backlog_age_p95 (placeholder)
    ])


def simulate_with_config(trace: List[Message], threshold: int, delay_us: float) -> dict:
    sim = BatchingSimulator(threshold, delay_us)

    for msg in trace:
        sim.enqueue(msg, msg.arrival_time)
        sim.maybe_flush(msg.arrival_time)

    duration = trace[-1].arrival_time if trace else 1.0
    sim.force_flush(duration)

    latencies = sim.get_latencies_us()

    if len(latencies) == 0:
        return None

    return {
        'latency_p50_us': np.percentile(latencies, 50),
        'latency_p95_us': np.percentile(latencies, 95),
        'latency_p99_us': np.percentile(latencies, 99),
        'flushes_per_sec': sim.flush_count / duration,
        'throughput_msgs_per_sec': len(sim.flushed_messages) / duration,
    }


def run_validation(n_samples=50):
    print("=== Chronome Reflex Validation ===\n")

    # Load normalizer and retrain models
    print("Loading models...")
    with open('data/models/normalizer-chronome.json', 'r') as f:
        norm = json.load(f)

    mins = np.array(norm['mins'])
    maxs = np.array(norm['maxs'])

    # Load labeled data and retrain (quick way to get models in Python)
    df = pd.read_csv('data/telemetry/chronome-labeled.csv')
    feature_names = [
        'queue_depth', 'arrival_rate_hz', 'dequeue_rate_hz',
        'latency_p50_us', 'latency_p95_us', 'latency_p99_us',
        'msg_size_mean', 'msg_size_var', 'batch_size_mean',
        'batch_flushes_per_sec', 'burstiness', 'backlog_age_p95_us'
    ]
    X = df[feature_names].values
    y_threshold = df['optimal_batch_threshold'].values
    y_delay = df['optimal_max_delay_us'].values

    X_norm = (X - mins) / (maxs - mins)

    model_threshold = DecisionTreeRegressor(max_depth=4, min_samples_leaf=20, random_state=42)
    model_threshold.fit(X_norm, y_threshold)

    model_delay = DecisionTreeRegressor(max_depth=4, min_samples_leaf=20, random_state=42)
    model_delay.fit(X_norm, y_delay)

    print(f"  Models loaded\n")

    # Test on fresh traces
    results = {
        'baseline_8_1000': [],
        'reflex': []
    }

    print("Generating and testing traces...\n")

    for i in range(n_samples):
        workload_type = ['steady', 'bursty'][i % 2]
        trace = generate_traffic_trace(workload_type, seed=5000+i)

        if len(trace) < 10:
            continue

        # Baseline: threshold=8, delay=1000µs
        baseline_metrics = simulate_with_config(trace, 8, 1000)
        if baseline_metrics:
            results['baseline_8_1000'].append(baseline_metrics)

        # Reflex: predict from features
        features = compute_telemetry_features(trace)
        features_norm = (features - mins) / (maxs - mins)

        threshold_pred = model_threshold.predict([features_norm])[0]
        delay_pred = model_delay.predict([features_norm])[0]

        # Clamp to valid ranges
        threshold_pred = int(np.clip(threshold_pred, 1, 64))
        delay_pred = float(np.clip(delay_pred, 50, 4000))

        reflex_metrics = simulate_with_config(trace, threshold_pred, delay_pred)
        if reflex_metrics:
            results['reflex'].append(reflex_metrics)

    # Aggregate results
    print("=== Results ===\n")

    policies = ['baseline_8_1000', 'reflex']
    summary = {}

    for policy in policies:
        p95_vals = [r['latency_p95_us'] for r in results[policy]]
        p99_vals = [r['latency_p99_us'] for r in results[policy]]
        flush_vals = [r['flushes_per_sec'] for r in results[policy]]

        summary[policy] = {
            'p95_mean': np.mean(p95_vals),
            'p95_std': np.std(p95_vals),
            'p99_mean': np.mean(p99_vals),
            'p99_std': np.std(p99_vals),
            'flush_mean': np.mean(flush_vals),
            'flush_std': np.std(flush_vals)
        }

    # Print table
    print("| Policy          | p95 Latency (µs) | p99 Latency (µs) | Flushes/sec |")
    print("|-----------------|------------------|------------------|-------------|")

    for policy in policies:
        s = summary[policy]
        label = policy.replace('_', ' ').title()
        print(f"| {label:15s} | {s['p95_mean']:7.1f} ± {s['p95_std']:5.1f} | {s['p99_mean']:7.1f} ± {s['p99_std']:5.1f} | {s['flush_mean']:6.1f} ± {s['flush_std']:4.1f} |")

    # Compute gains
    print("\n=== Gains vs Baseline ===\n")

    baseline = summary['baseline_8_1000']
    reflex = summary['reflex']

    p95_delta_pct = 100.0 * (reflex['p95_mean'] - baseline['p95_mean']) / baseline['p95_mean']
    p99_delta_pct = 100.0 * (reflex['p99_mean'] - baseline['p99_mean']) / baseline['p99_mean']
    flush_delta_pct = 100.0 * (reflex['flush_mean'] - baseline['flush_mean']) / baseline['flush_mean']

    print(f"Reflex:")
    print(f"  p95 latency:  {p95_delta_pct:+6.1f}%")
    print(f"  p99 latency:  {p99_delta_pct:+6.1f}%")
    print(f"  Flush rate:   {flush_delta_pct:+6.1f}%")


if __name__ == "__main__":
    run_validation(n_samples=50)
