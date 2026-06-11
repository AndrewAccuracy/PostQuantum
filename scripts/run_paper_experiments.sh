#!/usr/bin/env bash
set -euo pipefail

PYTHON="${PYTHON:-.venv/bin/python}"
OUTPUT_ROOT="${OUTPUT_ROOT:-results/paper_runs}"
RUNS="${RUNS:-5}"
SAMPLES_PER_CLASS="${SAMPLES_PER_CLASS:-400}"
REPETITIONS="${REPETITIONS:-50}"
N_GROUPS="${N_GROUPS:-60}"
WARMUP="${WARMUP:-500}"
VARIANTS="${VARIANTS:-512 768 1024}"
INVALID_STRATEGIES="${INVALID_STRATEGIES:-single_bit byte_flip random_bytes zero}"

mkdir -p "$OUTPUT_ROOT"

for run in $(seq -w 1 "$RUNS"); do
  output_dir="$OUTPUT_ROOT/run_${run}"
  echo "Collecting $output_dir"
  "$PYTHON" -m mlkem_leakage.cli \
    --output-dir "$output_dir" \
    --samples-per-class "$SAMPLES_PER_CLASS" \
    --repetitions "$REPETITIONS" \
    --groups "$N_GROUPS" \
    --warmup "$WARMUP" \
    --seed "$((20260602 + 10#$run))" \
    --control-delay-ns 20000 \
    --variants $VARIANTS \
    --invalid-strategies $INVALID_STRATEGIES
done

"$PYTHON" -m mlkem_leakage.paper_artifacts \
  --input-root "$OUTPUT_ROOT" \
  --output-dir results/paper_artifacts
