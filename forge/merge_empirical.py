#!/usr/bin/env python3
"""
Merge parallel empirical labelling results.
"""

import pandas as pd
import sys
import os
import glob

def merge_empirical_results(results_dir, output_csv):
    """Merge all empirical_*.csv files in results_dir"""

    pattern = os.path.join(results_dir, "empirical_*.csv")
    files = sorted(glob.glob(pattern))

    if not files:
        print(f"ERROR: No empirical_*.csv files found in {results_dir}")
        sys.exit(1)

    print(f"Found {len(files)} result files:")
    for f in files:
        print(f"  {f}")

    # Load and concatenate
    dfs = []
    for f in files:
        df = pd.read_csv(f)
        dfs.append(df)
        print(f"  Loaded {len(df)} samples from {os.path.basename(f)}")

    merged = pd.concat(dfs, ignore_index=True)
    print(f"\n✓ Merged {len(merged)} total samples")

    # Save
    merged.to_csv(output_csv, index=False)
    print(f"✓ Saved to {output_csv}")

    # Print statistics
    print("\n=== Merged Label Distribution ===")
    print(merged['optimal_n_workers'].value_counts().sort_index())

    print("\n=== Empirical p95 Statistics ===")
    print(merged['empirical_p95'].describe())

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: merge_empirical.py <results_dir> <output.csv>")
        sys.exit(1)

    merge_empirical_results(sys.argv[1], sys.argv[2])
