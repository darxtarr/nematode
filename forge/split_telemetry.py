#!/usr/bin/env python3
"""
Split telemetry CSV into chunks for parallel processing.
"""

import pandas as pd
import sys
import os

def split_telemetry(input_csv, output_dir, n_chunks):
    """Split CSV into n_chunks files"""
    df = pd.read_csv(input_csv)
    chunk_size = len(df) // n_chunks

    os.makedirs(output_dir, exist_ok=True)

    for i in range(n_chunks):
        start = i * chunk_size
        end = start + chunk_size if i < n_chunks - 1 else len(df)

        chunk = df.iloc[start:end]
        output_file = f"{output_dir}/chunk_{i:03d}.csv"
        chunk.to_csv(output_file, index=False)
        print(f"Chunk {i}: {len(chunk)} samples → {output_file}")

    print(f"\n✓ Split {len(df)} samples into {n_chunks} chunks")

if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: split_telemetry.py <input.csv> <output_dir> <n_chunks>")
        sys.exit(1)

    split_telemetry(sys.argv[1], sys.argv[2], int(sys.argv[3]))
