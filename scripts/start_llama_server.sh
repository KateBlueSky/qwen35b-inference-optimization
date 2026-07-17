#!/usr/bin/env bash
set -euo pipefail

MODEL_QUANT="${1:-Q4_K_M}"
N_GPU_LAYERS="${2:-14}"
N_CPU_MOE="${3:-16}"
CONTEXT_SIZE="${4:-24576}"
KV_TYPE_K="${5:-q4_0}"
KV_TYPE_V="${6:-q4_0}"

MODEL_REPO="bartowski/Qwen_Qwen3.6-35B-A3B-GGUF"
MODEL_ALIAS="qwen-coder"
PORT="8080"

TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RUN_NAME="${TIMESTAMP}_${MODEL_QUANT}_ngl${N_GPU_LAYERS}_cpumoe${N_CPU_MOE}_ctx${CONTEXT_SIZE}"
RESULTS_DIR="results/server-runs/${RUN_NAME}"

mkdir -p "${RESULTS_DIR}"

SERVER_COMMAND=(
    llama-server
    -hf "${MODEL_REPO}:${MODEL_QUANT}"
    --alias "${MODEL_ALIAS}"
    --fit on
    --fit-ctx "${CONTEXT_SIZE}"
    #-ngl "${N_GPU_LAYERS}"
    #-c "${CONTEXT_SIZE}"
    -ctk "${KV_TYPE_K}"
    -ctv "${KV_TYPE_V}"
    #--n-cpu-moe "${N_CPU_MOE}"
    -fa on
    --parallel 1
    --host 127.0.0.1
    --port "${PORT}"
    --jinja
    --metrics
    --no-mmap
)

printf '%q ' "${SERVER_COMMAND[@]}" > "${RESULTS_DIR}/server-command.sh"
printf '\n' >> "${RESULTS_DIR}/server-command.sh"
chmod +x "${RESULTS_DIR}/server-command.sh"

cat > "${RESULTS_DIR}/config.json" <<EOF
{
  "timestamp_utc": "${TIMESTAMP}",
  "run_name": "${RUN_NAME}",
  "model_repo": "${MODEL_REPO}",
  "model_quantization": "${MODEL_QUANT}",
  "model_alias": "${MODEL_ALIAS}",
  "gpu_layers": ${N_GPU_LAYERS},
  "cpu_moe_layers": ${N_CPU_MOE},
  "context_size": ${CONTEXT_SIZE},
  "kv_cache_type_k": "${KV_TYPE_K}",
  "kv_cache_type_v": "${KV_TYPE_V}",
  "flash_attention": true,
  "jinja": true,
  "metrics_enabled": true,
  "host": "127.0.0.1",
  "port": ${PORT}
}
EOF

{
    echo "Started: $(date --iso-8601=seconds)"
    echo
    echo "Hostname:"
    hostname
    echo
    echo "Kernel:"
    uname -a
    echo
    echo "GPU:"
    nvidia-smi
    echo
    echo "llama.cpp version:"
    llama-server --version
} > "${RESULTS_DIR}/environment.txt" 2>&1

ln -sfn "${RUN_NAME}" results/server-runs/latest

echo "Run directory: ${RESULTS_DIR}"
echo "Model alias:   ${MODEL_ALIAS}"
echo "Metrics:       http://127.0.0.1:${PORT}/metrics"
echo "Starting server..."

exec "${SERVER_COMMAND[@]}" \
    2>&1 | tee "${RESULTS_DIR}/llama-server.log"
