# Experiment Playbook

Three canonical workload classes:

## 1. Steady
Uniform request rate, stable object size.
Goal: match or exceed baseline throughput with lower tail latency.

## 2. Bursty
Alternating high/low load periods.
Goal: maintain latency stability (p95 drift < 10 %).

## 3. Adversarial
Abrupt load and pattern shifts.
Goal: recover within < 1 s, avoid oscillation.

### Procedure
1. Run baseline heuristic, log metrics.
2. Train reflex with telemetry.
3. Replay workloads with reflex active.
4. Compare metrics → plot.
5. Run shadow mode for safety validation.

### Metrics to Record
- latency_{median,p95,p99}
- throughput
- jitter (MAD)
- oscillation rate
- CPU µs/inference
- rollback_count

### Success Criteria
⭐ 5 → ≥ 20 % tail-latency reduction, stable  
⭐ 4 → 10–20 % improvement  
⭐ 3 → equal but more stable  
< 3 → discard/retrain
