//! Fake Transport Simulator
//!
//! Simulates a packet queue with configurable flush policies.

use std::collections::VecDeque;
use std::time::{Duration, Instant};
use telemetry::TelemetrySample;
use rand::Rng;

/// Simulated packet
#[derive(Debug, Clone)]
pub struct Packet {
    pub id: u64,
    pub size_bytes: usize,
    pub arrival_time: Instant,
}

/// Flush policy decision
#[derive(Debug, Clone, Copy)]
pub struct FlushDecision {
    pub threshold: u32,        // packets
    pub max_delay_us: u32,     // microseconds
}

/// Flush policy trait
pub trait FlushPolicy {
    fn decide(&mut self, telem: &TelemetrySample) -> FlushDecision;
}

/// Baseline static policy
pub struct BaselinePolicy {
    threshold: u32,
    max_delay_us: u32,
}

impl BaselinePolicy {
    pub fn new() -> Self {
        Self {
            threshold: 16,
            max_delay_us: 500,
        }
    }
}

impl Default for BaselinePolicy {
    fn default() -> Self {
        Self::new()
    }
}

impl FlushPolicy for BaselinePolicy {
    fn decide(&mut self, _telem: &TelemetrySample) -> FlushDecision {
        FlushDecision {
            threshold: self.threshold,
            max_delay_us: self.max_delay_us,
        }
    }
}

/// Reflex policy (loaded from .reflex file)
pub struct ReflexPolicy {
    reflex: reflex_format::Reflex,
    normalizer: telemetry::Normalizer,
    hysteresis_threshold: f32,
    last_decision: Option<FlushDecision>,
    last_decision_time: Option<Instant>,
    hold_time: Duration,
}

impl ReflexPolicy {
    pub fn load(reflex_path: &str, normalizer: telemetry::Normalizer) -> std::io::Result<Self> {
        let bytes = std::fs::read(reflex_path)?;
        let reflex = reflex_format::Reflex::from_bytes(&bytes)?;

        Ok(Self {
            reflex,
            normalizer,
            hysteresis_threshold: 0.05,
            last_decision: None,
            last_decision_time: None,
            hold_time: Duration::from_millis(300),
        })
    }
}

impl FlushPolicy for ReflexPolicy {
    fn decide(&mut self, telem: &TelemetrySample) -> FlushDecision {
        let now = Instant::now();

        // Hold time enforcement
        if let Some(last_time) = self.last_decision_time {
            if now.duration_since(last_time) < self.hold_time {
                return self.last_decision.unwrap();
            }
        }

        // Normalize features
        let features = telem.to_features();
        let norm_features = self.normalizer.normalize(&features);

        // Infer
        let outputs = self.reflex.infer(&norm_features);

        // Decode outputs (assume first output is threshold, second is delay)
        let threshold = outputs[0].round() as u32;
        let max_delay_us = outputs[1].round() as u32;

        let decision = FlushDecision {
            threshold,
            max_delay_us,
        };

        self.last_decision = Some(decision);
        self.last_decision_time = Some(now);

        decision
    }
}

/// Metrics collector
#[derive(Debug, Clone)]
pub struct Metrics {
    pub latencies_us: Vec<u64>,
    pub throughput_samples: Vec<f64>, // packets/s
    pub decision_changes: usize,
}

impl Metrics {
    pub fn new() -> Self {
        Self {
            latencies_us: Vec::new(),
            throughput_samples: Vec::new(),
            decision_changes: 0,
        }
    }

    pub fn record_latency(&mut self, latency_us: u64) {
        self.latencies_us.push(latency_us);
    }

    pub fn record_throughput(&mut self, pkts_per_sec: f64) {
        self.throughput_samples.push(pkts_per_sec);
    }

    pub fn record_decision_change(&mut self) {
        self.decision_changes += 1;
    }

    pub fn p50_latency(&self) -> f64 {
        self.percentile(0.50)
    }

    pub fn p95_latency(&self) -> f64 {
        self.percentile(0.95)
    }

    pub fn p99_latency(&self) -> f64 {
        self.percentile(0.99)
    }

    fn percentile(&self, p: f64) -> f64 {
        if self.latencies_us.is_empty() {
            return 0.0;
        }
        let mut sorted = self.latencies_us.clone();
        sorted.sort_unstable();
        let idx = ((sorted.len() as f64) * p).floor() as usize;
        sorted[idx.min(sorted.len() - 1)] as f64
    }

    pub fn mean_throughput(&self) -> f64 {
        if self.throughput_samples.is_empty() {
            return 0.0;
        }
        self.throughput_samples.iter().sum::<f64>() / self.throughput_samples.len() as f64
    }
}

impl Default for Metrics {
    fn default() -> Self {
        Self::new()
    }
}

/// Fake transport simulator
pub struct FakeTransport<P: FlushPolicy> {
    queue: VecDeque<Packet>,
    policy: P,
    metrics: Metrics,
    next_packet_id: u64,
    last_decision: Option<FlushDecision>,
    sent_packets: usize,
    last_throughput_measurement: Instant,
}

impl<P: FlushPolicy> FakeTransport<P> {
    pub fn new(policy: P) -> Self {
        Self {
            queue: VecDeque::new(),
            policy,
            metrics: Metrics::new(),
            next_packet_id: 0,
            last_decision: None,
            sent_packets: 0,
            last_throughput_measurement: Instant::now(),
        }
    }

    /// Enqueue a packet
    pub fn enqueue(&mut self, size_bytes: usize) {
        let packet = Packet {
            id: self.next_packet_id,
            size_bytes,
            arrival_time: Instant::now(),
        };
        self.next_packet_id += 1;
        self.queue.push_back(packet);
    }

    /// Tick the simulator
    pub fn tick(&mut self) {
        let telem = self.collect_telemetry();
        let decision = self.policy.decide(&telem);

        // Track decision changes
        if let Some(last) = self.last_decision {
            if last.threshold != decision.threshold || last.max_delay_us != decision.max_delay_us {
                self.metrics.record_decision_change();
            }
        }
        self.last_decision = Some(decision);

        // Flush if conditions met
        let should_flush = self.queue.len() >= decision.threshold as usize
            || self.oldest_packet_age_us() >= decision.max_delay_us as u64;

        if should_flush {
            self.flush();
        }

        // Measure throughput every second
        let now = Instant::now();
        if now.duration_since(self.last_throughput_measurement) >= Duration::from_secs(1) {
            let elapsed = now.duration_since(self.last_throughput_measurement).as_secs_f64();
            let throughput = self.sent_packets as f64 / elapsed;
            self.metrics.record_throughput(throughput);
            self.sent_packets = 0;
            self.last_throughput_measurement = now;
        }
    }

    fn flush(&mut self) {
        let now = Instant::now();
        while let Some(packet) = self.queue.pop_front() {
            let latency_us = now.duration_since(packet.arrival_time).as_micros() as u64;
            self.metrics.record_latency(latency_us);
            self.sent_packets += 1;
        }
    }

    fn oldest_packet_age_us(&self) -> u64 {
        self.queue.front().map_or(0, |p| {
            Instant::now().duration_since(p.arrival_time).as_micros() as u64
        })
    }

    fn collect_telemetry(&self) -> TelemetrySample {
        let now = Instant::now();

        // Compute simple statistics
        let queue_depth = self.queue.len() as u32;

        let latencies: Vec<u64> = self.queue.iter()
            .map(|p| now.duration_since(p.arrival_time).as_micros() as u64)
            .collect();

        let (latency_p50, latency_p95) = if latencies.is_empty() {
            (0.0, 0.0)
        } else {
            let mut sorted = latencies.clone();
            sorted.sort_unstable();
            let p50 = sorted[sorted.len() / 2] as f32;
            let p95_idx = ((sorted.len() as f32 * 0.95) as usize).min(sorted.len() - 1);
            let p95 = sorted[p95_idx] as f32;
            (p50, p95)
        };

        let packet_sizes: Vec<f32> = self.queue.iter().map(|p| p.size_bytes as f32).collect();
        let packet_size_mean = if packet_sizes.is_empty() {
            0.0
        } else {
            packet_sizes.iter().sum::<f32>() / packet_sizes.len() as f32
        };

        let packet_size_var = if packet_sizes.is_empty() {
            0.0
        } else {
            let mean = packet_size_mean;
            packet_sizes.iter().map(|s| (s - mean).powi(2)).sum::<f32>() / packet_sizes.len() as f32
        };

        TelemetrySample {
            timestamp_us: now.elapsed().as_micros() as u64,
            queue_depth,
            enqueue_rate: 0.0, // TODO: track
            dequeue_rate: 0.0, // TODO: track
            latency_p50_us: latency_p50,
            latency_p95_us: latency_p95,
            bytes_in_per_sec: 0.0, // TODO: track
            bytes_out_per_sec: 0.0, // TODO: track
            packet_size_mean,
            packet_size_var,
            rtt_ewma_us: 50.0, // TODO: track
        }
    }

    pub fn metrics(&self) -> &Metrics {
        &self.metrics
    }
}

/// Workload generator
pub trait WorkloadGenerator {
    fn next_packet(&mut self) -> Option<(Duration, usize)>; // (wait_time, size_bytes)
}

/// Steady Poisson workload
pub struct SteadyWorkload {
    rate_per_sec: f64,
    packet_size: usize,
    duration: Duration,
    elapsed: Duration,
    rng: rand::rngs::ThreadRng,
}

impl SteadyWorkload {
    pub fn new(rate_per_sec: f64, packet_size: usize, duration: Duration) -> Self {
        Self {
            rate_per_sec,
            packet_size,
            duration,
            elapsed: Duration::ZERO,
            rng: rand::thread_rng(),
        }
    }
}

impl WorkloadGenerator for SteadyWorkload {
    fn next_packet(&mut self) -> Option<(Duration, usize)> {
        if self.elapsed >= self.duration {
            return None;
        }

        // Exponential inter-arrival time
        let lambda = self.rate_per_sec;
        let u: f64 = self.rng.gen();
        let wait_s = -u.ln() / lambda;
        let wait = Duration::from_secs_f64(wait_s);

        self.elapsed += wait;
        Some((wait, self.packet_size))
    }
}

/// Bursty workload (alternating high/low)
pub struct BurstyWorkload {
    high_rate: f64,
    low_rate: f64,
    packet_size: usize,
    period: Duration,
    duration: Duration,
    elapsed: Duration,
    rng: rand::rngs::ThreadRng,
}

impl BurstyWorkload {
    pub fn new(
        high_rate: f64,
        low_rate: f64,
        packet_size: usize,
        period: Duration,
        duration: Duration,
    ) -> Self {
        Self {
            high_rate,
            low_rate,
            packet_size,
            period,
            duration,
            elapsed: Duration::ZERO,
            rng: rand::thread_rng(),
        }
    }

    fn current_rate(&self) -> f64 {
        let phase = self.elapsed.as_secs_f64() % (self.period.as_secs_f64() * 2.0);
        if phase < self.period.as_secs_f64() {
            self.high_rate
        } else {
            self.low_rate
        }
    }
}

impl WorkloadGenerator for BurstyWorkload {
    fn next_packet(&mut self) -> Option<(Duration, usize)> {
        if self.elapsed >= self.duration {
            return None;
        }

        let lambda = self.current_rate();
        let u: f64 = self.rng.gen();
        let wait_s = -u.ln() / lambda;
        let wait = Duration::from_secs_f64(wait_s);

        self.elapsed += wait;
        Some((wait, self.packet_size))
    }
}

/// Adversarial workload (random shifts)
pub struct AdversarialWorkload {
    base_rate: f64,
    packet_size_range: (usize, usize),
    duration: Duration,
    elapsed: Duration,
    rng: rand::rngs::ThreadRng,
}

impl AdversarialWorkload {
    pub fn new(
        base_rate: f64,
        packet_size_range: (usize, usize),
        duration: Duration,
    ) -> Self {
        Self {
            base_rate,
            packet_size_range,
            duration,
            elapsed: Duration::ZERO,
            rng: rand::thread_rng(),
        }
    }
}

impl WorkloadGenerator for AdversarialWorkload {
    fn next_packet(&mut self) -> Option<(Duration, usize)> {
        if self.elapsed >= self.duration {
            return None;
        }

        // Random rate variation
        let rate_multiplier: f64 = self.rng.gen_range(0.1..5.0);
        let lambda = self.base_rate * rate_multiplier;

        let u: f64 = self.rng.gen();
        let wait_s = -u.ln() / lambda;
        let wait = Duration::from_secs_f64(wait_s);

        // Random packet size
        let size = self.rng.gen_range(self.packet_size_range.0..=self.packet_size_range.1);

        self.elapsed += wait;
        Some((wait, size))
    }
}
