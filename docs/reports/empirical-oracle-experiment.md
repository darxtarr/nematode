# Empirical Oracle Experiment - Research Log

**Date**: 2025-10-06
**Status**: Setup Complete ✅ | Overnight Run Pending ⏳
**Researcher**: Sonny + Human

---

## Research Question

**Does the analytical oracle's model of thread-pool performance match empirical reality?**

Analytical oracle uses a cost function:
```
J = α·p95_task_time + β·ctx_switch_cost + γ·idle_waste
```

But this is just our *guess*. We can run actual simulations to measure ground truth.

---

## Key Findings (So Far)

### 🔴 Analytical Oracle is Degenerate
- **All 2000 samples labeled as N=2** (100% bias)
- Idle penalty (γ=0.1) dominates the objective function
- No adaptive behavior learned

### 🎯 Empirical Sweeps Show Task-Size Dependency

Manual sweeps revealed optimal N varies with task size:

| Task Size | Optimal N | Empirical p95 |
|-----------|-----------|---------------|
| 100 µs    | N=16      | 10,291 µs     |
| 500 µs    | N=8       | 10,273 µs     |
| 2000 µs   | N=4       | 10,273 µs     |

**Pattern**: Smaller tasks → more workers (parallelism)
**Pattern**: Larger tasks → fewer workers (less context switching)

### ✅ Small Empirical Test (10 samples)

Label distribution from empirical simulation:
- N=1: 2 samples
- N=2: 2 samples
- N=8: 3 samples
- N=32: 2 samples
- N=64: 1 sample

**Diversity achieved!** vs. analytical: 100% N=2

---

## Experimental Pipeline

### Infrastructure Built

1. **`sweep` binary** (`sim-compute/src/bin/sweep.rs`)
   - Runs simulation across N ∈ {1,2,4,8,16,32,64}
   - Measures actual p50/p95/p99 latency + throughput
   - Returns empirically optimal N

2. **`oracle_compute_empirical.py`**
   - Extracts workload params from telemetry (arrival_rate, task_size_mean)
   - Calls `sweep` for each sample
   - Labels with empirically optimal N
   - **Incremental saving**: appends after each sample (resume-safe!)

3. **Parallelization scripts**
   - `split_telemetry.py`: Split CSV into chunks
   - `parallel_empirical.sh`: Generate parallel commands
   - `merge_empirical.py`: Merge results after completion

---

## Overnight Run Instructions

### Setup Complete ✅

Data split into **10 chunks** of 200 samples each.
Each chunk takes ~400s (6.7 min) at 2s/sample.

### Commands for Parallel Execution

**Option 1: Manual (10 terminals)**

```bash
# Terminal 0
cd /home/u/code/reflex
source venv/bin/activate && python forge/oracle_compute_empirical.py data/telemetry/chunks/chunk_000.csv data/telemetry/empirical-results/empirical_000.csv all 2 2>&1 | tee data/telemetry/empirical-results/log_0.txt

# Terminal 1
cd /home/u/code/reflex
source venv/bin/activate && python forge/oracle_compute_empirical.py data/telemetry/chunks/chunk_001.csv data/telemetry/empirical-results/empirical_001.csv all 2 2>&1 | tee data/telemetry/empirical-results/log_1.txt

# ... (repeat for chunks 2-9)
```

**Option 2: GNU Parallel (automated)**

```bash
cd /home/u/code/reflex
parallel -j 10 'source venv/bin/activate && python forge/oracle_compute_empirical.py data/telemetry/chunks/chunk_{}.csv data/telemetry/empirical-results/empirical_{}.csv all 2 > data/telemetry/empirical-results/log_{}.txt 2>&1' ::: $(seq -w 0 9)
```

### After Completion

Merge results:
```bash
source venv/bin/activate
python forge/merge_empirical.py data/telemetry/empirical-results data/telemetry/compute-empirical-full.csv
```

### Progress Monitoring

Check progress anytime:
```bash
# See how many samples completed in each chunk
wc -l data/telemetry/empirical-results/empirical_*.csv

# Watch live progress
tail -f data/telemetry/empirical-results/log_0.txt
```

### Resume-Safe ✅

If a job crashes/times out:
- Already-processed samples saved incrementally
- Just re-run the same command
- Script auto-detects existing results and resumes

---

## Next Steps (After Overnight Run)

1. **Merge & Analyze**
   - Label distribution (expect diversity!)
   - Feature correlations with optimal N
   - Compare to analytical oracle predictions

2. **Train Reflex on Empirical Labels**
   ```bash
   python forge/trainer_compute.py data/telemetry/compute-empirical-full.csv data/models/thread-pool-empirical.reflex
   ```

3. **Validation**
   - Run baseline vs reflex-empirical comparison
   - Measure p95 improvement
   - Check adaptive behavior

4. **Science Questions**
   - Can we reverse-engineer objective weights from empirical labels?
   - Does empirical-trained reflex beat analytical oracle?
   - What features matter most?

---

## Files Created

### Code
- `sim-compute/src/bin/sweep.rs` - Pool size sweeper
- `forge/oracle_compute_empirical.py` - Empirical labeller (incremental)
- `forge/split_telemetry.py` - Chunk splitter
- `forge/parallel_empirical.sh` - Parallel setup script
- `forge/merge_empirical.py` - Result merger

### Data
- `data/telemetry/chunks/chunk_*.csv` - 10 chunks of 200 samples
- `data/telemetry/empirical-results/` - Output directory (will contain results)

### Docs
- This file!

---

## Research Notes

### Why Empirical Approach?

The analytical oracle makes assumptions:
- Queue delay formula: `(arrival_rate - capacity) / capacity × 1000 µs`
- Context switch cost: `n_workers × 10 µs`
- Idle waste: `idle_workers × 50 µs`

These are **model parameters**, not measured reality. By running actual simulations, we can:
1. Validate the model assumptions
2. Discover where they break down
3. Generate true ground-truth labels
4. Compare analytical vs empirical approaches

This is *real science* - testing our models against reality!

### Hypothesis

The analytical oracle over-penalizes idle workers, causing it to always choose N=2. Empirical measurements will show that moderate idle capacity (N=4 to N=16) actually produces better tail latency at minimal cost.

### Interesting Observations

From manual sweeps, p95 latency is **remarkably flat** across N∈{1,2,4,8}:
- All within ~70µs (< 1% variation)
- Suggests threshold is very fine-grained
- May explain why oracle struggles - signal is weak!

---

## Timeline

- **2025-10-06 Evening**: Setup complete, ready for overnight run
- **2025-10-07 Morning**: Check results, merge, analyze
- **2025-10-07 Afternoon**: Train + validate empirical reflex

---

## To Be Continued...

Paste results here tomorrow morning! 🌅
