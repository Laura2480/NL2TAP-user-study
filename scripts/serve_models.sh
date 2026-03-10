#!/usr/bin/env bash
# ==============================================================
# vLLM dual-model serving for user study
# GPU 0: ft_2_qwen_merged (Q4_K_M) — code generation
# GPU 1: Qwen3-4B-Instruct-2507 (Q8_0) — orchestrator
# ==============================================================

set -euo pipefail

LMSTUDIO_MODELS="$HOME/.lmstudio/models"

GEN_MODEL="$LMSTUDIO_MODELS/LDES777/ft_2_qwen_merged-Q4_K_M-GGUF/ft_2_qwen_merged-q4_k_m.gguf"
ORC_MODEL="$LMSTUDIO_MODELS/lmstudio-community/Qwen3-4B-Instruct-2507-GGUF/Qwen3-4B-Instruct-2507-Q8_0.gguf"

echo "=== Starting vLLM model servers ==="
echo "  GEN: $GEN_MODEL"
echo "  ORC: $ORC_MODEL"

# --- Generation model — GPU 0, port 8001 ---
CUDA_VISIBLE_DEVICES=0 python -m vllm.entrypoints.openai.api_server \
  --model "$GEN_MODEL" \
  --served-model-name ft_2_qwen_merged \
  --tokenizer Qwen/Qwen2.5-Coder-7B \
  --port 8001 \
  --host 0.0.0.0 \
  --max-model-len 2048 \
  --gpu-memory-utilization 0.85 \
  --max-num-seqs 32 \
  --dtype auto \
  --enforce-eager \
  --disable-log-requests \
  &
GEN_PID=$!
echo "[GEN] PID=$GEN_PID — GPU 0, port 8001"

# --- Orchestrator model — GPU 1, port 8002 ---
CUDA_VISIBLE_DEVICES=1 python -m vllm.entrypoints.openai.api_server \
  --model "$ORC_MODEL" \
  --served-model-name qwen3-4b-2507 \
  --tokenizer Qwen/Qwen3-4B-Instruct-2507 \
  --port 8002 \
  --host 0.0.0.0 \
  --max-model-len 8192 \
  --gpu-memory-utilization 0.85 \
  --max-num-seqs 16 \
  --dtype auto \
  --enforce-eager \
  --enable-auto-tool-choice \
  --tool-call-parser hermes \
  --disable-log-requests \
  &
ORC_PID=$!
echo "[ORC] PID=$ORC_PID — GPU 1, port 8002"

# --- Wait for readiness ---
echo ""
echo "Waiting for models to load..."
for port in 8001 8002; do
  until curl -s "http://localhost:$port/health" > /dev/null 2>&1; do
    sleep 2
  done
  echo "  port $port ready"
done

echo ""
echo "=== Both models serving ==="
echo "  Generation:   http://localhost:8001/v1/chat/completions  (ft_2_qwen_merged)"
echo "  Orchestrator: http://localhost:8002/v1/chat/completions  (qwen3-4b-2507)"
echo ""
echo "Press Ctrl+C to stop both"

trap "kill $GEN_PID $ORC_PID 2>/dev/null; exit 0" SIGINT SIGTERM
wait
