#!/usr/bin/env bash
set -euo pipefail
PYTHON="${PYTHON:-.venv/bin/python}"
OUTPUT_ROOT="${OUTPUT_ROOT:-results/local_runs}"
ARTIFACTS="${ARTIFACTS:-results/local_artifacts}"
RUNS="${RUNS:-3}"
SAMPLES_PER_CLASS="${SAMPLES_PER_CLASS:-120}"
REPETITIONS="${REPETITIONS:-20}"
N_GROUPS="${N_GROUPS:-20}"
WARMUP="${WARMUP:-200}"
VARIANTS="${VARIANTS:-512 768 1024}"
INVALID_STRATEGIES="${INVALID_STRATEGIES:-single_bit byte_flip random_bytes zero}"
export LOKY_MAX_CPU_COUNT="${LOKY_MAX_CPU_COUNT:-8}"
export MLKEM_PERMUTATIONS="${MLKEM_PERMUTATIONS:-20}"
export MLKEM_N_JOBS="${MLKEM_N_JOBS:-1}"
export PYTHONUNBUFFERED=1
mkdir -p "$OUTPUT_ROOT"
for run in $(seq -w 1 "$RUNS"); do
  output_dir="$OUTPUT_ROOT/run_${run}"
  echo "=== Collecting $output_dir ($(date +%H:%M:%S)) ==="
  "$PYTHON" -u -m mlkem_leakage.cli \
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
echo "=== Generating artifacts ==="
"$PYTHON" -m mlkem_leakage.paper_artifacts --input-root "$OUTPUT_ROOT" --output-dir "$ARTIFACTS"
echo "=== DONE ==="
