//! Baseline policy runner
//!
//! Runs the fake transport with static flush policy

use sim::{BaselinePolicy, FakeTransport, SteadyWorkload, BurstyWorkload, AdversarialWorkload, WorkloadGenerator};
use std::time::Duration;
use std::thread;

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let workload_type = args.get(1).map(|s| s.as_str()).unwrap_or("steady");

    println!("Running baseline policy with {} workload", workload_type);

    let mut transport = FakeTransport::new(BaselinePolicy::new());

    // Create workload
    let duration = Duration::from_secs(30);
    let mut workload: Box<dyn WorkloadGenerator> = match workload_type {
        "steady" => Box::new(SteadyWorkload::new(1000.0, 1024, duration)),
        "bursty" => Box::new(BurstyWorkload::new(
            5000.0,
            100.0,
            1024,
            Duration::from_secs(5),
            duration,
        )),
        "adversarial" => Box::new(AdversarialWorkload::new(
            1000.0,
            (256, 2048),
            duration,
        )),
        _ => {
            eprintln!("Unknown workload type: {}", workload_type);
            eprintln!("Usage: baseline [steady|bursty|adversarial]");
            std::process::exit(1);
        }
    };

    // Run simulation
    let start = std::time::Instant::now();
    let tick_interval = Duration::from_micros(100); // 10 kHz tick rate

    loop {
        // Enqueue packets
        while let Some((wait, size)) = workload.next_packet() {
            if wait > Duration::ZERO {
                thread::sleep(wait.min(tick_interval));
            }
            transport.enqueue(size);

            // Tick transport
            transport.tick();

            if start.elapsed() >= duration {
                break;
            }
        }

        if start.elapsed() >= duration {
            break;
        }

        thread::sleep(tick_interval);
        transport.tick();
    }

    // Final flush
    transport.tick();

    // Print metrics
    let metrics = transport.metrics();
    println!("\n=== Metrics ===");
    println!("Total packets: {}", metrics.latencies_us.len());
    println!("p50 latency: {:.2} µs", metrics.p50_latency());
    println!("p95 latency: {:.2} µs", metrics.p95_latency());
    println!("p99 latency: {:.2} µs", metrics.p99_latency());
    println!("p99/p50 ratio: {:.2}", metrics.p99_latency() / metrics.p50_latency());
    println!("Mean throughput: {:.2} pkts/s", metrics.mean_throughput());
    println!("Decision changes: {}", metrics.decision_changes);
}
