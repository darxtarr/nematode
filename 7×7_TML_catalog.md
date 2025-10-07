Each entry = a candidate reflex ready for Reflex trials: knobs → inputs → cadence → objective → win test. This is the experiment backlog.

## 1) Networking / Transport

Adaptive Batch/Flush (Chronome)
Knobs: {threshold: {1,4,8,16,32,64}, max_delay: {50µs,200µs,1ms,4ms}}
Inputs: queue_depth, enqueue/dequeue rate, p50/p95, rtt_ewma, size_mean/var
Cadence: 10 Hz
Objective: minimize tail latency + overhead
Win: p95 ↓ ≥15% vs baseline/PID; throughput ≥ baseline; flips ≤ 1/min.

Congestion Window Hint
Knobs: cwnd_step ∈ {−2,−1,0,+1}
Inputs: loss_ewma, rtt, rtt_var, reorders, queue_len
Cadence: 50 Hz
Objective: balance goodput vs latency/jitter
Win: goodput ≥ baseline, p95 RTT ↓ ≥10%, fewer loss spikes.

Backpressure Valve
Knobs: {drop_prob ∈ [0..0.1], shed_class ∈ {bg,bulk,none}}
Inputs: ingress_rate, backlog, SLA_miss_rate, e2e_p95
Cadence: 10 Hz
Objective: protect high-priority flow tails
Win: SLA misses ↓ ≥30% with ≤3% goodput loss on low-priority.

Multi-NIC Path Selector
Knobs: iface_id
Inputs: per-path rtt, jitter, loss, cpu, queue_len
Cadence: 1 Hz
Objective: minimize e2e p95 with stability
Win: path switches correlate with improved p95; hysteresis prevents flapping.

Nagle/PSH Hybrid
Knobs: coalesce_on/off
Inputs: msg_size_hist, idle_gap_hist, syscall_rate
Cadence: 10 Hz
Objective: reduce small-write tax without tail hits
Win: CPU/syscalls ↓ ≥20% with p95 Δ ≤ +5%.

ACK Pacing
Knobs: ack_delay ∈ {0..25% RTT}
Inputs: rtt, burstiness, dupacks, reorders
Cadence: 50 Hz
Objective: smooth sender rate, avoid reordering penalties
Win: retransmits ↓, jitter ↓, goodput ≥ baseline.

Priority Scheduler Weights
Knobs: class_weights (simplex)
Inputs: class_queue, SLA_violations, age_max
Cadence: 5 Hz
Objective: minimize weighted tardiness
Win: tardiness index ↓ ≥20% without starvation.

## 2) Storage / I-O

Prefetch Size
Knobs: {32,64,128,256,512} KB
Inputs: sequentiality score, hit_ratio, req_size_var
Cadence: 5 Hz
Objective: maximize hit-rate & p95 read latency
Win: p95 read ↓ ≥15%, cache misses ↓.

Writeback Cadence
Knobs: {10,20,40,80} ms
Inputs: dirty_ratio, p95_write, io_depth, device_idle
Cadence: 5 Hz
Objective: cap write tails without throughput loss
Win: p95 write ↓ ≥15%, throughput ≥ baseline.

Eviction Policy Switch
Knobs: {LRU,2Q,ARC}
Inputs: reuse_distance, scan_detect, working_set
Cadence: 1 Hz
Objective: maximize cache efficiency under pattern shifts
Win: hit-rate ↑ and p95 read ↓ on mixed workloads.

I/O Merge Aggressiveness
Knobs: {low,med,high}
Inputs: adjacent_ops ratio, device_idle, queue_depth
Cadence: 10 Hz
Objective: amortize seeks without new tails
Win: ops merged ↑, p95 stable or ↓.

GC Throttle (SSD-like)
Knobs: gc_pct ∈ {0,5,10,15}
Inputs: free_blocks, wear_level, p95_read
Cadence: 1 Hz
Objective: maintain read tails during GC
Win: p95 read ↑ ≤5% when GC active; wear leveling unchanged.

Queue Split per LUN
Knobs: weights per LUN
Inputs: latency_skew, hot_lun_id, queue_len
Cadence: 1 Hz
Objective: fairness + tail control
Win: max-min latency gap ↓ ≥20%.

Compression-on-Write Level
Knobs: {off,light,med,high}
Inputs: entropy_est, cpu_idle, p95_write
Cadence: 1 Hz
Objective: bytes saved vs p95 write
Win: size ↓ with p95 within +5% (or ↓).

## 3) Compute / Scheduling

Thread-Pool Size
Knobs: N ∈ {1..64}
Inputs: runq_len, p95_task, cpu_util, ctx_switch/s
Cadence: 2 Hz
Objective: maximize throughput, bound p95 task latency
Win: p95 ↓ ≥10% at same throughput, or throughput ↑ with tails stable.

Task Batching Window
Knobs: {50,200,1000} µs
Inputs: arrival_burst, cache_miss, syscalls/s
Cadence: 10 Hz
Objective: amortize overhead without micro-stutter
Win: syscalls ↓, p95 task Δ ≤ +5%.

NUMA Placement Hint
Knobs: {local,interleave}
Inputs: remote_misses, socket_load, memory_bw
Cadence: 1 Hz
Objective: lower cross-socket latency
Win: remote misses ↓ ≥20%, p95 task ↓.

Affinity Stickiness
Knobs: {low,med,high}
Inputs: migrations/s, cache_heat, runq_len
Cadence: 1 Hz
Objective: improve cache reuse vs fairness
Win: migrations ↓, L3 MPKI ↓, tails stable.

Priority Decay Rate
Knobs: k ∈ {fast,med,slow}
Inputs: wait_time_hist, SLA_miss_rate
Cadence: 1 Hz
Objective: reduce starvation
Win: 99p wait ↓, SLA misses ↓ without throughput loss.

Work-Steal Throttle
Knobs: steal_prob ∈ {0..1}
Inputs: imbalance, cross_socket_cost, cache_heat
Cadence: 5 Hz
Objective: balance with minimal thrash
Win: tail wait ↓, steals that help ↑.

Kernel/User Boundary Toggle
Knobs: {io_uring, syscalls}
Inputs: sysenter_rate, ctx_switch, small_io rate
Cadence: 1 Hz
Objective: choose cheaper path
Win: CPU ↓, p95 I/O stable.

## 4) Graphics / WebGPU (WRWW)

Draw-Call Coalescing
Knobs: batch_size ∈ {1,2,4,8,16}
Inputs: queue_depth, frame_time_var, CPU headroom
Cadence: per-frame
Objective: stabilize FPS tail
Win: frame-time p95 ↓ ≥15% with visual parity.

Swapchain Frame Pacing
Knobs: present_delay ∈ {0,1,2} frames
Inputs: GPU_util, vsync_jitter, CPU/GPU desync
Cadence: per-frame
Objective: reduce micro-stutter
Win: 99p frame-time ↓, judder events ↓.

Buffer-Pool Depth
Knobs: N ∈ {4,8,16,32}
Inputs: alloc_fail, reuse_latency, VRAM_pressure
Cadence: 2 Hz
Objective: cut alloc churn / stalls
Win: alloc stalls ↓, frame tails ↓.

LOD Bias per Tile
Knobs: ΔLOD ∈ {0,±0.5,±1.0}
Inputs: motion_vec, occupancy, FPS_p95
Cadence: per-frame
Objective: save GPU under motion
Win: FPS p95 ↑, artifacts minimal.

Shader Variant Select
Knobs: {fast_path, quality}
Inputs: GPU_temp, FPS_p95, thermal headroom
Cadence: per-frame
Objective: meet FPS under thermal cap
Win: throttling events ↓, FPS floor held.

Texture Streaming Rate
Knobs: MB/s ∈ {0.5,1,2,4}
Inputs: VRAM_pressure, miss_rate, frame_time_var
Cadence: 2 Hz
Objective: avoid VRAM spikes
Win: paging stalls ↓, tails ↓.

Async Compute Split
Knobs: ratio ∈ {0.2,0.4,0.6,0.8}
Inputs: graphics_queue_len, compute_queue_len
Cadence: per-frame
Objective: balance queues
Win: long frames ↓, overall frame variance ↓.

## 5) Compression / Codec

Level On-the-Fly
Knobs: {off,1,3,6}
Inputs: entropy_est, cpu_idle, link_p95
Cadence: 1 Hz
Objective: bytes vs tail
Win: size ↓ with p95 stable/↓.

Chunk Size
Knobs: {16,32,64,128} KB
Inputs: size_var, dedup_hit_rate, mem_bw
Cadence: 1 Hz
Objective: better dedup/compress trade
Win: effective bytes/vector ↓, CPU ≈ baseline.

Dictionary Refresh Period
Knobs: {N blocks}
Inputs: drift_score (topic shift), miss_rate
Cadence: 0.2 Hz
Objective: track content drift
Win: ratio ↑, p95 compress time stable.

Codec Switch
Knobs: {LZ4, Zstd}
Inputs: entropy_est, latency_budget
Cadence: 1 Hz
Objective: meet latency budget
Win: budget met with best ratio.

Delta vs Full
Knobs: {delta, full}
Inputs: temporal_corr, err_budget
Cadence: 1 Hz
Objective: minimize bandwidth within error
Win: bytes ↓ with error ≤ budget.

Quantization Level (Media)
Knobs: q ∈ {low,med,high}
Inputs: SNR_proxy, motion score
Cadence: per-GOP
Objective: hold visual QoS
Win: VMAF ≥ target; bitrate ↓.

Checksum Frequency
Knobs: {every N blocks}
Inputs: error_rate, retransmits
Cadence: 1 Hz
Objective: integrity cost vs throughput
Win: corrupted blocks ↓ with ≤3% throughput hit.

## 6) Sensing / Robotics

Sampling Rate Adaptation
Knobs: Hz ∈ {low,med,high}
Inputs: variance, event_rate, CPU_idle
Cadence: 2 Hz
Objective: save power w/o misses
Win: energy ↓ with recall ≥ baseline.

Fusion Horizon
Knobs: window ∈ {short,med,long}
Inputs: SNR, drift, motion
Cadence: 1 Hz
Objective: latency vs stability
Win: latency ↓ with accuracy ≈ baseline.

Outlier Gate σ
Knobs: σ ∈ {2,3,4}
Inputs: residuals, burst_outliers
Cadence: 10 Hz
Objective: robustness w/o drop storms
Win: false rejects ↓, RMSE stable.

Active Sensing Density
Knobs: grid_step ∈ {coarse,med,fine}
Inputs: info_gain_est, time_budget
Cadence: 1 Hz
Objective: maximize info under budget
Win: coverage ↑ at same time cap.

PID Autotune Hint
Knobs: ΔKp,ΔKi,ΔKd (bounded)
Inputs: step_response_features, overshoot
Cadence: on events
Objective: faster settle, bounded overshoot
Win: Ts ↓, Mp within spec.

Trajectory Replan Cadence
Knobs: period ∈ {50,100,200} ms
Inputs: obstacle_rate, CPU_idle
Cadence: 1 Hz
Objective: avoid thrash, react in time
Win: success rate ↑, CPU spikes ↓.

Object-Cache TTL
Knobs: t ∈ {0.1,0.5,1,2}s
Inputs: scene_change, track_conf
Cadence: 1 Hz
Objective: freshness vs compute
Win: re-id errors ↓ with compute ≤ baseline.

## 7) Energy / Thermal / Power

DVFS Governor Hint
Knobs: {perf,powersave,turbo}
Inputs: thermal_headroom, QoS_miss, util
Cadence: 1 Hz
Objective: meet QoS under cap
Win: QoS hits ↓, temp spikes ↓.

Fan Curve Offset
Knobs: ΔPWM ∈ {−10..+10%}
Inputs: temp_slope, hotspot idx
Cadence: 1 Hz
Objective: pre-empt throttle
Win: throttle events ↓ with noise ≤ baseline+small.

Core Parking
Knobs: N_active
Inputs: util_ewma, p95_task
Cadence: 1 Hz
Objective: efficiency without tail hits
Win: watts ↓ with p95 Δ ≤ +5%.

GPU Power Limit
Knobs: W ∈ {−20%, −10%, 0, +10%}
Inputs: FPS_p95, temp, power_budget
Cadence: 1 Hz
Objective: hold FPS floor in budget
Win: FPS p95 stable; W within cap.

Sleep/Idle Timing
Knobs: timeout ∈ {short,med,long}
Inputs: wake_rate, miss_rate
Cadence: 0.2 Hz
Objective: battery life vs wake latency
Win: energy ↓ with miss ≤ baseline.

Charger Current Cap
Knobs: A ∈ {0.5,1,2,...}
Inputs: pack_temp, IR_drop, SoC
Cadence: 1 Hz
Objective: safe fast-charge
Win: time-to-X% ↓ with temps in spec.

Workload Placement (ToD / Carbon)
Knobs: site_id
Inputs: electricity_price, carbon_intensity, latency
Cadence: 2–6 per hour
Objective: cost/carbon aware QoS
Win: cost ↓ or CO₂ ↓ with SLA met.

How to use this list (serious mode)

Pick 1 per domain as Phase-1 (7 total).

For each: define the discrete/continuous knob set, finalize the feature window, build the oracle labeler (grid or sweep), then run Steady / Bursty / Adversarial traces with Baseline vs PID vs Reflex.

Promotion rule (default): Reflex wins on p95 in ≥2/3 traces, never loses throughput/QoS
