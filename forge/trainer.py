#!/usr/bin/env python3
"""
Reflex Trainer

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
    'queue_depth',
    'enqueue_rate',
    'dequeue_rate',
    'latency_p50_us',
    'latency_p95_us',
    'bytes_in_per_sec',
    'bytes_out_per_sec',
    'packet_size_mean',
    'packet_size_var',
    'rtt_ewma_us',
]

TARGET_NAMES = ['optimal_threshold', 'optimal_delay_us']


def load_training_data(csv_path: str):
    """Load labeled training data"""
    df = pd.read_csv(csv_path)
    X = df[FEATURE_NAMES].values
    y_threshold = df['optimal_threshold'].values
    y_delay = df['optimal_delay_us'].values
    return X, y_threshold, y_delay, df


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


def train_tree(X_train, y_train, X_test, y_test, name: str, max_depth: int = 4):
    """Train a single decision tree"""
    print(f"\nTraining tree for {name}...")
    print(f"  Training samples: {len(X_train)}")
    print(f"  Test samples: {len(X_test)}")

    model = DecisionTreeRegressor(
        max_depth=max_depth,
        min_samples_leaf=20,  # regularization
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

    return model


def export_tree_to_nodes(tree):
    """
    Convert sklearn DecisionTreeRegressor to our TreeNode format.

    Returns list of nodes as dictionaries matching Rust TreeNode struct.
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
                "feature_idx": 255,  # 0xFF = leaf marker
                "threshold": float(value),
                "left": 0,
                "right": 0
            })
        else:
            # Placeholder, will be filled after children
            nodes.append({"feature_idx": 0, "threshold": 0.0, "left": 0, "right": 0})

            # Recurse children
            left_idx = len(nodes)
            recurse(left_child)

            right_idx = len(nodes)
            recurse(right_child)

            # Update current node
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
    output_bounds,
    mins,
    maxs,
    telemetry_hash,
    lambda_param,
    output_path
):
    """
    Serialize to .reflex binary format.

    Layout: [Header][Model][Bounds][Metadata][CRC32]
    """
    # Encode model (both trees as JSON for now)
    trees = [tree_threshold_nodes, tree_delay_nodes]
    model_json = json.dumps(trees).encode('utf-8')

    # Encode bounds
    bounds = {
        'min': output_bounds['min'],
        'max': output_bounds['max']
    }
    bounds_json = json.dumps(bounds).encode('utf-8')

    # Encode metadata
    metadata = {
        'created_at': datetime.utcnow().isoformat() + 'Z',
        'trainer_commit': 'forge@v1',
        'feature_schema': 'v1',
        'telemetry_hash': telemetry_hash,
        'lambda': lambda_param,
        'notes': 'Chronome batch reflex',
    }
    metadata_json = json.dumps(metadata).encode('utf-8')

    # Build header
    magic = b'NEM1'
    version = 1
    model_type = 0  # DecisionTree
    feature_count = len(FEATURE_NAMES)
    output_count = 2
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


def train_and_export(training_csv, output_reflex, lambda_param=0.1):
    """Full training pipeline"""
    print("=" * 60)
    print("REFLEX TRAINER")
    print("=" * 60)

    # Load data
    print(f"\nLoading training data from {training_csv}...")
    X, y_threshold, y_delay, df = load_training_data(training_csv)
    print(f"Loaded {len(X)} samples, {len(FEATURE_NAMES)} features")

    # Compute telemetry hash
    telemetry_hash = hashlib.sha1(df.to_csv(index=False).encode()).hexdigest()[:8]

    # Split
    X_train, X_test, y_th_train, y_th_test, y_dl_train, y_dl_test = train_test_split(
        X, y_threshold, y_delay, test_size=0.2, random_state=42
    )

    # Normalize
    print("\nNormalizing features...")
    X_train_norm, X_test_norm, mins, maxs = normalize_features(X_train, X_test)

    # Train threshold tree
    tree_threshold = train_tree(X_train_norm, y_th_train, X_test_norm, y_th_test, "threshold")

    # Train delay tree
    tree_delay = train_tree(X_train_norm, y_dl_train, X_test_norm, y_dl_test, "delay (µs)")

    # Export trees
    print("\nExporting trees to node format...")
    tree_th_nodes = export_tree_to_nodes(tree_threshold)
    tree_dl_nodes = export_tree_to_nodes(tree_delay)
    print(f"  Threshold tree: {len(tree_th_nodes)} nodes")
    print(f"  Delay tree: {len(tree_dl_nodes)} nodes")

    # Output bounds
    output_bounds = {
        'min': [1.0, 50.0],  # threshold, delay_us
        'max': [64.0, 4000.0]
    }

    # Serialize
    serialize_reflex(
        tree_th_nodes,
        tree_dl_nodes,
        output_bounds,
        mins.tolist(),
        maxs.tolist(),
        telemetry_hash,
        lambda_param,
        output_reflex
    )

    print("\n" + "=" * 60)
    print("Training complete!")
    print("=" * 60)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: trainer.py <training.csv> <output.reflex> [lambda]")
        sys.exit(1)

    training_csv = sys.argv[1]
    output_reflex = sys.argv[2]
    lambda_param = float(sys.argv[3]) if len(sys.argv) > 3 else 0.1

    train_and_export(training_csv, output_reflex, lambda_param)
