//! Reflex thread pool simulator
//!
//! Runs thread pool with adaptive sizing from .reflex model

use sim_compute::{ReflexPolicy, SteadyWorkload, ThreadPoolSim, WorkloadGenerator};
use std::thread;
use std::time::Duration;

fn main() {
    println!("=== Thread Pool Simulator: Reflex ===");

    let reflex_path = "data/models/thread-pool.reflex";
    let normalizer_path = "data/models/normalizer-compute.json";

    // Load normalizer
    let normalizer_json = std::fs::read_to_string(normalizer_path)
        .expect("Failed to load normalizer");
    let normalizer: telemetry_compute::Normalizer = serde_json::from_str(&normalizer_json)
        .expect("Failed to parse normalizer");

    // Load reflex
    let policy = ReflexPolicy::load(reflex_path, normalizer)
        .expect("Failed to load reflex");

    let mut sim = ThreadPoolSim::new(policy, 8); // Start with 8 workers

    // Steady workload: 100 tasks/sec, 500µs per task, for 10 seconds
    let mut workload = SteadyWorkload::new(100.0, 500, Duration::from_secs(10));

    println!("Policy: Reflex from {}", reflex_path);
    println!("Workload: Steady 100 tasks/sec, 500µs/task, 10s duration\n");

    let start = std::time::Instant::now();

    // Run simulation
    loop {
        // Generate tasks
        if let Some((wait, work_us)) = workload.next_task() {
            thread::sleep(wait.min(Duration::from_micros(100)));
            sim.enqueue(work_us);
        }

        // Tick simulator
        sim.tick();
        thread::sleep(Duration::from_millis(10));

        // Check if done
        if start.elapsed() >= Duration::from_secs(11) {
            break;
        }
    }

    // Print metrics
    let metrics = sim.metrics();
    println!("\n=== Results ===");
    println!("Total tasks completed: {}", metrics.task_times_us.len());
    println!("p50 task time: {:.2} µs", metrics.p50_task_time());
    println!("p95 task time: {:.2} µs", metrics.p95_task_time());
    println!("p99 task time: {:.2} µs", metrics.p99_task_time());
    println!("Mean throughput: {:.2} tasks/s", metrics.mean_throughput());
    println!("Decision changes: {}", metrics.decision_changes);
}
