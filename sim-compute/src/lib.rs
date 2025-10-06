//! Thread Pool Simulator
//!
//! Simulates a task queue with configurable thread pool sizing policies.

use std::collections::VecDeque;
use std::time::{Duration, Instant};
use telemetry_compute::ComputeTelemetry;
use rand::Rng;

/// Simulated task
#[derive(Debug, Clone)]
pub struct Task {
    pub id: u64,
    pub work_us: u64,              // microseconds of work
    pub arrival_time: Instant,
    pub start_time: Option<Instant>,
}

/// Thread pool sizing decision
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct PoolSizeDecision {
    pub n_workers: u32,
}

/// Thread pool sizing policy trait
pub trait PoolSizePolicy {
    fn decide(&mut self, telem: &ComputeTelemetry) -> PoolSizeDecision;
}

/// Baseline static policy
pub struct BaselinePolicy {
    n_workers: u32,
}

impl BaselinePolicy {
    pub fn new() -> Self {
        Self { n_workers: 8 }
    }
}

impl Default for BaselinePolicy {
    fn default() -> Self {
        Self::new()
    }
}

impl PoolSizePolicy for BaselinePolicy {
    fn decide(&mut self, _telem: &ComputeTelemetry) -> PoolSizeDecision {
        PoolSizeDecision {
            n_workers: self.n_workers,
        }
    }
}

/// Reflex policy (loaded from .reflex file)
pub struct ReflexPolicy {
    reflex: reflex_format::Reflex,
    normalizer: telemetry_compute::Normalizer,
    last_decision: Option<PoolSizeDecision>,
    last_decision_time: Option<Instant>,
    hold_time: Duration,
}

impl ReflexPolicy {
    pub fn load(reflex_path: &str, normalizer: telemetry_compute::Normalizer) -> std::io::Result<Self> {
        let bytes = std::fs::read(reflex_path)?;
        let reflex = reflex_format::Reflex::from_bytes(&bytes)?;

        Ok(Self {
            reflex,
            normalizer,
            last_decision: None,
            last_decision_time: None,
            hold_time: Duration::from_millis(500),
        })
    }
}

impl PoolSizePolicy for ReflexPolicy {
    fn decide(&mut self, telem: &ComputeTelemetry) -> PoolSizeDecision {
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

        // Decode output (single output: n_workers)
        let n_workers = outputs[0].round().max(1.0).min(64.0) as u32;

        let decision = PoolSizeDecision { n_workers };

        self.last_decision = Some(decision);
        self.last_decision_time = Some(now);

        decision
    }
}

/// Metrics collector
#[derive(Debug, Clone)]
pub struct Metrics {
    pub task_times_us: Vec<u64>,
    pub throughput_samples: Vec<f64>, // tasks/s
    pub decision_changes: usize,
}

impl Metrics {
    pub fn new() -> Self {
        Self {
            task_times_us: Vec::new(),
            throughput_samples: Vec::new(),
            decision_changes: 0,
        }
    }

    pub fn record_task_time(&mut self, time_us: u64) {
        self.task_times_us.push(time_us);
    }

    pub fn record_throughput(&mut self, tasks_per_sec: f64) {
        self.throughput_samples.push(tasks_per_sec);
    }

    pub fn record_decision_change(&mut self) {
        self.decision_changes += 1;
    }

    pub fn p50_task_time(&self) -> f64 {
        self.percentile(0.50)
    }

    pub fn p95_task_time(&self) -> f64 {
        self.percentile(0.95)
    }

    pub fn p99_task_time(&self) -> f64 {
        self.percentile(0.99)
    }

    fn percentile(&self, p: f64) -> f64 {
        if self.task_times_us.is_empty() {
            return 0.0;
        }
        let mut sorted = self.task_times_us.clone();
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

/// Worker state
#[derive(Debug)]
struct Worker {
    id: usize,
    current_task: Option<Task>,
    task_finish_time: Option<Instant>,
}

impl Worker {
    fn new(id: usize) -> Self {
        Self {
            id,
            current_task: None,
            task_finish_time: None,
        }
    }

    fn is_idle(&self) -> bool {
        self.current_task.is_none()
    }

    fn assign(&mut self, mut task: Task, now: Instant) {
        task.start_time = Some(now);
        let finish_time = now + Duration::from_micros(task.work_us);
        self.current_task = Some(task);
        self.task_finish_time = Some(finish_time);
    }

    fn check_complete(&mut self, now: Instant) -> Option<Task> {
        if let Some(finish_time) = self.task_finish_time {
            if now >= finish_time {
                let task = self.current_task.take();
                self.task_finish_time = None;
                return task;
            }
        }
        None
    }
}

/// Thread pool simulator
pub struct ThreadPoolSim<P: PoolSizePolicy> {
    queue: VecDeque<Task>,
    workers: Vec<Worker>,
    policy: P,
    metrics: Metrics,
    next_task_id: u64,
    last_decision: Option<PoolSizeDecision>,
    completed_tasks: usize,
    last_throughput_measurement: Instant,
    arrival_count_window: VecDeque<(Instant, usize)>,
    completion_count_window: VecDeque<(Instant, usize)>,
    task_times_window: Vec<u64>,
}

impl<P: PoolSizePolicy> ThreadPoolSim<P> {
    pub fn new(policy: P, initial_workers: u32) -> Self {
        let workers = (0..initial_workers)
            .map(|i| Worker::new(i as usize))
            .collect();

        Self {
            queue: VecDeque::new(),
            workers,
            policy,
            metrics: Metrics::new(),
            next_task_id: 0,
            last_decision: None,
            completed_tasks: 0,
            last_throughput_measurement: Instant::now(),
            arrival_count_window: VecDeque::new(),
            completion_count_window: VecDeque::new(),
            task_times_window: Vec::new(),
        }
    }

    /// Enqueue a task
    pub fn enqueue(&mut self, work_us: u64) {
        let task = Task {
            id: self.next_task_id,
            work_us,
            arrival_time: Instant::now(),
            start_time: None,
        };
        self.next_task_id += 1;
        self.queue.push_back(task);

        // Track arrivals
        let now = Instant::now();
        self.arrival_count_window.push_back((now, 1));
    }

    /// Tick the simulator
    pub fn tick(&mut self) {
        let now = Instant::now();

        // Check for completed tasks
        for worker in &mut self.workers {
            if let Some(task) = worker.check_complete(now) {
                let total_time = now.duration_since(task.arrival_time).as_micros() as u64;
                self.metrics.record_task_time(total_time);
                self.task_times_window.push(total_time);
                self.completed_tasks += 1;
                self.completion_count_window.push_back((now, 1));
            }
        }

        // Assign tasks to idle workers
        for worker in &mut self.workers {
            if worker.is_idle() {
                if let Some(task) = self.queue.pop_front() {
                    worker.assign(task, now);
                }
            }
        }

        // Collect telemetry
        let telem = self.collect_telemetry();

        // Get policy decision
        let decision = self.policy.decide(&telem);

        // Track decision changes
        if let Some(last) = self.last_decision {
            if last.n_workers != decision.n_workers {
                self.metrics.record_decision_change();
            }
        }
        self.last_decision = Some(decision);

        // Resize worker pool
        self.resize_workers(decision.n_workers);

        // Measure throughput every second
        if now.duration_since(self.last_throughput_measurement) >= Duration::from_secs(1) {
            let elapsed = now.duration_since(self.last_throughput_measurement).as_secs_f64();
            let throughput = self.completed_tasks as f64 / elapsed;
            self.metrics.record_throughput(throughput);
            self.completed_tasks = 0;
            self.last_throughput_measurement = now;
        }

        // Cleanup old window data
        let cutoff = now - Duration::from_secs(1);
        self.arrival_count_window.retain(|(t, _)| *t >= cutoff);
        self.completion_count_window.retain(|(t, _)| *t >= cutoff);
    }

    fn resize_workers(&mut self, target: u32) {
        let current = self.workers.len();
        let target = target as usize;

        if target > current {
            // Add workers
            for i in current..target {
                self.workers.push(Worker::new(i));
            }
        } else if target < current {
            // Remove idle workers until we reach target
            let mut to_remove = current - target;
            self.workers.retain(|w| {
                if to_remove > 0 && w.is_idle() {
                    to_remove -= 1;
                    false
                } else {
                    true
                }
            });
        }
    }

    fn collect_telemetry(&self) -> ComputeTelemetry {
        let now = Instant::now();

        let runq_len = self.queue.len() as u32;

        // Arrival rate
        let arrival_rate = self.arrival_count_window.iter().map(|(_, c)| *c).sum::<usize>() as f32;

        // Completion rate
        let completion_rate = self.completion_count_window.iter().map(|(_, c)| *c).sum::<usize>() as f32;

        // Task time percentiles
        let (task_time_p50, task_time_p95) = if self.task_times_window.is_empty() {
            (0.0, 0.0)
        } else {
            let mut sorted = self.task_times_window.clone();
            sorted.sort_unstable();
            let p50 = sorted[sorted.len() / 2] as f32;
            let p95_idx = ((sorted.len() as f32 * 0.95) as usize).min(sorted.len() - 1);
            let p95 = sorted[p95_idx] as f32;
            (p50, p95)
        };

        // Worker utilization
        let busy_workers = self.workers.iter().filter(|w| !w.is_idle()).count();
        let worker_util = if self.workers.is_empty() {
            0.0
        } else {
            busy_workers as f32 / self.workers.len() as f32
        };

        // Idle worker count
        let idle_worker_count = (self.workers.len() - busy_workers) as u32;

        // Task size stats (from queue)
        let task_sizes: Vec<f32> = self.queue.iter().map(|t| t.work_us as f32).collect();
        let task_size_mean = if task_sizes.is_empty() {
            0.0
        } else {
            task_sizes.iter().sum::<f32>() / task_sizes.len() as f32
        };

        let task_size_var = if task_sizes.is_empty() {
            0.0
        } else {
            let mean = task_size_mean;
            task_sizes.iter().map(|s| (s - mean).powi(2)).sum::<f32>() / task_sizes.len() as f32
        };

        // Context switches (estimate: worker count changes + task switches)
        let ctx_switches_per_sec = (self.workers.len() * 10) as f32; // Placeholder

        ComputeTelemetry {
            timestamp_us: now.elapsed().as_micros() as u64,
            runq_len,
            arrival_rate,
            completion_rate,
            task_time_p50_us: task_time_p50,
            task_time_p95_us: task_time_p95,
            worker_util,
            ctx_switches_per_sec,
            task_size_mean,
            task_size_var,
            idle_worker_count,
        }
    }

    pub fn metrics(&self) -> &Metrics {
        &self.metrics
    }
}

/// Workload generator
pub trait WorkloadGenerator {
    fn next_task(&mut self) -> Option<(Duration, u64)>; // (wait_time, work_us)
}

/// Steady Poisson workload
pub struct SteadyWorkload {
    rate_per_sec: f64,
    task_work_us: u64,
    duration: Duration,
    elapsed: Duration,
    rng: rand::rngs::ThreadRng,
}

impl SteadyWorkload {
    pub fn new(rate_per_sec: f64, task_work_us: u64, duration: Duration) -> Self {
        Self {
            rate_per_sec,
            task_work_us,
            duration,
            elapsed: Duration::ZERO,
            rng: rand::thread_rng(),
        }
    }
}

impl WorkloadGenerator for SteadyWorkload {
    fn next_task(&mut self) -> Option<(Duration, u64)> {
        if self.elapsed >= self.duration {
            return None;
        }

        // Exponential inter-arrival time
        let lambda = self.rate_per_sec;
        let u: f64 = self.rng.gen();
        let wait_s = -u.ln() / lambda;
        let wait = Duration::from_secs_f64(wait_s);

        self.elapsed += wait;
        Some((wait, self.task_work_us))
    }
}

/// Bursty workload (alternating high/low)
pub struct BurstyWorkload {
    high_rate: f64,
    low_rate: f64,
    task_work_us: u64,
    period: Duration,
    duration: Duration,
    elapsed: Duration,
    rng: rand::rngs::ThreadRng,
}

impl BurstyWorkload {
    pub fn new(
        high_rate: f64,
        low_rate: f64,
        task_work_us: u64,
        period: Duration,
        duration: Duration,
    ) -> Self {
        Self {
            high_rate,
            low_rate,
            task_work_us,
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
    fn next_task(&mut self) -> Option<(Duration, u64)> {
        if self.elapsed >= self.duration {
            return None;
        }

        let lambda = self.current_rate();
        let u: f64 = self.rng.gen();
        let wait_s = -u.ln() / lambda;
        let wait = Duration::from_secs_f64(wait_s);

        self.elapsed += wait;
        Some((wait, self.task_work_us))
    }
}

/// Adversarial workload (random rate and work variations)
pub struct AdversarialWorkload {
    base_rate: f64,
    work_range_us: (u64, u64),
    duration: Duration,
    elapsed: Duration,
    rng: rand::rngs::ThreadRng,
}

impl AdversarialWorkload {
    pub fn new(
        base_rate: f64,
        work_range_us: (u64, u64),
        duration: Duration,
    ) -> Self {
        Self {
            base_rate,
            work_range_us,
            duration,
            elapsed: Duration::ZERO,
            rng: rand::thread_rng(),
        }
    }
}

impl WorkloadGenerator for AdversarialWorkload {
    fn next_task(&mut self) -> Option<(Duration, u64)> {
        if self.elapsed >= self.duration {
            return None;
        }

        // Random rate variation
        let rate_multiplier: f64 = self.rng.gen_range(0.1..5.0);
        let lambda = self.base_rate * rate_multiplier;

        let u: f64 = self.rng.gen();
        let wait_s = -u.ln() / lambda;
        let wait = Duration::from_secs_f64(wait_s);

        // Random work amount
        let work_us = self.rng.gen_range(self.work_range_us.0..=self.work_range_us.1);

        self.elapsed += wait;
        Some((wait, work_us))
    }
}
