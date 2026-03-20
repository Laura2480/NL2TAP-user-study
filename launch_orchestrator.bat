@echo off
REM Launch vLLM orchestrator with MSVC environment on GPU 1

call "C:\Program Files\Microsoft Visual Studio\18\Community\VC\Auxiliary\Build\vcvars64.bat"

set CUDA_VISIBLE_DEVICES=1

python -m vllm.entrypoints.openai.api_server ^
  --model "%USERPROFILE%/.lmstudio/models/lmstudio-community/Qwen3-4B-Instruct-2507-GGUF/Qwen3-4B-Instruct-2507-Q8_0.gguf" ^
  --served-model-name qwen3-4b-2507 ^
  --tokenizer Qwen/Qwen3-4B-Instruct-2507 ^
  --port 8001 --max-model-len 4096 --gpu-memory-utilization 0.45 ^
  --quantization gguf ^
  --enable-auto-tool-choice --tool-call-parser hermes
