# Telemetry Schema — Chronome Adaptive Batching
**Domain**: Networking / Transport
**Tablet**: 🜁 1
**Version**: v1
**Date**: 2025-10-07

---

## Purpose

Define telemetry schema for adaptive batching reflex in network transport layer. The reflex observes traffic patterns and queue state to dynamically adjust batch parameters, minimizing tail latency while maintaining throughput.

---

## Batching Problem

**Tradeoff**:
- **Small batches** → Low latency, high per-packet overhead (syscalls, headers, interrupts)
- **Large batches** → High latency (queueing delay), low amortized overhead

**Goal**: Find optimal `{batch_threshold, max_delay}` that minimizes:
```
J = α·p95_latency + β·overhead + γ·throughput_loss
```

---

## Control Knobs

### 1. Batch Threshold
`batch_threshold` ∈ {1, 4, 8, 16, 32, 64} messages

When queue reaches this size, flush immediately (bypass delay).

### 2. Max Delay
`max_delay_us` ∈ {50, 200, 1000, 4000} µs

Maximum time to wait for more messages before flushing partial batch.

**Total parameter space**: 6 × 4 = 24 configurations

---

## Telemetry Features (12 inputs → 2 outputs)

| Feature | Type | Unit | Description |
|---------|------|------|-------------|
| `queue_depth` | int | msgs | Current number of messages in send queue |
| `arrival_rate_hz` | float | msg/s | Recent arrival rate (EWMA over 1s window) |
| `dequeue_rate_hz` | float | msg/s | Recent dequeue rate (messages sent) |
| `latency_p50_us` | float | µs | Median message latency (enqueue → send) |
| `latency_p95_us` | float | µs | 95th percentile latency |
| `latency_p99_us` | float | µs | 99th percentile latency |
| `msg_size_mean` | float | bytes | Mean message size |
| `msg_size_var` | float | bytes² | Message size variance |
| `batch_size_mean` | float | msgs | Mean batch size (recent window) |
| `batch_flushes_per_sec` | float | Hz | Batch flush rate (overhead proxy) |
| `burstiness` | float | [0,1] | Traffic burstiness metric (CoV of arrivals) |
| `backlog_age_p95_us` | float | µs | Age of oldest message in queue (95th pct) |

**Outputs**:
- `optimal_batch_threshold` ∈ {1, 4, 8, 16, 32, 64}
- `optimal_max_delay_us` ∈ {50, 200, 1000, 4000}

---

## Workload Types

### 1. Steady
- Constant arrival rate (e.g., 100 msg/s)
- Low variance in inter-arrival times
- Predictable message sizes
- Expected optimal: Moderate batching (16-32 threshold, 200-1000 µs delay)

### 2. Bursty
- Alternating quiet/burst phases
- High variance in arrival rate (CoV > 0.5)
- Bursts: 500-1000 msg/s for 100 ms
- Quiet: 10-50 msg/s for 1 s
- Expected optimal: Adaptive — high threshold during bursts, low threshold during quiet

### 3. Adversarial
- Random arrival patterns
- Message size variations (64 B - 4 KB)
- Sudden traffic spikes
- Expected optimal: Conservative (low threshold, short delay to cap tails)

---

## Empirical Oracle

For each telemetry sample, sweep all 24 configurations:

```python
for threshold in [1, 4, 8, 16, 32, 64]:
    for delay_us in [50, 200, 1000, 4000]:
        # Simulate 1-second window with these parameters
        batches = simulate_batching(traffic_trace, threshold, delay_us)

        # Measure latency distribution
        latency_p50 = percentile(batches.latencies, 50)
        latency_p95 = percentile(batches.latencies, 95)
        latency_p99 = percentile(batches.latencies, 99)

        # Measure overhead (flushes per second)
        overhead = len(batches) / duration

        # Measure throughput
        throughput = sum(batches.sizes) / duration

        # Objective
        J = α·latency_p95 + β·overhead + γ·max(0, target_throughput - throughput)

optimal_config = argmin(J)
```

**Weights (initial)**: α=1.0, β=10.0 µs, γ=0.1

**Rationale**:
- α=1.0: Latency is primary metric (microsecond units)
- β=10.0: Each flush has ~10 µs overhead (syscall + header)
- γ=0.1: Throughput penalty if below target

---

## Performance Metrics

| Metric | Description | Target |
|--------|-------------|--------|
| p95 latency | 95th percentile message latency | Minimize (vs baseline) |
| p99 latency | 99th percentile tail latency | Minimize |
| Throughput | Messages per second | ≥ baseline |
| Flush rate | Batches per second | Minimize (reduce overhead) |
| Decision stability | Config changes per second | < 1 Hz |
| Performance variance | Std(J) across configs | > 10% (learnable) |
| Model R² | Training set explained variance | > 0.4 |

---

## Expected Results

**Hypothesis**: Adaptive batching has strong learnable structure because:

1. **Queueing theory foundation**: Little's Law relates latency, throughput, queue length
2. **Traffic patterns predict optimal batching**:
   - High arrival rate → large batches amortize overhead
   - Bursty traffic → need adaptive thresholds
   - Low arrival rate → flush quickly to minimize latency
3. **Arrival rate correlation**: Expected >0.5 with batch threshold
4. **Burstiness correlation**: Expected >0.4 with delay tolerance

**Expected**:
- Performance variance: 15-30% across configurations
- Feature correlations: arrival_rate (>0.5), burstiness (>0.4), queue_depth (>0.3)
- Model R²: 0.5-0.7
- Gains: 15-25% p95 latency reduction vs fixed baseline

If these fail, we learn which traffic patterns resist adaptive batching (flat landscape on specific workloads).

---

## Comparison to Baseline Policies

### 1. Fixed Batching
- threshold=8, delay=1000 µs (typical default)
- No adaptation to traffic patterns

### 2. Nagle-like Algorithm
- Threshold=1, delay=200 µs
- Classic TCP-style coalescing

### 3. PID Controller
- Proportional-Integral-Derivative feedback
- Adjust threshold based on latency error
- Tuned Kp, Ki, Kd gains

### 4. Reflex (ML Model)
- Decision tree predicting {threshold, delay}
- Feature-based adaptation

---

## Integration with CHORUS

Success enables:
- **Chronome transport layer**: Adaptive batching for inter-ganglion messages
- **Message queue optimization**: Minimize latency for time-sensitive packets
- **Burst handling**: Automatically adjust to traffic spikes
- **Energy efficiency**: Reduce unnecessary wakeups during idle periods

Each Chronome node can:
1. Collect telemetry every 100 ms
2. Infer optimal batching params (<1 µs inference)
3. Apply new config to send queue
4. Measure impact and refine

---

## Related Work

- **Nagle's Algorithm** (RFC 896): Classic TCP small-packet coalescing
- **TCP_CORK**: Linux socket option for manual batching control
- **Interrupt coalescing**: NIC-level batching (ethtool -C)
- **Kernel bypass** (io_uring): Batch syscalls for efficiency
- **Google's TCP BBR**: Congestion control with pacing (related concept)

Our approach differs: **application-level batching tuned by tiny ML model**, not kernel heuristics.

---

## Theoretical Bounds

### Latency Lower Bound
Minimum latency = serialization delay + propagation delay
- Serialization: `msg_size / link_bandwidth`
- Propagation: `distance / speed_of_light`

Batching adds queueing delay: `queue_depth / dequeue_rate`

### Throughput Upper Bound
Maximum throughput = `link_bandwidth / (msg_size + header_overhead)`

Large batches → amortize header, approach bandwidth limit.

### Optimal Batch Size (M/M/1 Model)
From queueing theory:
```
optimal_batch = sqrt(2 * arrival_rate * setup_cost / holding_cost)
```

Our reflex should learn approximations of this without explicit formula.

---

## Implementation Notes

### Simulator Requirements
- Event-driven discrete simulator
- Message arrival events (Poisson or trace-based)
- Batch flush logic (threshold OR delay trigger)
- Latency tracking (enqueue timestamp → flush timestamp)
- Statistics collection (p50/p95/p99, throughput)

### Rust Simulator Structure
```rust
struct ChronomeSimulator {
    queue: VecDeque<Message>,
    config: BatchConfig,  // {threshold, delay}
    stats: LatencyStats,
    clock: SimulatedTime,
}

impl ChronomeSimulator {
    fn enqueue(&mut self, msg: Message) { ... }
    fn maybe_flush(&mut self) -> Option<Batch> { ... }
    fn step(&mut self, dt: Duration) { ... }
}
```

---

## References

- RFC 896: Nagle's Algorithm
- Leonard Kleinrock: Queueing Theory foundations
- Little's Law: L = λW
- TCP_CORK, TCP_NODELAY socket options
- CHORUS architecture: `chorus/ARCHITECTURE.md`
- Thread pool empirical methodology: `docs/reports/empirical-oracle-findings.md`
- Sensorium adaptive sampling: `docs/reports/sensorium-findings.md`

---

**Status**: Design phase (schema defined, implementation pending)
