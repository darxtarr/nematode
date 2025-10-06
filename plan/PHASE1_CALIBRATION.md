# 🌱 Phase 1 — Calibration  
*(Seven-Tablet Validation of Tiny-ML Reflexes)*

Purpose:  
Verify that the Nematode forge generalizes beyond Chronome by training and testing one reflex per domain.  
Each seed will run through the complete loop  
→ telemetry → oracle → train → `.reflex` → replay → metrics → report.

Duration: ≈ 2 weeks (one per day, with weekends for analysis).

---

## ⌘ Experiment Matrix

| Tablet | Domain | Reflex | Primary Metric | Lead | Status | Dataset Hash | Reflex Size (bytes) | Δ p95 Latency / Tail Metric | Notes |
|:--:|:--|:--|:--|:--|:--|:--|:--|:--|:--|
| 🜁 1 | **Networking / Transport** | *Chronome Batching v2* – adaptive `{threshold, delay}` | p95 latency | Sonny | ☐ planned | — | — | — | baseline validated |
| 🜂 2 | **Storage / I-O** | *Prefetch Depth* – choose `{32–512 KB}` | read hit ratio vs tail latency | Gemma | ☐ planned | — | — | — | synthetic fio trace |
| 🜃 3 | **Compute / Scheduling** | *Thread-Pool Size* – adjust `N_threads` | throughput vs p95 task time | Sonny | ☐ planned | — | — | — | Rayon microbench |
| 🜄 4 | **Graphics / WebGPU** | *Frame-Pacing Reflex* – modulate `present_delay` | frame-time jitter | Gemma | ☐ planned | — | — | — | WRWW sim harness |
| 🜅 5 | **Compression / Codec** | *Adaptive Level* – choose `{off,1,3,6}` | compression ratio vs CPU µs | Sonny | ☐ planned | — | — | — | dataset : text + binary |
| 🜆 6 | **Sensing / Robotics** | *Sampling-Rate Reflex* – tune Hz based on variance | energy vs event miss rate | Gemma | ☐ planned | — | — | — | sensor log replay |
| 🜇 7 | **Energy / Thermal / Power** | *DVFS Governor Hint* – pick {perf, balanced, save} | QoS miss vs power draw | Sonny | ☐ planned | — | — | — | CPU sim trace |

---

## 🧩 For Each Reflex

1. **Telemetry Source**  
   - Describe synthetic or captured dataset (sampling rate, features, duration).

2. **Oracle Definition**  
   - What discrete or continuous grid defines “optimal”?  
   - Objective J = ( α·tail + β·overhead + γ·stability )

3. **Model Type & Training Time**  
   - Decision Tree ≤ depth 4 unless justified.  
   - Record training minutes and CPU spec.

4. **Runtime Deployment**  
   - `.reflex` size (bytes)  
   - Inference µs (average of 1 k calls)

5. **Evaluation Metrics**  
   - p50/p95/p99 latency or domain-specific equivalent  
   - throughput or power/energy  
   - oscillation rate  
   - rollback events

6. **Result Summary**  
   - Table (Baseline vs Reflex vs PID if applicable)  
   - Plot CDF and time-series  
   - 1-paragraph interpretation

7. **Artifacts to Commit**  
   - `data/telemetry/<reflex>.csv`  
   - `models/<reflex>.reflex`  
   - `runs/YYYYMMDD/<reflex>/metrics.json`  
   - `docs/reports/<reflex>.md`

---

## 🧠 Mentat Review Checklist
- [ ] Reflex behaves deterministically (flip rate ≤ 0.1 Hz).  
- [ ] Gains ≥ 10 % on primary metric.  
- [ ] No safety violations (rollbacks = 0).  
- [ ] Training time ≤ 15 min on CPU.  
- [ ] Model ≤ 1 KB binary.  
- [ ] Findings added to Seven Seeds Report.

---

## 🧾 Schedule Template
| Day | Reflex | Lead | Expected Runtime | Status |
|------|---------|------|------------------|--------|
| D1 | Chronome Batching v2 | Sonny | ~30 min training + 5 min replay | ☐ |
| D2 | Prefetch Depth | Gemma | ~15 min | ☐ |
| D3 | Thread-Pool Size | Sonny | ~20 min | ☐ |
| D4 | Frame-Pacing Reflex | Gemma | ~25 min | ☐ |
| D5 | Adaptive Compression | Sonny | ~15 min | ☐ |
| D6 | Sampling-Rate Reflex | Gemma | ~20 min | ☐ |
| D7 | DVFS Governor Hint | Sonny | ~30 min | ☐ |

---

### 📦 Deliverable
`reports/SEVEN_SEEDS_SUMMARY.md`  
For each seed:  model stats + performance gains + stability notes + insight on transferability.

> Completion of Phase 1 → Tag `v0.3.0-SevenSeeds`.
