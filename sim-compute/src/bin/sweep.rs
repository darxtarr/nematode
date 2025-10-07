//! Pool Size Sweep - Empirical Ground Truth Collector
//!
//! Runs simulations across N ∈ {1,2,4,8,16,32,64} for a given workload
//! and measures actual p95 latency to find empirically optimal pool size.

use sim_compute::{PoolSizeDecision, PoolSizePolicy, SteadyWorkload, ThreadPoolSim, WorkloadGenerator};
use std::thread;
use std::time::Duration;
use std::env;

/// Fixed pool size policy (for testing specific N values)
struct FixedPolicy {
    n_workers: u32,
}

impl FixedPolicy {
    fn new(n_workers: u32) -> Self {
        Self { n_workers }
    }
}

impl PoolSizePolicy for FixedPolicy {
    fn decide(&mut self, _telem: &telemetry_compute::ComputeTelemetry) -> PoolSizeDecision {
        PoolSizeDecision {
            n_workers: self.n_workers,
        }
    }
}

fn run_simulation(n_workers: u32, arrival_rate: f64, task_us: u64, duration_secs: u64) -> (f64, f64, f64, f64) {
    let policy = FixedPolicy::new(n_workers);
    let mut sim = ThreadPoolSim::new(policy, n_workers);

    let mut workload = SteadyWorkload::new(arrival_rate, task_us, Duration::from_secs(duration_secs));

    let start = std::time::Instant::now();

    // Run simulation
    loop {
        if let Some((wait, work_us)) = workload.next_task() {
            thread::sleep(wait.min(Duration::from_micros(100)));
            sim.enqueue(work_us);
        }

        sim.tick();
        thread::sleep(Duration::from_millis(10));

        if start.elapsed() >= Duration::from_secs(duration_secs + 1) {
            break;
        }
    }

    let metrics = sim.metrics();
    (
        metrics.p50_task_time(),
        metrics.p95_task_time(),
        metrics.p99_task_time(),
        metrics.mean_throughput(),
    )
}

fn main() {
    let args: Vec<String> = env::args().collect();

    if args.len() < 4 {
        eprintln!("Usage: sweep <arrival_rate> <task_us> <duration_secs>");
        eprintln!("Example: sweep 100 500 5");
        std::process::exit(1);
    }

    let arrival_rate: f64 = args[1].parse().expect("arrival_rate must be float");
    let task_us: u64 = args[2].parse().expect("task_us must be u64");
    let duration_secs: u64 = args[3].parse().expect("duration_secs must be u64");

    println!("=== Pool Size Sweep ===");
    println!("Workload: {} tasks/sec, {} µs/task, {} sec duration\n", arrival_rate, task_us, duration_secs);
    println!("{:<10} {:>12} {:>12} {:>12} {:>15}", "N Workers", "p50 (µs)", "p95 (µs)", "p99 (µs)", "Throughput");
    println!("{:-<65}", "");

    let pool_sizes = [1, 2, 4, 8, 16, 32, 64];
    let mut best_n = 1;
    let mut best_p95 = f64::MAX;

    for n in pool_sizes {
        let (p50, p95, p99, throughput) = run_simulation(n, arrival_rate, task_us, duration_secs);

        println!("{:<10} {:>12.0} {:>12.0} {:>12.0} {:>15.2}",
                 n, p50, p95, p99, throughput);

        if p95 < best_p95 {
            best_p95 = p95;
            best_n = n;
        }
    }

    println!("\n=== Empirical Optimum ===");
    println!("Best N: {} (p95 = {:.0} µs)", best_n, best_p95);
}
