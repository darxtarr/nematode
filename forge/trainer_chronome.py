#!/usr/bin/env python3
"""
Reflex Trainer for Chronome Adaptive Batching

Trains two decision trees (threshold + delay) from labeled telemetry.
"""

import pandas as pd
import numpy as np
from sklearn.tree import DecisionTreeRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, r2_score
import json
import struct
import sys
import hashlib


FEATURE_NAMES = [
    'queue_depth',
    'arrival_rate_hz',
    'dequeue_rate_hz',
    'latency_p50_us',
    'latency_p95_us',
    'latency_p99_us',
    'msg_size_mean',
    'msg_size_var',
    'batch_size_mean',
    'batch_flushes_per_sec',
    'burstiness',
    'backlog_age_p95_us',
]

TARGET_NAMES = ['optimal_batch_threshold', 'optimal_max_delay_us']


def load_training_data(csv_path: str):
    """Load labeled training data"""
    df = pd.read_csv(csv_path)
    X = df[FEATURE_NAMES].values
    y_threshold = df['optimal_batch_threshold'].values
    y_delay = df['optimal_max_delay_us'].values
    return X, y_threshold, y_delay, df


def normalize_features(X_train, X_test):
    """Min-max normalization to [0, 1]"""
    mins = X_train.min(axis=0)
    maxs = X_train.max(axis=0)
    ranges = maxs - mins
    ranges[ranges == 0] = 1.0

    X_train_norm = (X_train - mins) / ranges
    X_test_norm = (X_test - mins) / ranges

    return X_train_norm, X_test_norm, mins, maxs


def train_tree(X_train, y_train, X_test, y_test, target_name: str, max_depth: int = 4):
    """Train a single decision tree"""
    print(f"\nTraining tree for {target_name}...")
    print(f"  Training samples: {len(X_train)}")
    print(f"  Test samples: {len(X_test)}")

    model = DecisionTreeRegressor(
        max_depth=max_depth,
        min_samples_leaf=20,
        random_state=42
    )

    model.fit(X_train, y_train)

    # Evaluate
    y_pred_train = model.predict(X_train)
    y_pred_test = model.predict(X_test)

    train_mae = mean_absolute_error(y_train, y_pred_train)
    test_mae = mean_absolute_error(y_test, y_pred_test)
    train_r2 = r2_score(y_train, y_pred_train)
    test_r2 = r2_score(y_test, y_pred_test)

    print(f"  Train MAE: {train_mae:.2f}, R²: {train_r2:.3f}")
    print(f"  Test MAE: {test_mae:.2f}, R²: {test_r2:.3f}")

    return model, train_r2, test_r2


def export_tree_to_nodes(tree):
    """Convert sklearn tree to node format"""
    nodes = []

    def recurse(node_id):
        current_idx = len(nodes)

        feature = tree.tree_.feature[node_id]
        threshold = tree.tree_.threshold[node_id]
        left_child = tree.tree_.children_left[node_id]
        right_child = tree.tree_.children_right[node_id]

        if left_child == right_child:  # leaf
            value = tree.tree_.value[node_id][0][0]
            nodes.append({
                "feature_idx": 255,
                "threshold": float(value),
                "left": 0,
                "right": 0
            })
        else:
            nodes.append({"feature_idx": 0, "threshold": 0.0, "left": 0, "right": 0})

            left_idx = len(nodes)
            recurse(left_child)

            right_idx = len(nodes)
            recurse(right_child)

            nodes[current_idx] = {
                "feature_idx": int(feature),
                "threshold": float(threshold),
                "left": left_idx,
                "right": right_idx
            }

    recurse(0)
    return nodes


def serialize_reflex(
    tree_threshold_nodes,
    tree_delay_nodes,
    mins,
    maxs,
    telemetry_hash,
    output_path
):
    """Serialize two trees to .reflex binary format"""
    # Encode models (two trees as JSON array)
    trees = [tree_threshold_nodes, tree_delay_nodes]
    model_json = json.dumps(trees).encode('utf-8')

    # Encode bounds (threshold, delay ranges)
    bounds = {
        'min': [1.0, 50.0],
        'max': [64.0, 4000.0]
    }
    bounds_json = json.dumps(bounds).encode('utf-8')

    # Encode normalizer
    normalizer = {
        'mins': mins.tolist(),
        'maxs': maxs.tolist()
    }
    normalizer_json = json.dumps(normalizer).encode('utf-8')

    # Header
    magic = b'RFLX'
    version = 1
    n_inputs = len(mins)
    n_outputs = 2  # threshold + delay

    # Pack binary
    with open(output_path, 'wb') as f:
        # Header (16 bytes)
        f.write(magic)
        f.write(struct.pack('<I', version))
        f.write(struct.pack('<I', n_inputs))
        f.write(struct.pack('<I', n_outputs))

        # Model blob
        f.write(struct.pack('<I', len(model_json)))
        f.write(model_json)

        # Bounds blob
        f.write(struct.pack('<I', len(bounds_json)))
        f.write(bounds_json)

        # Normalizer blob
        f.write(struct.pack('<I', len(normalizer_json)))
        f.write(normalizer_json)

        # Telemetry hash (32 bytes)
        f.write(telemetry_hash)

        file_size = f.tell()
        print(f"\n✓ Exported .reflex file: {output_path} ({file_size} bytes)")


def save_normalizer_json(mins, maxs, output_path):
    """Save normalizer as standalone JSON"""
    normalizer = {
        'feature_names': FEATURE_NAMES,
        'mins': mins.tolist(),
        'maxs': maxs.tolist()
    }
    with open(output_path, 'w') as f:
        json.dump(normalizer, f, indent=2)
    print(f"✓ Saved normalizer: {output_path}")


def compute_feature_correlations(df):
    """Analyze feature correlations with targets"""
    print("\n=== Feature Correlations ===")

    for target in TARGET_NAMES:
        print(f"\n{target}:")
        correlations = []
        for feat in FEATURE_NAMES:
            corr = df[feat].corr(df[target])
            correlations.append((feat, corr))

        correlations.sort(key=lambda x: abs(x[1]), reverse=True)

        for feat, corr in correlations[:5]:  # Top 5
            print(f"  {feat:30s}: {corr:+.3f}")

    return correlations


def main(csv_path, reflex_output_path, normalizer_output_path):
    print("=== Chronome Adaptive Batching Reflex Trainer ===\n")

    # Load data
    print(f"Loading training data from {csv_path}...")
    X, y_threshold, y_delay, df = load_training_data(csv_path)
    print(f"  Loaded {len(X)} samples, {X.shape[1]} features")

    # Analyze label distribution
    print("\n=== Label Distribution ===")
    print("Batch Thresholds:")
    unique_thresh, counts_thresh = np.unique(y_threshold, return_counts=True)
    for val, count in zip(unique_thresh, counts_thresh):
        pct = 100.0 * count / len(y_threshold)
        print(f"  {val:3.0f}: {count:4d} samples ({pct:5.1f}%)")

    print("\nMax Delays (µs):")
    unique_delay, counts_delay = np.unique(y_delay, return_counts=True)
    for val, count in zip(unique_delay, counts_delay):
        pct = 100.0 * count / len(y_delay)
        print(f"  {val:4.0f}: {count:4d} samples ({pct:5.1f}%)")

    # Compute feature correlations
    compute_feature_correlations(df)

    # Split data
    X_train, X_test, y_thresh_train, y_thresh_test, y_delay_train, y_delay_test = train_test_split(
        X, y_threshold, y_delay, test_size=0.2, random_state=42
    )

    # Normalize
    print("\nNormalizing features...")
    X_train_norm, X_test_norm, mins, maxs = normalize_features(X_train, X_test)

    # Train threshold tree
    model_threshold, train_r2_thresh, test_r2_thresh = train_tree(
        X_train_norm, y_thresh_train, X_test_norm, y_thresh_test,
        'optimal_batch_threshold'
    )

    # Train delay tree
    model_delay, train_r2_delay, test_r2_delay = train_tree(
        X_train_norm, y_delay_train, X_test_norm, y_delay_test,
        'optimal_max_delay_us'
    )

    # Export tree structures
    print("\nExporting tree structures...")
    tree_threshold_nodes = export_tree_to_nodes(model_threshold)
    tree_delay_nodes = export_tree_to_nodes(model_delay)
    print(f"  Threshold tree: {len(tree_threshold_nodes)} nodes")
    print(f"  Delay tree: {len(tree_delay_nodes)} nodes")

    # Compute telemetry hash
    csv_bytes = open(csv_path, 'rb').read()
    telemetry_hash = hashlib.sha256(csv_bytes).digest()

    # Serialize .reflex
    print("\nSerializing .reflex file...")
    serialize_reflex(
        tree_threshold_nodes, tree_delay_nodes,
        mins, maxs, telemetry_hash, reflex_output_path
    )

    # Save normalizer JSON
    save_normalizer_json(mins, maxs, normalizer_output_path)

    # Summary
    print("\n=== Training Summary ===")
    print(f"  Threshold tree: depth {model_threshold.get_depth()}, R² = {test_r2_thresh:.3f}")
    print(f"  Delay tree: depth {model_delay.get_depth()}, R² = {test_r2_delay:.3f}")
    print(f"  Combined R² (avg): {(test_r2_thresh + test_r2_delay) / 2:.3f}")
    print(f"  Reflex size: {len(open(reflex_output_path, 'rb').read())} bytes")

    avg_r2 = (test_r2_thresh + test_r2_delay) / 2
    if avg_r2 > 0.3:
        print(f"\n✅ REFLEX-VIABLE: Avg R²={avg_r2:.3f} > 0.3 (learnable structure)")
    elif avg_r2 < 0.1:
        print(f"\n⚠️  HEURISTIC-SATURATED: Avg R²={avg_r2:.3f} < 0.1 (flat landscape)")
    else:
        print(f"\n⚡ MARGINAL: Avg R²={avg_r2:.3f} (weak structure)")


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: trainer_chronome.py <input.csv> <output.reflex> <normalizer.json>")
        sys.exit(1)

    csv_path = sys.argv[1]
    reflex_output = sys.argv[2]
    normalizer_output = sys.argv[3]

    main(csv_path, reflex_output, normalizer_output)
