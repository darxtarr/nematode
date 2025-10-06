# 🧪 Threats to Validity & Mitigations


## 1. Overfitting to Synthetic Traces
**Risk:** reflex memorizes workload shapes.
**Mitigation:**
- Mix steady + bursty traces during training.
- Hold out unseen patterns for test.
- Regularize (max_depth ≤ 4, min_samples_leaf > 20).


## 2. Unrealistic Metrics
**Risk:** evaluating internal transport latency only.
**Mitigation:** measure *end-to-end* app latency including flush + downstream.


## 3. Reflex Oscillation
**Risk:** rapid alternation between decisions.
**Mitigation:**
- Enforce 300 ms hold time.
- Hysteresis threshold = 5 % predicted gain.
- Log flip frequency.


## 4. Control-theory Unfairness
**Risk:** poorly tuned PID looks bad.
**Mitigation:** grid-search Kp, Ki, Kd on identical traces before comparison.


## 5. Out-of-Distribution Inputs
**Risk:** unseen workload causes unsafe decisions.
**Mitigation:**
- Mahalanobis distance monitor → freeze reflex.
- Auto-shadow new telemetry for retraining.


## 6. Metric Noise
**Risk:** low traffic → volatile percentiles.
**Mitigation:** minimum sample window = 100 packets before computing stats.


## 7. Measurement Bias
**Risk:** training traces recorded at different sampling rates.
**Mitigation:** resample to canonical 100 ms step before processing.


## 8. Confirmation Bias
**Risk:** visually preferring reflex plots.
**Mitigation:** blind comparison: anonymize plots A/B before rating.


## 9. Engineering Drift
**Risk:** changes in telemetry schema break reflex compatibility.
**Mitigation:** schema hash in `.reflex` header; loader rejects mismatch.


## 10. Runaway Optimism
**Risk:** assuming all heuristics can be replaced.
**Mitigation:** document each success/failure; only generalize after ≥3 distinct wins.
