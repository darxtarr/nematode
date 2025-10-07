# 🪱 Reflex Research Roadmap — 7×7 Tiny-ML Domains
**Date:** 2025-10-08
**Purpose:** Identify domains with measurable curvature (non-flat performance landscapes) suitable for sub-kilobyte reflexes.
**Format:** Each row = target domain; each column = core design axes for reflex viability.

---

## 1. Chronome — Adaptive Batching (Network)
| Axis | Description |
|------|--------------|
| Signal Source | queue_depth, latency_p95, packet_var |
| Reflex Output | flush_threshold, max_delay_us |
| Metric | p95 latency ↓, throughput ↑ |
| Learnability | medium–high (bursty patterns) |
| Feasibility | proven pipeline |
| Training Time | minutes |
| Integration | direct with CHORUS transport |

---

## 2. Alembic — Compression Policy
| Axis | Description |
|------|--------------|
| Signal Source | chunk_size, entropy, cpu_util, backlog |
| Reflex Output | codec_choice, window_len |
| Metric | bytes_out ↓, CPU cost ↓ |
| Learnability | high (clear tradeoff curve) |
| Feasibility | trivial to simulate |
| Integration | CHORUS storage path |

---

## 3. Sensorium — Adaptive Sampling
| Axis | Description |
|------|--------------|
| Signal Source | signal_var, freq_spectrum, backlog, power_state |
| Reflex Output | sampling_rate_hz |
| Metric | reconstruction error vs energy cost |
| Learnability | high (nonlinear signal variance) |
| Feasibility | use synthetic sinusoid + noise workloads |
| Integration | input stage daemon |

---

## 4. Compute — Thread Pool / Core Affinity
| Axis | Description |
|------|--------------|
| Signal Source | runq_len, util, task_us |
| Reflex Output | n_workers |
| Metric | p95 latency ↓ |
| Learnability | low (flat surface proven) |
| Feasibility | done |
| Integration | baseline reference for others |

---

## 5. Motor — BLDC Timing Reflex
| Axis | Description |
|------|--------------|
| Signal Source | back_emf, rpm, torque, temp |
| Reflex Output | commutation_advance_deg |
| Metric | torque ripple ↓, efficiency ↑ |
| Learnability | high (strong nonlinearities) |
| Feasibility | can simulate easily with simple EMF model |
| Integration | physical daemon candidate |

---

## 6. PID Auto-Tuning
| Axis | Description |
|------|--------------|
| Signal Source | error_t, d_error_t, system_gain |
| Reflex Output | kp, ki, kd gains |
| Metric | settling_time ↓, overshoot ↓ |
| Learnability | medium (bounded regions) |
| Feasibility | single-eq sim (mass-spring) |
| Integration | control loop library |

---

## 7. Velocity Planner — 3-D Printer / CNC
| Axis | Description |
|------|--------------|
| Signal Source | accel_cmd, jerk, previous_seg, vibration_feedback |
| Reflex Output | next_velocity |
| Metric | overshoot ↓, print_time ↓ |
| Learnability | high (discontinuities, jerk limits) |
| Feasibility | high via G-code replayer + IMU sim |
| Integration | mechanical control daemon |

---

## Reflex Taxonomy Matrix (7 × 7)
| Domain ↓ / Property → | Learnability | Input Bandwidth | Output Dim | Cost/Benefit | Safety Risk | Simulation Ease | Integration Priority |
|-----------------------|--------------|-----------------|-------------|--------------|--------------|------------------|----------------------|
| Chronome | ★★★★☆ | M | 2 | H | L | ★★★★☆ | 1 |
| Alembic | ★★★★★ | M | 2 | H | L | ★★★☆☆ | 2 |
| Sensorium | ★★★★★ | H | 1 | M | M | ★★★★★ | 3 |
| Compute | ★☆☆☆☆ | L | 1 | L | L | ★★★★★ | ref |
| Motor | ★★★★★ | M | 1 | H | M | ★★★☆☆ | 4 |
| PID-Tuner | ★★★★☆ | L | 3 | M | M | ★★★★☆ | 5 |
| Velocity Planner | ★★★★★ | H | 1 | H | H | ★★★☆☆ | 6 |

Legend: ★ = relative strength (1–5).

---

## Immediate Candidates (Next Three)
1. **Chronome** — continue with adaptive batching (ongoing).
2. **Alembic** — compression policy (clear compression ratio vs CPU tradeoff).
3. **Sensorium** — adaptive sampling rate (nonlinear feedback, excellent curvature).

Each yields rapid results (<1 h training) and clear baseline comparisons.

---

**Mentat Directive:**
When a reflex experiment ends in a flat landscape (<1 % variance), mark the domain *heuristic-saturated*.
When >5 % variance and R² > 0.3 → mark *reflex-viable*.
Store findings in `docs/reports/<domain>-findings.md`.

🪱 *End of Document*
