#!/bin/bash
# Parallel Empirical Labelling Runner
#
# Usage: ./forge/parallel_empirical.sh
#
# This splits telemetry into chunks and generates commands for parallel execution.

set -e

TELEMETRY="data/telemetry/compute-training.csv"
CHUNKS_DIR="data/telemetry/chunks"
OUTPUT_DIR="data/telemetry/empirical-results"
N_CHUNKS=10
DURATION_SECS=2

echo "=== Parallel Empirical Labelling Setup ==="
echo "Telemetry: $TELEMETRY"
echo "Chunks: $N_CHUNKS"
echo "Duration per sample: ${DURATION_SECS}s"
echo ""

# Split telemetry
echo "Splitting telemetry into $N_CHUNKS chunks..."
source venv/bin/activate
python forge/split_telemetry.py "$TELEMETRY" "$CHUNKS_DIR" $N_CHUNKS

# Create output directory
mkdir -p "$OUTPUT_DIR"

# Generate parallel commands
echo ""
echo "=== Parallel Commands ==="
echo "Run these in separate terminals (or use GNU parallel/tmux):"
echo ""

for i in $(seq 0 $((N_CHUNKS-1))); do
    chunk=$(printf "chunk_%03d.csv" $i)
    output=$(printf "empirical_%03d.csv" $i)

    cmd="source venv/bin/activate && python forge/oracle_compute_empirical.py $CHUNKS_DIR/$chunk $OUTPUT_DIR/$output all $DURATION_SECS 2>&1 | tee $OUTPUT_DIR/log_$i.txt"

    echo "# Terminal $i:"
    echo "$cmd"
    echo ""
done

echo "=== After all jobs complete, merge results with: ==="
echo "python forge/merge_empirical.py $OUTPUT_DIR data/telemetry/compute-empirical-full.csv"
echo ""
echo "=== Or use GNU parallel for automated execution: ==="
echo "parallel -j $N_CHUNKS 'source venv/bin/activate && python forge/oracle_compute_empirical.py $CHUNKS_DIR/chunk_{}.csv $OUTPUT_DIR/empirical_{}.csv all $DURATION_SECS > $OUTPUT_DIR/log_{}.txt 2>&1' ::: $(seq -w 0 $((N_CHUNKS-1)))"
