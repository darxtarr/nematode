#!/usr/bin/env python3
"""
Generate Synthetic Chronome Telemetry

Creates realistic network traffic traces and computes telemetry features
for adaptive batching reflex training.
"""

import pandas as pd
import numpy as np
import sys
from collections import deque
from dataclasses import dataclass
from typing import List, Tuple


@dataclass
class Message:
    """A single message in the queue"""
    arrival_time: float
    size: int  # bytes
    enqueue_time: float = 0.0
    flush_time: float = 0.0

    @property
    def latency(self) -> float:
        """Time from arrival to flush"""
        return self.flush_time - self.arrival_time


class BatchingSimulator:
    """Simulate message batching with configurable threshold and delay"""

    def __init__(self, batch_threshold: int, max_delay_us: float):
        self.batch_threshold = batch_threshold
        self.max_delay_us = max_delay_us / 1_000_000.0  # convert to seconds
        self.queue = deque()
        self.last_flush_time = 0.0
        self.flushed_messages = []

    def enqueue(self, msg: Message, current_time: float):
        """Add message to queue"""
        msg.enqueue_time = current_time
        self.queue.append(msg)

    def maybe_flush(self, current_time: float) -> bool:
        """Check if batch should be flushed"""
        if len(self.queue) == 0:
            return False

        # Flush if threshold reached
        if len(self.queue) >= self.batch_threshold:
            self._flush_batch(current_time)
            return True

        # Flush if delay exceeded
        time_since_first = current_time - self.queue[0].enqueue_time
        if time_since_first >= self.max_delay_us:
            self._flush_batch(current_time)
            return True

        return False

    def _flush_batch(self, current_time: float):
        """Flush all messages in queue"""
        while self.queue:
            msg = self.queue.popleft()
            msg.flush_time = current_time
            self.flushed_messages.append(msg)
        self.last_flush_time = current_time

    def force_flush(self, current_time: float):
        """Flush any remaining messages (end of simulation)"""
        if self.queue:
            self._flush_batch(current_time)

    def get_latencies(self) -> List[float]:
        """Get all message latencies in microseconds"""
        return [msg.latency * 1_000_000 for msg in self.flushed_messages]


def generate_traffic_trace(workload_type: str, duration: float = 1.0, seed: int = None) -> List[Message]:
    """
    Generate message arrival trace.

    Args:
        workload_type: 'steady', 'bursty', or 'adversarial'
        duration: Trace duration in seconds
        seed: Random seed for reproducibility

    Returns:
        List of messages with arrival times
    """
    if seed is not None:
        np.random.seed(seed)

    messages = []
    current_time = 0.0

    if workload_type == 'steady':
        # Constant rate (Poisson arrivals)
        rate = np.random.uniform(200, 1000)  # messages/sec (high rate for batching)
        msg_size_mean = np.random.uniform(256, 1024)  # bytes

        while current_time < duration:
            # Exponential inter-arrival times
            inter_arrival = np.random.exponential(1.0 / rate)
            current_time += inter_arrival

            if current_time >= duration:
                break

            size = int(max(64, np.random.normal(msg_size_mean, msg_size_mean * 0.2)))
            messages.append(Message(current_time, size))

    elif workload_type == 'bursty':
        # Alternating burst/quiet phases
        phase_duration = 0.1  # 100 ms per phase
        phase = 0

        while current_time < duration:
            if phase % 2 == 0:  # Burst phase
                rate = np.random.uniform(800, 2000)
                msg_size_mean = np.random.uniform(512, 2048)
            else:  # Quiet phase
                rate = np.random.uniform(50, 200)
                msg_size_mean = np.random.uniform(128, 512)

            phase_end = min(current_time + phase_duration, duration)

            while current_time < phase_end:
                inter_arrival = np.random.exponential(1.0 / rate)
                current_time += inter_arrival

                if current_time >= phase_end:
                    break

                size = int(max(64, np.random.normal(msg_size_mean, msg_size_mean * 0.3)))
                messages.append(Message(current_time, size))

            phase += 1

    elif workload_type == 'adversarial':
        # Random rate changes and size variations
        rate = np.random.uniform(200, 800)
        msg_size_mean = np.random.uniform(256, 2048)

        while current_time < duration:
            # Random rate changes every 50 ms
            if len(messages) % 25 == 0:
                rate = np.random.uniform(100, 1500)
                msg_size_mean = np.random.uniform(128, 4096)

            inter_arrival = np.random.exponential(1.0 / rate)
            current_time += inter_arrival

            if current_time >= duration:
                break

            size = int(max(64, np.random.exponential(msg_size_mean)))
            messages.append(Message(current_time, size))

    else:
        raise ValueError(f"Unknown workload type: {workload_type}")

    return messages


def simulate_and_compute_features(trace: List[Message]) -> dict:
    """
    Simulate batching and compute telemetry features.

    Uses a default config (threshold=8, delay=1000µs) to collect baseline telemetry.
    """
    # Default config for feature collection
    sim = BatchingSimulator(batch_threshold=8, max_delay_us=1000)

    # Simulate trace
    for i, msg in enumerate(trace):
        sim.enqueue(msg, msg.arrival_time)

        # Check for flush after each message
        sim.maybe_flush(msg.arrival_time)

    # Force flush at end
    duration = trace[-1].arrival_time if trace else 1.0
    sim.force_flush(duration)

    # Compute features
    latencies = sim.get_latencies()

    if len(latencies) == 0:
        # No messages processed
        return None

    # Basic statistics
    queue_depth = len(trace)  # Simplified: total messages
    arrival_rate_hz = len(trace) / duration
    dequeue_rate_hz = len(sim.flushed_messages) / duration

    latency_p50_us = np.percentile(latencies, 50)
    latency_p95_us = np.percentile(latencies, 95)
    latency_p99_us = np.percentile(latencies, 99)

    sizes = [msg.size for msg in trace]
    msg_size_mean = np.mean(sizes)
    msg_size_var = np.var(sizes)

    # Compute batch statistics
    batch_sizes = []
    current_batch_size = 0
    last_flush_time = 0.0

    for msg in sim.flushed_messages:
        if msg.flush_time > last_flush_time:
            if current_batch_size > 0:
                batch_sizes.append(current_batch_size)
            current_batch_size = 1
            last_flush_time = msg.flush_time
        else:
            current_batch_size += 1

    if current_batch_size > 0:
        batch_sizes.append(current_batch_size)

    batch_size_mean = np.mean(batch_sizes) if batch_sizes else 1.0
    batch_flushes_per_sec = len(batch_sizes) / duration if batch_sizes else 0.0

    # Burstiness (coefficient of variation of inter-arrival times)
    if len(trace) > 1:
        inter_arrivals = np.diff([msg.arrival_time for msg in trace])
        burstiness = np.std(inter_arrivals) / np.mean(inter_arrivals) if np.mean(inter_arrivals) > 0 else 0.0
    else:
        burstiness = 0.0

    # Backlog age (simplified: use latency p95)
    backlog_age_p95_us = latency_p95_us

    return {
        'queue_depth': int(queue_depth),
        'arrival_rate_hz': arrival_rate_hz,
        'dequeue_rate_hz': dequeue_rate_hz,
        'latency_p50_us': latency_p50_us,
        'latency_p95_us': latency_p95_us,
        'latency_p99_us': latency_p99_us,
        'msg_size_mean': msg_size_mean,
        'msg_size_var': msg_size_var,
        'batch_size_mean': batch_size_mean,
        'batch_flushes_per_sec': batch_flushes_per_sec,
        'burstiness': min(1.0, burstiness),  # cap at 1.0
        'backlog_age_p95_us': backlog_age_p95_us,
    }


def generate_workload(workload_type: str, n_samples: int) -> pd.DataFrame:
    """Generate multiple traces and compute features"""
    samples = []

    for i in range(n_samples):
        trace = generate_traffic_trace(workload_type, duration=1.0, seed=1000 + i)

        if len(trace) == 0:
            continue

        features = simulate_and_compute_features(trace)

        if features is None:
            continue

        samples.append(features)

        if (i + 1) % 100 == 0:
            print(f"  {workload_type:12s}: {i+1}/{n_samples} samples")

    return pd.DataFrame(samples)


def generate_mixed_workload(output_path: str):
    """Generate mixed workload combining all three patterns"""
    print("Generating synthetic chronome telemetry...")

    steady = generate_workload('steady', 800)
    print(f"✓ Generated {len(steady)} steady samples\n")

    bursty = generate_workload('bursty', 600)
    print(f"✓ Generated {len(bursty)} bursty samples\n")

    adversarial = generate_workload('adversarial', 600)
    print(f"✓ Generated {len(adversarial)} adversarial samples\n")

    # Combine
    mixed = pd.concat([steady, bursty, adversarial], ignore_index=True)

    # Shuffle
    mixed = mixed.sample(frac=1, random_state=42).reset_index(drop=True)

    # Save
    mixed.to_csv(output_path, index=False)
    print(f"✓ Saved {len(mixed)} samples to {output_path}\n")

    # Print statistics
    print("=== Sample Statistics ===")
    print(mixed.describe())

    print("\n=== Feature Ranges ===")
    for col in mixed.columns:
        print(f"{col:30s}: [{mixed[col].min():10.2f}, {mixed[col].max():10.2f}]")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: gen_synthetic_telemetry_chronome.py <output.csv>")
        sys.exit(1)

    output_path = sys.argv[1]
    generate_mixed_workload(output_path)
