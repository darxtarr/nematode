#!/usr/bin/env python3
"""
Reflex Trainer for Thread Pool Sizing

Trains decision trees from labeled telemetry and exports to .reflex format.
"""

import pandas as pd
import numpy as np
from sklearn.tree import DecisionTreeRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, r2_score
import json
import struct
import sys
from datetime import datetime
import hashlib


FEATURE_NAMES = [
    'runq_len',
    'arrival_rate',
    'completion_rate',
    'task_time_p50_us',
    'task_time_p95_us',
    'worker_util',
    'ctx_switches_per_sec',
    'task_size_mean',
    'task_size_var',
    'idle_worker_count',
]

TARGET_NAME = 'optimal_n_workers'


def load_training_data(csv_path: str):
    """Load labeled training data"""
    df = pd.read_csv(csv_path)
    X = df[FEATURE_NAMES].values
    y = df[TARGET_NAME].values
    return X, y, df


def normalize_features(X_train, X_test):
    """Min-max normalization to [0, 1]"""
    mins = X_train.min(axis=0)
    maxs = X_train.max(axis=0)
    ranges = maxs - mins

    # Avoid division by zero
    ranges[ranges == 0] = 1.0

    X_train_norm = (X_train - mins) / ranges
    X_test_norm = (X_test - mins) / ranges

    return X_train_norm, X_test_norm, mins, maxs


def train_tree(X_train, y_train, X_test, y_test, max_depth: int = 4):
    """Train a single decision tree"""
    print(f"\nTraining tree for {TARGET_NAME}...")
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

    print(f"  Train MAE: {train_mae:.2f} workers, R²: {train_r2:.3f}")
    print(f"  Test MAE: {test_mae:.2f} workers, R²: {test_r2:.3f}")

    return model


def export_tree_to_nodes(tree):
    """
    Convert sklearn DecisionTreeRegressor to TreeNode format.
    """
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
    tree_nodes,
    mins,
    maxs,
    telemetry_hash,
    output_path
):
    """
    Serialize to .reflex binary format.
    """
    # Encode model (single tree as JSON)
    trees = [tree_nodes]  # Wrap in array for consistency
    model_json = json.dumps(trees).encode('utf-8')

    # Encode bounds (pool size range)
    bounds = {
        'min': [1.0],
        'max': [64.0]
    }
    bounds_json = json.dumps(bounds).encode('utf-8')

    # Metadata
    metadata = {
        'created_at': datetime.utcnow().isoformat() + 'Z',
        'trainer_commit': 'forge@compute-v1',
        'feature_schema': 'compute-v1',
        'telemetry_hash': telemetry_hash,
        'lambda': 0.0,  # Not used for compute (single output)
        'notes': 'Thread pool sizing reflex',
    }
    metadata_json = json.dumps(metadata).encode('utf-8')

    # Build header
    magic = b'NEM1'
    version = 1
    model_type = 0  # DecisionTree
    feature_count = len(FEATURE_NAMES)
    output_count = 1  # Single output: n_workers
    created_at_unix = int(datetime.utcnow().timestamp())
    model_size = len(model_json)
    bounds_size = len(bounds_json)
    metadata_size = len(metadata_json)

    header = struct.pack(
        '<4sHBBBQIII',
        magic,
        version,
        model_type,
        feature_count,
        output_count,
        created_at_unix,
        model_size,
        bounds_size,
        metadata_size
    )

    # Combine payload
    payload = header + model_json + bounds_json + metadata_json

    # Compute CRC32
    crc = 0xFFFFFFFF
    for byte in payload:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0xEDB88320 if (crc & 1) else (crc >> 1)
    crc ^= 0xFFFFFFFF
    crc_bytes = struct.pack('<I', crc & 0xFFFFFFFF)

    # Write file
    with open(output_path, 'wb') as f:
        f.write(payload + crc_bytes)

    print(f"\n✓ Exported reflex to {output_path}")
    print(f"  Size: {len(payload) + 4} bytes")


def export_normalizer(mins, maxs, output_path):
    """Export normalizer as JSON"""
    normalizer = {
        'min': mins.tolist(),
        'max': maxs.tolist()
    }
    with open(output_path, 'w') as f:
        json.dump(normalizer, f, indent=2)
    print(f"✓ Exported normalizer to {output_path}")


def train_and_export(training_csv, output_reflex, normalizer_path):
    """Full training pipeline"""
    print("=" * 60)
    print("REFLEX TRAINER: COMPUTE")
    print("=" * 60)

    # Load data
    print(f"\nLoading training data from {training_csv}...")
    X, y, df = load_training_data(training_csv)
    print(f"Loaded {len(X)} samples, {len(FEATURE_NAMES)} features")

    # Compute telemetry hash
    telemetry_hash = hashlib.sha1(df.to_csv(index=False).encode()).hexdigest()[:8]

    # Split
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )

    # Normalize
    print("\nNormalizing features...")
    X_train_norm, X_test_norm, mins, maxs = normalize_features(X_train, X_test)

    # Train tree
    tree = train_tree(X_train_norm, y_train, X_test_norm, y_test)

    # Export tree
    print("\nExporting tree to node format...")
    tree_nodes = export_tree_to_nodes(tree)
    print(f"  Tree: {len(tree_nodes)} nodes")

    # Serialize
    serialize_reflex(
        tree_nodes,
        mins,
        maxs,
        telemetry_hash,
        output_reflex
    )

    # Export normalizer
    export_normalizer(mins, maxs, normalizer_path)

    print("\n" + "=" * 60)
    print("Training complete!")
    print("=" * 60)


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: trainer_compute.py <training.csv> <output.reflex> <normalizer.json>")
        sys.exit(1)

    training_csv = sys.argv[1]
    output_reflex = sys.argv[2]
    normalizer_path = sys.argv[3]

    train_and_export(training_csv, output_reflex, normalizer_path)
