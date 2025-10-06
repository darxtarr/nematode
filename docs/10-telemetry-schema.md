# Telemetry Schema

Telemetry is recorded as rolling statistics of system behavior.

| Field | Type | Range | Notes |
|-------|------|--------|-------|
| queue_depth | u32 | 0–1024 | Pending requests / commands |
| latency_mean | f32 | ms | 100 ms window average |
| latency_p95 | f32 | ms | 95th percentile |
| latency_jitter | f32 | ms | stddev |
| bytes_in | f64 | B/s | smoothed |
| bytes_out | f64 | B/s | smoothed |
| req_size_mean | f32 | B | mean object size |
| rw_ratio | f32 | 0–1 | read / write balance |
| cache_hit_ratio | f32 | 0–1 | optional |
| cpu_util | f32 | 0–1 | normalized |
| ctx_switches | u32 | /s | system noise indicator |

Normalization: min–max per session → [0, 1].  
Windows: 100 ms–1 s sliding.

Each sample is timestamped and stored in `data/telemetry/*.csv`.
