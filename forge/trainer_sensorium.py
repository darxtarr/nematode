#!/usr/bin/env python3
"""
Reflex Trainer for Sensorium Adaptive Sampling

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
    'signal_variance',
    'signal_mean',
    'dominant_freq_hz',
    'freq_energy_ratio',
    'zero_crossings_per_sec',
    'sample_age_ms',
    'reconstruction_error_ewma',
    'power_budget_pct',
    'event_rate_hz',
    'signal_snr_db',
]

TARGET_NAME = 'optimal_sampling_rate_hz'


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

    print(f"  Train MAE: {train_mae:.2f} Hz, R²: {train_r2:.3f}")
    print(f"  Test MAE: {test_mae:.2f} Hz, R²: {test_r2:.3f}")

    return model, train_r2, test_r2


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
    trees = [tree_nodes]
    model_json = json.dumps(trees).encode('utf-8')

    # Encode bounds (sampling rate range)
    bounds = {
        'min': [1.0],
        'max': [100.0]
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
    n_outputs = 1

    # Pack binary
    with open(output_path, 'wb') as f:
        # Header (16 bytes)
        f.write(magic)  # 4 bytes
        f.write(struct.pack('<I', version))  # 4 bytes
        f.write(struct.pack('<I', n_inputs))  # 4 bytes
        f.write(struct.pack('<I', n_outputs))  # 4 bytes

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
    """Save normalizer as standalone JSON for convenience."""
    normalizer = {
        'feature_names': FEATURE_NAMES,
        'mins': mins.tolist(),
        'maxs': maxs.tolist()
    }
    with open(output_path, 'w') as f:
        json.dump(normalizer, f, indent=2)
    print(f"✓ Saved normalizer: {output_path}")


def compute_feature_correlations(df):
    """Analyze feature correlations with target."""
    print("\n=== Feature Correlations with Optimal Sampling Rate ===")

    correlations = []
    for feat in FEATURE_NAMES:
        corr = df[feat].corr(df[TARGET_NAME])
        correlations.append((feat, corr))

    # Sort by absolute correlation
    correlations.sort(key=lambda x: abs(x[1]), reverse=True)

    for feat, corr in correlations:
        print(f"  {feat:30s}: {corr:+.3f}")

    return correlations


def main(csv_path, reflex_output_path, normalizer_output_path):
    print("=== Sensorium Adaptive Sampling Reflex Trainer ===\n")

    # Load data
    print(f"Loading training data from {csv_path}...")
    X, y, df = load_training_data(csv_path)
    print(f"  Loaded {len(X)} samples, {X.shape[1]} features")

    # Analyze label distribution
    print("\n=== Label Distribution ===")
    unique, counts = np.unique(y, return_counts=True)
    for rate, count in zip(unique, counts):
        pct = 100.0 * count / len(y)
        print(f"  {rate:3.0f} Hz: {count:4d} samples ({pct:5.1f}%)")

    # Compute feature correlations
    compute_feature_correlations(df)

    # Split data
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )

    # Normalize
    print("\nNormalizing features...")
    X_train_norm, X_test_norm, mins, maxs = normalize_features(X_train, X_test)

    # Train
    model, train_r2, test_r2 = train_tree(X_train_norm, y_train, X_test_norm, y_test)

    # Export tree structure
    print("\nExporting tree structure...")
    tree_nodes = export_tree_to_nodes(model)
    print(f"  Tree has {len(tree_nodes)} nodes")

    # Compute telemetry hash
    csv_bytes = open(csv_path, 'rb').read()
    telemetry_hash = hashlib.sha256(csv_bytes).digest()

    # Serialize .reflex
    print("\nSerializing .reflex file...")
    serialize_reflex(tree_nodes, mins, maxs, telemetry_hash, reflex_output_path)

    # Save normalizer JSON
    save_normalizer_json(mins, maxs, normalizer_output_path)

    # Summary
    print("\n=== Training Summary ===")
    print(f"  Model: Decision Tree (depth {model.get_depth()})")
    print(f"  Train R²: {train_r2:.3f}")
    print(f"  Test R²: {test_r2:.3f}")
    print(f"  Reflex size: {len(open(reflex_output_path, 'rb').read())} bytes")

    if test_r2 > 0.3:
        print(f"\n✅ REFLEX-VIABLE: Test R²={test_r2:.3f} > 0.3 (learnable structure detected)")
    elif test_r2 < 0.1:
        print(f"\n⚠️  HEURISTIC-SATURATED: Test R²={test_r2:.3f} < 0.1 (flat landscape)")
    else:
        print(f"\n⚡ MARGINAL: Test R²={test_r2:.3f} (weak but detectable structure)")


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: trainer_sensorium.py <input.csv> <output.reflex> <normalizer.json>")
        sys.exit(1)

    csv_path = sys.argv[1]
    reflex_output = sys.argv[2]
    normalizer_output = sys.argv[3]

    main(csv_path, reflex_output, normalizer_output)
