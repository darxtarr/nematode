#!/usr/bin/env python3
"""Export normalizer from training data for runtime use"""

import pandas as pd
import json
import sys

if len(sys.argv) < 3:
    print("Usage: export_normalizer.py <training.csv> <output.json>")
    sys.exit(1)

df = pd.read_csv(sys.argv[1])

FEATURE_NAMES = [
    'queue_depth', 'enqueue_rate', 'dequeue_rate',
    'latency_p50_us', 'latency_p95_us',
    'bytes_in_per_sec', 'bytes_out_per_sec',
    'packet_size_mean', 'packet_size_var', 'rtt_ewma_us'
]

X = df[FEATURE_NAMES].values
mins = X.min(axis=0).tolist()
maxs = X.max(axis=0).tolist()

normalizer = {'min': mins, 'max': maxs}

with open(sys.argv[2], 'w') as f:
    json.dump(normalizer, f, indent=2)

print(f"✓ Exported normalizer to {sys.argv[2]}")
