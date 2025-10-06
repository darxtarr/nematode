# Compute Telemetry Schema v1

## Overview
Telemetry for thread-pool sizing reflexes.

## Features (10-dimensional)

| Index | Name | Type | Unit | Description |
|-------|------|------|------|-------------|
| 0 | `runq_len` | u32 | tasks | Current run queue length (waiting tasks) |
| 1 | `arrival_rate` | f32 | tasks/s | Task arrival rate (EWMA) |
| 2 | `completion_rate` | f32 | tasks/s | Task completion rate (EWMA) |
| 3 | `task_time_p50_us` | f32 | µs | Median task latency (enqueue → complete) |
| 4 | `task_time_p95_us` | f32 | µs | 95th percentile task latency |
| 5 | `worker_util` | f32 | [0,1] | Fraction of workers busy |
| 6 | `ctx_switches_per_sec` | f32 | /s | Context switches (estimated from thread churn) |
| 7 | `task_size_mean` | f32 | µs | Mean task execution time |
| 8 | `task_size_var` | f32 | µs² | Variance of task execution time |
| 9 | `idle_worker_count` | u32 | workers | Number of idle workers |

## Sampling
- Cadence: 2 Hz (every 500 ms)
- Window: 1 second sliding

## Outputs (Tunables)

| Output | Type | Range | Description |
|--------|------|-------|-------------|
| `n_workers` | u32 | [1, 64] | Number of worker threads |

## Normalization
Min-max scaling to [0, 1] computed from training data.

## Objective Function

```
J = α·p95_task_time + β·ctx_switch_cost + γ·idle_waste

where:
  α = 1.0     (prioritize tail latency)
  β = 0.05    (penalize thrashing)
  γ = 0.1     (penalize over-provisioning)
```

## Baseline Policy
Static: `n_workers = 8`

## Notes
- Modeled after Linux scheduler metrics
- Context switch cost is proxy (not actual syscalls in simulation)
- Future: add NUMA placement, CPU affinity
