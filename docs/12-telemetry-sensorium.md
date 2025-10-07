# Telemetry Schema — Sensorium Adaptive Sampling
**Domain**: Sensing / Robotics
**Tablet**: 🜆 6
**Version**: v1
**Date**: 2025-10-07

---

## Purpose

Define telemetry schema for adaptive sampling rate reflex. The reflex observes signal characteristics and power constraints to dynamically adjust sampling frequency, minimizing energy while maintaining reconstruction quality.

---

## Signal Model

**Environment**: Continuous analog signal `s(t)` sampled at discrete intervals.

**Control Knob**: `sampling_rate_hz` ∈ {1, 2, 5, 10, 20, 50, 100}

**Objective**: Minimize `J = α·RMSE + β·energy + γ·staleness`

---

## Telemetry Features (10 inputs → 1 output)

| Feature | Type | Unit | Description |
|---------|------|------|-------------|
| `signal_variance` | float | V² | Variance of recent window (16 samples) |
| `signal_mean` | float | V | Mean level (DC offset) |
| `dominant_freq_hz` | float | Hz | Estimated dominant frequency (FFT peak) |
| `freq_energy_ratio` | float | [0,1] | Energy in dominant freq / total energy |
| `zero_crossings_per_sec` | float | Hz | Activity metric (how fast signal oscillates) |
| `sample_age_ms` | float | ms | Time since last sample (freshness) |
| `reconstruction_error_ewma` | float | V | EWMA of recent reconstruction error |
| `power_budget_pct` | float | % | Remaining power budget [0-100] |
| `event_rate_hz` | float | Hz | Rate of significant events (threshold crossings) |
| `signal_snr_db` | float | dB | Estimated signal-to-noise ratio |

**Output**: `optimal_sampling_rate_hz` ∈ {1, 2, 5, 10, 20, 50, 100}

---

## Workload Types

### 1. Steady
- Single sinusoid: `s(t) = A·sin(2πft) + noise`
- Frequency: 0.5-10 Hz
- SNR: 20-40 dB
- Expected optimal: Near Nyquist (2× dominant freq)

### 2. Bursty
- Quiet periods (low variance) alternating with bursts
- `s(t) = A(t)·sin(2πf(t)·t) + noise`
- A(t): envelope function with 10-90% duty cycle
- Expected optimal: Low rate in quiet, high rate in bursts

### 3. Adversarial
- Non-stationary frequency sweeps
- Random SNR changes (10-40 dB)
- Sudden event injections
- Expected optimal: Adaptive tracking with hysteresis

---

## Empirical Oracle

For each telemetry sample, sweep all 7 sampling rates and measure:

```python
for rate in [1, 2, 5, 10, 20, 50, 100]:
    sampled_signal = sample(true_signal, rate, duration=1.0)
    reconstructed = reconstruct(sampled_signal)  # linear interpolation
    rmse = compute_rmse(true_signal, reconstructed)
    energy = rate * ENERGY_PER_SAMPLE  # mJ
    staleness = 1000.0 / rate  # ms (max age)

    J = α·rmse + β·energy + γ·staleness

optimal_rate = argmin(J)
```

**Weights (initial)**: α=1.0, β=0.01, γ=0.001

---

## Performance Metrics

| Metric | Description | Target |
|--------|-------------|--------|
| Reconstruction RMSE | Quality of signal recovery | Minimize |
| Energy consumption | mJ per second | Minimize |
| Max staleness | Worst-case sample age | < 100 ms |
| Decision stability | Sampling rate changes per second | < 0.1 Hz |
| Performance variance | Std(J) across rates | > 5% (learnable) |
| Model R² | Training set explained variance | > 0.3 |

---

## Expected Results

**Hypothesis**: Unlike thread pool sizing (R²=0.035), adaptive sampling should have strong learnable structure because:

1. **Nyquist theorem provides theoretical foundation** (need 2× dominant freq)
2. **Energy-quality tradeoff is nonlinear** (diminishing returns at high rates)
3. **Signal variance predicts optimal rate** (high variance → need more samples)

**Expected**:
- Performance variance: 10-30% across sampling rates
- Feature correlations: signal_variance (>0.4), dominant_freq (>0.5)
- Model R²: 0.4-0.7 (vs thread pool's 0.035)
- Gains: 20-40% energy savings vs fixed-rate baseline

If these expectations fail, we discover a *second* heuristic-saturated domain, which is scientifically valuable.

---

## Integration with CHORUS

Success here enables:
- Adaptive camera frame rates (Sensorium vision nodes)
- Audio VAD-aware sampling (microphone ganglia)
- IMU motion-based gyro/accel adjustment
- Network packet capture rate modulation

Each Sensorium ganglion can load a `.reflex` model and optimize its own power-quality tradeoff locally.

---

## References

- Shannon-Nyquist sampling theorem
- Compressive sensing literature
- Rate-distortion theory (Cover & Thomas)
- Thread pool empirical oracle methodology (docs/reports/empirical-oracle-findings.md)

---

**Status**: Design phase (schema defined, implementation pending)
