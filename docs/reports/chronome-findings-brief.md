# Chronome Adaptive Batching — Research Findings (Brief)

**Date**: 2025-10-07  
**Experiment**: Adaptive batching for network transport (threshold + delay tuning)  
**Status**: ✅ COMPLETE (structure found, tradeoff sensitivity discovered)

---

## Key Results

### Model Performance
- **Test R² = 0.475** (avg of threshold=0.398, delay=0.552)
- **Feature correlations**: arrival_rate (+0.707), queue_depth (+0.655-0.706) ⭐
- **Performance variance**: CoV = 0.583 (58.3%)
- **Model size**: 5.3 KB (two decision trees)

**Verdict**: **REFLEX-VIABLE** — learnable structure detected (R² > 0.3)

### Validation Results
- **Flush rate**: -17.8% (reduced overhead) ✅
- **p95 latency**: +14.5% (increased) ⚠️
- **p99 latency**: +9.4% (increased)

**Interpretation**: Model learned to reduce flushes but over-optimized, trading too much latency for overhead reduction.

---

## Scientific Insights

### 1. Curvature Spectrum Position

| Domain | Test R² | Variance | Position |
|--------|---------|----------|----------|
| Thread Pool | 0.035 | 0.17% | Flat |
| **Chronome** | **0.475** | **58.3%** | **Moderate** ⭐ |
| Sensorium | 0.582 | 76.6% | High |

**Chronome sits in the middle** — more structure than thread pools, less than sensor sampling.

### 2. Objective Function Sensitivity

The empirical oracle used:
```
J = 1.0·p95_latency + 20.0·flush_rate
```

**Lesson**: BETA=20 made overhead reduction dominant. The model correctly optimized the objective but the weights may not reflect real-world priorities.

**Next iteration**: Try BETA=5-10 for better latency-overhead balance.

### 3. Multi-Dimensional Output Complexity

Training two separate trees (threshold + delay) worked well:
- Threshold tree: R²=0.398
- Delay tree: R²=0.552 (better prediction)

Delay is more predictable from arrival rate than threshold.

---

## Comparison to Sensorium

| Metric | Sensorium | Chronome |
|--------|-----------|----------|
| Test R² | 0.582 | 0.475 |
| Validation gains | -3.7% (better) | +14.5% (worse) |
| Flush/overhead | -17.5% energy | -17.8% flushes |

**Both learned structure**, but Sensorium's objective was better-tuned.

---

## Artifacts

- `forge/gen_synthetic_telemetry_chronome.py` — Traffic generator
- `forge/oracle_chronome_empirical.py` — Empirical oracle (24 configs)
- `forge/trainer_chronome.py` — Two-output trainer
- `forge/validate_chronome.py` — Validation harness
- `data/models/chronome.reflex` — 5.3 KB model
- `data/telemetry/chronome-labeled.csv` — 2000 labeled samples

---

## Next Steps

1. **Retune objective**: BETA=5-10 for better latency-overhead balance
2. **Extended validation**: Test on real network traces (not synthetic)
3. **PID comparison**: Compare reflex vs classical PID controller
4. **CHORUS integration**: Deploy to actual Chronome transport layer

---

## Conclusion

Chronome adaptive batching has **moderate learnable structure** (R²=0.475), validating our reflex methodology. The model successfully learned traffic patterns but the objective function needs rebalancing.

This is **valuable negative-ish result** — it shows:
1. ✅ Structure exists (R² proves it)
2. ✅ Model learned the objective (reduced flushes)
3. ⚠️ Objective weights need tuning (over-optimized for overhead)

**Status**: Tablet 🜁 1 (Chronome) → ✅ REFLEX-VIABLE (with caveats)

---

🪱 Research complete!
