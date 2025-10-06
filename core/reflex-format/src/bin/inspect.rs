//! Inspect a .reflex file

use reflex_format::Reflex;
use std::env;

fn main() {
    let args: Vec<String> = env::args().collect();
    if args.len() < 2 {
        eprintln!("Usage: inspect <reflex_file>");
        std::process::exit(1);
    }

    let path = &args[1];
    println!("Loading {}...", path);

    let bytes = std::fs::read(path).expect("Failed to read file");
    let reflex = Reflex::from_bytes(&bytes).expect("Failed to parse reflex");

    println!("\n=== Header ===");
    println!("Magic: {:?}", std::str::from_utf8(&reflex.header.magic).unwrap_or("???"));
    println!("Version: {}", reflex.header.version);
    println!("Model type: {}", reflex.header.model_type);
    println!("Features: {}", reflex.header.feature_count);
    println!("Outputs: {}", reflex.header.output_count);
    println!("Created: {}", reflex.header.created_at_unix);

    println!("\n=== Trees ===");
    for (i, tree) in reflex.trees.iter().enumerate() {
        println!("Tree {}: {} nodes", i, tree.len());
    }

    println!("\n=== Bounds ===");
    println!("Min: {:?}", reflex.bounds.min);
    println!("Max: {:?}", reflex.bounds.max);

    println!("\n=== Metadata ===");
    println!("{:#?}", reflex.metadata);

    println!("\n=== Test Inference ===");
    let test_features = vec![20.0, 1000.0, 1000.0, 300.0, 600.0, 1e6, 1e6, 1024.0, 100.0, 50.0];
    let norm_features: Vec<f32> = test_features.iter().map(|&x| x / 10000.0).collect(); // dummy normalization
    let outputs = reflex.infer(&norm_features);
    println!("Input (normalized): {:?}", &norm_features[..3]);
    println!("Output: {:?}", outputs);
}
