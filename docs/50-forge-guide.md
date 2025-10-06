# 🧱 Forge Guide
### From Trace → Oracle → Model → `.reflex`

This guide defines the reproducible path for creating a trained reflex.

---

## 1. Overview
A reflex is a deterministic model trained offline on telemetry traces.
The forge turns raw telemetry into a small binary (`.reflex`) that can be loaded by the runtime.

telemetry.csv ──→ oracle labeller ──→ model trainer ──→ quantizer ──→ .reflex


## 2. Telemetry → Feature Windows
- **Window length:** 200 ms
- **Step:** 100 ms (50 % overlap)
- **Features:**
  - `queue_depth`
  - `enqueue_rate`, `dequeue_rate`
  - `latency_p50`, `latency_p95`
  - `bytes_in_per_sec`, `bytes_out_per_sec`
  - `packet_size_mean`, `packet_size_var`
  - `rtt_ewma`
- Normalize each feature to `[0,1]` using per-trace min/max.

## 3. Oracle Labelling
For each window:
1. Replay packets through an *oracle simulator* that exhaustively tests discrete policy pairs:
   - `flush_threshold ∈ {1,4,8,16,32,64}`
   - `max_batch_delay ∈ {50µs,200µs,1ms,4ms}`
2. Compute objective  
   `J = p95_latency + λ·batch_overhead`
   (start λ = 0.1)
3. Choose `(threshold, delay)` giving minimal J.  
   These become labels.

Store `(features, threshold, delay, J)` in `training-set.csv`.


## 4. Training
Train two small supervised models:

| Target | Type | Max Depth | Output |
|---------|------|------------|---------|
| `flush_threshold` | DecisionTreeRegressor | 4 | discrete value |
| `max_batch_delay` | DecisionTreeRegressor | 4 | discrete value |

Fit on 80 % of windows, validate on 20 %.


## 5. Quantization
Convert weights / thresholds to `int16`.
Clamp outputs to legal ranges.
Pack metadata:


created_at: 2025-10-06T12:00Z
telemetry_hash: sha1(telemetry.csv)
trainer_commit: forge@abcdef
lambda: 0.1
feature_schema: v1

## 6. Serialize to .reflex
Use the binary layout:

Section	    Description
Header	    NEM1 magic, version, feature_count, output_count
Model	    tree nodes (feature_idx, threshold, left, right, leaf_value)
Bounds	    per-output min/max
Metadata	UTF-8 YAML
Checksum	CRC32

## 7. Validation

Before promotion:
Run in shadow mode 10 min (no actuation).
Compute expected ∆p95 and oscillation rate.
Promote only if ∆p95 ≤ –10 % and oscillations ≤ 1 / 30 s.