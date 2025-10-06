//! Baseline thread pool simulator
//!
//! Runs thread pool with static sizing (N=8)

use sim_compute::{BaselinePolicy, SteadyWorkload, ThreadPoolSim, WorkloadGenerator};
use std::thread;
use std::time::Duration;

fn main() {
    println!("=== Thread Pool Simulator: Baseline ===");
    println!("Policy: Static N=8 workers\n");

    let policy = BaselinePolicy::new();
    let mut sim = ThreadPoolSim::new(policy, 8);

    // Steady workload: 100 tasks/sec, 500µs per task, for 10 seconds
    let mut workload = SteadyWorkload::new(100.0, 500, Duration::from_secs(10));

    println!("Starting simulation...");
    println!("Workload: Steady 100 tasks/sec, 500µs/task, 10s duration\n");

    let start = std::time::Instant::now();

    // Run simulation
    loop {
        // Generate tasks
        if let Some((wait, work_us)) = workload.next_task() {
            thread::sleep(wait.min(Duration::from_micros(100))); // Speed up sim
            sim.enqueue(work_us);
        }

        // Tick simulator every 10ms
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
