//! Compute Telemetry Schema v1
//!
//! Defines the feature schema for thread-pool sizing reflexes.

use serde::{Deserialize, Serialize};
use std::collections::VecDeque;
use std::time::{Duration, Instant};

/// Telemetry sample (raw, unnormalized)
#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
pub struct ComputeTelemetry {
    pub timestamp_us: u64,
    pub runq_len: u32,                  // tasks waiting in queue
    pub arrival_rate: f32,              // tasks/s
    pub completion_rate: f32,           // tasks/s
    pub task_time_p50_us: f32,          // median task latency
    pub task_time_p95_us: f32,          // 95th percentile task latency
    pub worker_util: f32,               // [0, 1] fraction of workers busy
    pub ctx_switches_per_sec: f32,      // context switch rate estimate
    pub task_size_mean: f32,            // mean task execution time (µs)
    pub task_size_var: f32,             // variance of task execution time (µs²)
    pub idle_worker_count: u32,         // number of idle workers
}

impl ComputeTelemetry {
    pub const FEATURE_COUNT: usize = 10;

    /// Convert to feature vector (unnormalized)
    pub fn to_features(&self) -> [f32; Self::FEATURE_COUNT] {
        [
            self.runq_len as f32,
            self.arrival_rate,
            self.completion_rate,
            self.task_time_p50_us,
            self.task_time_p95_us,
            self.worker_util,
            self.ctx_switches_per_sec,
            self.task_size_mean,
            self.task_size_var,
            self.idle_worker_count as f32,
        ]
    }

    /// Feature names for logging/debugging
    pub fn feature_names() -> [&'static str; Self::FEATURE_COUNT] {
        [
            "runq_len",
            "arrival_rate",
            "completion_rate",
            "task_time_p50_us",
            "task_time_p95_us",
            "worker_util",
            "ctx_switches_per_sec",
            "task_size_mean",
            "task_size_var",
            "idle_worker_count",
        ]
    }
}

/// Normalizer (min-max per feature)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Normalizer {
    pub min: [f32; ComputeTelemetry::FEATURE_COUNT],
    pub max: [f32; ComputeTelemetry::FEATURE_COUNT],
}

impl Normalizer {
    pub fn new() -> Self {
        Self {
            min: [f32::MAX; ComputeTelemetry::FEATURE_COUNT],
            max: [f32::MIN; ComputeTelemetry::FEATURE_COUNT],
        }
    }

    /// Update bounds from a sample
    pub fn observe(&mut self, features: &[f32; ComputeTelemetry::FEATURE_COUNT]) {
        for i in 0..ComputeTelemetry::FEATURE_COUNT {
            self.min[i] = self.min[i].min(features[i]);
            self.max[i] = self.max[i].max(features[i]);
        }
    }

    /// Normalize features to [0, 1]
    pub fn normalize(&self, features: &[f32; ComputeTelemetry::FEATURE_COUNT]) -> [f32; ComputeTelemetry::FEATURE_COUNT] {
        let mut normalized = [0.0; ComputeTelemetry::FEATURE_COUNT];
        for i in 0..ComputeTelemetry::FEATURE_COUNT {
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
#[derive(Debug)]
pub struct WindowCollector {
    window_size: Duration,
    step_size: Duration,
    samples: VecDeque<(Instant, ComputeTelemetry)>,
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
    pub fn push(&mut self, sample: ComputeTelemetry) {
        let now = Instant::now();
        self.samples.push_back((now, sample));

        // Evict old samples
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
    pub fn emit(&mut self) -> Option<ComputeTelemetry> {
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

        let f1 = [10.0, 100.0, 100.0, 500.0, 1000.0, 0.5, 100.0, 200.0, 50.0, 2.0];
        let f2 = [20.0, 200.0, 200.0, 1000.0, 2000.0, 0.9, 200.0, 400.0, 100.0, 5.0];

        norm.observe(&f1);
        norm.observe(&f2);

        let n1 = norm.normalize(&f1);
        let n2 = norm.normalize(&f2);

        assert_eq!(n1[0], 0.0); // min
        assert_eq!(n2[0], 1.0); // max
    }

    #[test]
    fn test_feature_conversion() {
        let telem = ComputeTelemetry {
            timestamp_us: 0,
            runq_len: 10,
            arrival_rate: 1000.0,
            completion_rate: 950.0,
            task_time_p50_us: 500.0,
            task_time_p95_us: 1200.0,
            worker_util: 0.85,
            ctx_switches_per_sec: 150.0,
            task_size_mean: 450.0,
            task_size_var: 2500.0,
            idle_worker_count: 1,
        };

        let features = telem.to_features();
        assert_eq!(features[0], 10.0);
        assert_eq!(features[1], 1000.0);
        assert_eq!(features[4], 1200.0);
    }
}
