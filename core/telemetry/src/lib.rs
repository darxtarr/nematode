//! Reflex Telemetry Schema v1
//!
//! Defines the feature schema for Chronome batch reflexes.

use serde::{Deserialize, Serialize};
use std::collections::VecDeque;
use std::time::{Duration, Instant};

/// Telemetry sample (raw, unnormalized)
#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
pub struct TelemetrySample {
    pub timestamp_us: u64,
    pub queue_depth: u32,
    pub enqueue_rate: f32,      // packets/s
    pub dequeue_rate: f32,      // packets/s (added, not in original list)
    pub latency_p50_us: f32,
    pub latency_p95_us: f32,
    pub bytes_in_per_sec: f64,
    pub bytes_out_per_sec: f64,
    pub packet_size_mean: f32,
    pub packet_size_var: f32,
    pub rtt_ewma_us: f32,
}

impl TelemetrySample {
    pub const FEATURE_COUNT: usize = 10;

    /// Convert to feature vector (unnormalized)
    pub fn to_features(&self) -> [f32; Self::FEATURE_COUNT] {
        [
            self.queue_depth as f32,
            self.enqueue_rate,
            self.dequeue_rate,
            self.latency_p50_us,
            self.latency_p95_us,
            self.bytes_in_per_sec as f32,
            self.bytes_out_per_sec as f32,
            self.packet_size_mean,
            self.packet_size_var,
            self.rtt_ewma_us,
        ]
    }

    /// Feature names for logging/debugging
    pub fn feature_names() -> [&'static str; Self::FEATURE_COUNT] {
        [
            "queue_depth",
            "enqueue_rate",
            "dequeue_rate",
            "latency_p50_us",
            "latency_p95_us",
            "bytes_in_per_sec",
            "bytes_out_per_sec",
            "packet_size_mean",
            "packet_size_var",
            "rtt_ewma_us",
        ]
    }
}

/// Normalizer (min-max per feature)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Normalizer {
    pub min: [f32; TelemetrySample::FEATURE_COUNT],
    pub max: [f32; TelemetrySample::FEATURE_COUNT],
}

impl Normalizer {
    pub fn new() -> Self {
        Self {
            min: [f32::MAX; TelemetrySample::FEATURE_COUNT],
            max: [f32::MIN; TelemetrySample::FEATURE_COUNT],
        }
    }

    /// Update bounds from a sample
    pub fn observe(&mut self, features: &[f32; TelemetrySample::FEATURE_COUNT]) {
        for i in 0..TelemetrySample::FEATURE_COUNT {
            self.min[i] = self.min[i].min(features[i]);
            self.max[i] = self.max[i].max(features[i]);
        }
    }

    /// Normalize features to [0, 1]
    pub fn normalize(&self, features: &[f32; TelemetrySample::FEATURE_COUNT]) -> [f32; TelemetrySample::FEATURE_COUNT] {
        let mut normalized = [0.0; TelemetrySample::FEATURE_COUNT];
        for i in 0..TelemetrySample::FEATURE_COUNT {
            let range = self.max[i] - self.min[i];
            normalized[i] = if range > 0.0 {
                (features[i] - self.min[i]) / range
            } else {
                0.5 // constant feature
            };
        }
        normalized
    }
}

impl Default for Normalizer {
    fn default() -> Self {
        Self::new()
    }
}

/// Windowed telemetry collector
///
/// Collects samples into sliding windows for feature extraction
#[derive(Debug)]
pub struct WindowCollector {
    window_size: Duration,
    step_size: Duration,
    samples: VecDeque<(Instant, TelemetrySample)>,
    last_window_at: Option<Instant>,
}

impl WindowCollector {
    pub fn new(window_size: Duration, step_size: Duration) -> Self {
        Self {
            window_size,
            step_size,
            samples: VecDeque::new(),
            last_window_at: None,
        }
    }

    /// Add a sample
    pub fn push(&mut self, sample: TelemetrySample) {
        let now = Instant::now();
        self.samples.push_back((now, sample));

        // Evict old samples (older than window_size)
        let cutoff = now - self.window_size;
        while let Some((t, _)) = self.samples.front() {
            if *t < cutoff {
                self.samples.pop_front();
            } else {
                break;
            }
        }
    }

    /// Check if a new window should be emitted
    pub fn should_emit(&self) -> bool {
        let now = Instant::now();
        match self.last_window_at {
            None => !self.samples.is_empty(),
            Some(last) => now.duration_since(last) >= self.step_size,
        }
    }

    /// Emit current window (aggregated sample)
    ///
    /// For now, just returns the most recent sample.
    /// TODO: proper aggregation (mean, percentiles, etc.)
    pub fn emit(&mut self) -> Option<TelemetrySample> {
        if !self.should_emit() {
            return None;
        }

        let now = Instant::now();
        self.last_window_at = Some(now);

        // Return most recent sample in window
        self.samples.back().map(|(_, sample)| *sample)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_normalizer() {
        let mut norm = Normalizer::new();

        let f1 = [10.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0];
        let f2 = [20.0, 100.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0];

        norm.observe(&f1);
        norm.observe(&f2);

        let n1 = norm.normalize(&f1);
        let n2 = norm.normalize(&f2);

        assert_eq!(n1[0], 0.0); // min
        assert_eq!(n2[0], 1.0); // max
        assert_eq!(n1[1], 0.0); // min
        assert_eq!(n2[1], 1.0); // max
    }

    #[test]
    fn test_window_collector() {
        let mut wc = WindowCollector::new(
            Duration::from_millis(200),
            Duration::from_millis(100),
        );

        let sample = TelemetrySample {
            timestamp_us: 0,
            queue_depth: 10,
            enqueue_rate: 1000.0,
            dequeue_rate: 1000.0,
            latency_p50_us: 100.0,
            latency_p95_us: 200.0,
            bytes_in_per_sec: 1e6,
            bytes_out_per_sec: 1e6,
            packet_size_mean: 1024.0,
            packet_size_var: 100.0,
            rtt_ewma_us: 50.0,
        };

        wc.push(sample);
        assert!(wc.should_emit());

        let emitted = wc.emit().unwrap();
        assert_eq!(emitted.queue_depth, 10);
    }
}
