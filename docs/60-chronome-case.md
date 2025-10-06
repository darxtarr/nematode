# ⚙️ Case Study: Chronome Adaptive Batching Reflex

---

## 1. Problem Statement
Chronome streams semantic packets between ganglia.
Current batching heuristic is static:
> flush when queue ≥ 16 packets or 500 µs elapsed.

This fails under variable load:
- Small batches → high CPU, low latency.
- Large batches → good throughput, bad tail latency.
- Static threshold → bad everywhere.

---

## 2. Reflex Hypothesis
A tiny model trained on telemetry can infer the right `(flush_threshold, max_batch_delay)` for each regime.

---

## 3. Inputs & Outputs

| Category | Name | Unit | Notes |
|-----------|------|------|-------|
| **Inputs** | queue_depth | packets | instantaneous backlog |
| | enqueue_rate | pkts/s | |
| | latency_p50, latency_p95 | µs | rolling stats |
| | bytes_in/out_per_sec | B/s | throughput |
| | packet_size_mean/var | B, B² | |
| | rtt_ewma | µs | |
| **Outputs** | flush_threshold | {1,4,8,16,32,64} | |
| | max_batch_delay | {50µs,200µs,1ms,4ms} | |

Decision cadence = 10 Hz.  
Minimum hold time = 300 ms.

---

## 4. Baselines
1. **Static heuristic** (current).  
2. **PID-like control**:

e = target_p95 − observed_p95
threshold_next = clamp(threshold + Kpe + Ki∑e + Kd*Δe)

Tuned by grid-search on same traces.



## 5. Workloads

| Name | Pattern | Description |
|-------|----------|-------------|
| Steady | Poisson λ = 1k/s, 1 KB pkts | baseline |
| Bursty | 5 s @ 5k/s ↔ 5 s @ 100/s | regime shifts |
| Adversarial | random phase, bimodal sizes, RTT jitter | stress test |



## 6. Metrics

| Symbol | Definition | Target |
|---------|-------------|--------|
| p95 | 95th % latency | ↓ |
| p99/p50 | tail ratio | ↓ |
| Throughput | pkts/s | ≥ baseline |
| Oscillations | decisions / min | ↓ |
| Inference µs | CPU cost | < 1 µs |



## 7. Success Criteria

| Workload | Reflex vs Baseline | Reflex vs PID |
|-----------|-------------------|---------------|
| Steady | p95 –10 % | ≥ |
| Bursty | p95 –15 %, fewer flips | ≥ |
| Adversarial | stable, no rollback | ≥ |



## 8. Safety Rails
- **Hysteresis:** ignore changes < 5 % predicted gain.  
- **Freeze:** Mahalanobis > τ for K windows → hold last.  
- **Rollback:** p95 ↑ > 20 % for 2 s → revert.  
- **Logging:** every decision + telemetry snapshot.  
- **Provenance:** metadata block in `.reflex`.



## 9. Deliverables
- Telemetry traces (`data/telemetry/chronome-*`)
- Oracle label CSV
- Trained `.reflex`
- Evaluation plots (CDFs, throughput, oscillations)
- Report comparing Baseline / PID / Reflex