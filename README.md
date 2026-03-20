# NL2TAP Research

Research project for IFTTT filter code generation via Large Language Models.

## Project structure

```
├── src/
│   ├── code_parsing/       # IFTTT filter code analysis pipeline
│   │   ├── expr.py             # Expr DSL (AST, simplify, eval, aliases)
│   │   ├── js_validator.py     # JS cleaning, esprima parsing, ASTParser
│   │   ├── path_analyzer.py    # Conditional path analysis, merge/normalize
│   │   ├── catalog_validator.py# IFTTT catalog validation & display labels
│   │   ├── feedback.py         # L1 (deterministic) + L2 (LLM) validation
│   │   ├── flowchart.py        # Behavior flow visualization (HTML/CSS)
│   │   ├── agent_support.py    # Orchestrator agent, API fixes, intent diffs
│   │   ├── execution_sandbox.py# V8 execution sandbox (offline analysis only)
│   │   └── parser.py           # Backward-compat wrapper
│   ├── evaluation/         # Streamlit user study app
│   │   ├── Home.py             # Entry point, registration, language selection
│   │   └── pages/
│   │       └── 2_Studio.py     # Main study page: chat UI, generation, eval
│   ├── utils/
│   │   ├── interaction_logger.py   # JSONL structured interaction logging
│   │   ├── session_manager.py      # SQLite session persistence (WAL mode)
│   │   └── study_utils.py          # Study set loader, catalog, translations
│   ├── analysis/           # Metrics computation, embeddings, study analysis
│   └── llm_utility/        # LLM prompt templates and request utilities
├── data/
│   ├── dataset/            # Curated datasets (applets, augmentation)
│   ├── ifttt_catalog/      # IFTTT service/trigger/action catalog
│   └── test/               # Test sets for evaluation
├── notebooks/
│   ├── analysis/           # Metric analysis and embedding visualization
│   ├── augmentation/       # Data augmentation notebooks
│   ├── fine_tuning/        # Model fine-tuning notebooks
│   └── test/               # Evaluation and results notebooks
├── prototypes/             # HTML visual prototypes
├── results/                # Experiment outputs (study.db, JSONL logs)
├── models/                 # HuggingFace models (not tracked, ~41 GB)
├── pyproject.toml
└── requirements.txt
```

## Installation

```bash
# Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate   # Linux/macOS
.venv\Scripts\activate      # Windows

# Install in editable mode
pip install -e .

# Or install pinned dependencies
pip install -r requirements.txt
```

## Quick Start

### 1. Start generation model — LM Studio (port 1234)

Load `ft_2_qwen_merged` (Q4_K_M GGUF) in LM Studio. It exposes an OpenAI-compatible endpoint at `http://localhost:1234/v1`.

### 2. Start orchestrator model — vLLM (port 8001)

```bash
python -m vllm.entrypoints.openai.api_server --model "$HOME/.lmstudio/models/lmstudio-community/Qwen3-4B-Instruct-2507-GGUF/Qwen3-4B-Instruct-2507-Q8_0.gguf"   --served-model-name qwen3-4b-2507   --tokenizer Qwen/Qwen3-4B-Instruct-2507   --port 8001 --max-model-len 4096 --gpu-memory-utilization 0.45  --enable-auto-tool-choice --tool-call-parser hermes
```

### 3. Start Streamlit app

```bash
cd src/evaluation && streamlit run Home.py --server.port 8501
```

### 4. Expose via ngrok (optional, for remote participants)

Streamlit requires specific settings to work behind ngrok's reverse proxy:

```bash
# Install ngrok (if not already installed)
pip install pyngrok

# Configure your authtoken (one-time, get it from https://dashboard.ngrok.com/get-started/your-authtoken)
ngrok config add-authtoken <YOUR_TOKEN>

# Start the tunnel with host-header rewrite (required for Streamlit WebSocket)
ngrok http --host-header=localhost 8501
```

The `.streamlit/config.toml` already includes the necessary proxy settings:
```toml
[server]
enableCORS = false
enableXsrfProtection = false
headless = true
```

> **Note:** The ngrok URL changes on every restart (free tier). For a fixed subdomain, a paid ngrok plan is required.

## Serving Architecture

| Component      | Model                                    | Quantization | Server   | Port |
|----------------|------------------------------------------|--------------|----------|------|
| Code generation | ft_2_qwen_merged (SFT on Qwen2.5-Coder-7B) | Q4_K_M       | LM Studio | 1234 |
| Orchestrator   | Qwen3-4B-Instruct-2507                  | Q8_0         | vLLM     | 8001 |

## Study Design

Single-flow within-subjects design — all participants use the orchestrator with up to 3 attempts per scenario. Each participant is their own control (T1 = baseline, T2-T3 = iterative refinement).

**Participants:**
- **Expert** (E1–E6): full technical view — code, L1 validation, behavior flow, API fixes
- **Non-expert** (S1–S3 simple, C1–C3 complex): behavioral view only — behavior flow + orchestrator commentary

**Analysis pipeline** (per attempt): L1 deterministic validation → behavior flow visualization → orchestrator commentary with intent suggestions.

**Data collected:** time-on-task, turns to convergence, suggestion acceptance, behavioral match, code correctness (expert), confidence, SUS, NASA-TLX.

Data stored in `results/study.db` (SQLite, WAL mode) and `results/*.jsonl`.

## Key Libraries

- **py_mini_racer** — V8 engine for JS constant folding and sandbox execution
- **sympy** — Boolean algebra simplification for condition logic
- **esprima** — JavaScript AST parsing
- **vLLM** — Orchestrator model serving (tool calling, OpenAI-compatible API)
- **LM Studio** — Generation model serving (OpenAI-compatible API)

## Models and large data

The `models/` directory (HuggingFace checkpoints, ~41 GB) and `data/_legacy/` (455 MB) are excluded from version control via `.gitignore`. Download or generate them locally as needed.
