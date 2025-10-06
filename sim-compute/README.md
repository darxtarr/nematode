# Thread Pool Sizing Simulator

**Domain**: Compute / Scheduling
**Tablet**: 🜃 3
**Status**: v1 baseline (oracle tuning pending)

## Quick Start

### Build
```bash
cargo build --release -p sim-compute
```

### Run Baseline (Static N=8)
```bash
./target/release/baseline-compute
```

### Run Reflex (Adaptive N from .reflex model)
```bash
# Requires: data/models/thread-pool.reflex + normalizer-compute.json
./target/release/reflex-compute
```

## Architecture

### Simulator Components

**ThreadPoolSim**
- Task queue (VecDeque)
- Worker pool (dynamic sizing)
- Policy interface (BaselinePolicy | ReflexPolicy)
- Telemetry collection (10 features, 2 Hz)
- Metrics tracking (p50/p95/p99, throughput, decision changes)

**Workload Generators**
- `SteadyWorkload`: Poisson arrivals, constant rate
- `BurstyWorkload`: Alternating high/low phases
- `AdversarialWorkload`: Random rate + work variations

### Telemetry Schema (compute-v1)

10 features → 1 output:
```rust
runq_len              → n_workers ∈ [1,64]
arrival_rate
completion_rate
task_time_p50_us
task_time_p95_us
worker_util
ctx_switches_per_sec
task_size_mean
task_size_var
idle_worker_count
```

See `docs/11-telemetry-compute.md` for full spec.

## Training Pipeline

### 1. Generate Synthetic Telemetry
```bash
source venv/bin/activate
python3 forge/gen_synthetic_telemetry_compute.py data/telemetry/compute-training.csv
```

Produces 2000 samples (800 steady + 600 bursty + 600 adversarial)

### 2. Label with Oracle
```bash
python3 forge/oracle_compute.py \
  data/telemetry/compute-training.csv \
  data/telemetry/compute-labeled.csv \
  [alpha] [beta] [gamma]
```

Default weights: α=1.0, β=0.05, γ=0.1

**Objective**: `J = α·p95_task + β·ctx_switches + γ·idle_waste`

**Known Issue (v1)**: γ=0.1 too aggressive → all samples labeled N=2

### 3. Train Decision Tree
```bash
python3 forge/trainer_compute.py \
  data/telemetry/compute-labeled.csv \
  data/models/thread-pool.reflex \
  data/models/normalizer-compute.json
```

Exports:
- `thread-pool.reflex` (325 bytes, single-output decision tree)
- `normalizer-compute.json` (min-max scaling bounds)

### 4. Validate
```bash
./target/release/baseline-compute   # Static N=8
./target/release/reflex-compute     # Adaptive (currently N=2 due to oracle bias)
```

## Current Results (v1)

**Workload**: Steady 100 tasks/sec, 500µs/task, 10s

| Metric | Baseline (N=8) | Reflex (N=2) | Δ |
|--------|----------------|--------------|---|
| p50 task time | 10,386 µs | 10,243 µs | −1.4% |
| p95 task time | 10,637 µs | 10,293 µs | **−3.2%** |
| p99 task time | 10,698 µs | 10,358 µs | −3.2% |
| Throughput | 96.26 tasks/s | 97.62 tasks/s | +1.4% |

**Interpretation**: Small improvement despite trivial model (constant N=2).
Validates infrastructure but doesn't demonstrate adaptive behavior.

## Next Steps

### Oracle Tuning (v2)
Reduce idle penalty, add queue backlog term:

```python
# Current (v1)
J = 1.0·p95 + 0.05·ctx_switches + 0.1·idle_waste

# Proposed (v2)
J = 1.0·p95 + 0.01·ctx_switches + 0.005·idle_waste + 0.5·max(0, runq_len - 5)
```

Expected: Label diversity across N∈{2,4,8,16,32}

### Validation Checklist
- [ ] Oracle produces diverse labels (not all N=2)
- [ ] Reflex shows adaptive behavior across workloads
- [ ] Performance gains ≥10% on p95 for bursty workload
- [ ] Decision oscillation ≤ 0.1 Hz
- [ ] Model size ≤ 1 KB

### Future Enhancements
- Real workload traces (Rayon, Tokio benchmarks)
- NUMA placement (extend to 2D output: `{n_workers, numa_node}`)
- CPU affinity simulation
- Thread migration costs
- Work-stealing metrics

## References

- **Design**: `docs/11-telemetry-compute.md`
- **Results**: `docs/reports/thread-pool-v1.md`
- **Catalog**: `7×7_TML_catalog.md` (Compute section)
- **Phase 1**: `plan/PHASE1_CALIBRATION.md` (Tablet 🜃 3)

---

**Commit**: 5c7515d (baseline v1)
**Dataset Hash**: fa5721a4
**Model Size**: 325 bytes
**Δ p95**: −3.2%
