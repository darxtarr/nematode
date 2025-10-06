# Offline Training

## Loop
1. Collect telemetry under different workloads.
2. Train small model offline (tree / linear / tiny MLP).
3. Quantize and export weights.
4. Serialize to `.reflex` binary.
5. Deploy and measure.

## Model Hints
| Type | Params | Size | Notes |
|------|---------|------|------|
| Decision Tree | depth ≤ 4 | < 4 KB | good default |
| Linear Regressor | d = 10–20 | < 2 KB | simple continuous control |
| MLP (2×32) | ~2k params | < 10 KB | use only if justified |

## Training Time
Minutes on CPU. No GPU needed.

## Evaluation Metrics
- median latency, p95, p99/p50 ratio
- throughput (MB/s or ops/s)
- oscillation count (how often the decision flips)
- CPU µs per inference
