# NL2TAP Research

Research project for IFTTT filter code generation via Large Language Models.

## Project structure

```
├── src/                    # Source code
│   ├── analysis/           # Metrics computation, embeddings, user study analysis
│   ├── code_parsing/       # IFTTT filter code parser
│   ├── evaluation/         # Streamlit evaluation app (user study)
│   ├── llm_utility/        # LLM prompt templates and request utilities
│   └── utils/              # Data loading, i18n, study helpers
├── data/
│   ├── dataset/            # Curated datasets (applets, augmentation)
│   ├── ifttt_catalog/      # IFTTT service/trigger/action catalog
│   └── test/               # Test sets for evaluation
├── notebooks/
│   ├── analysis/           # Metric analysis and embedding visualization
│   ├── augmentation/       # Data augmentation notebooks
│   ├── fine_tuning/        # Model fine-tuning notebooks
│   └── test/               # Evaluation and results notebooks
├── results/                # Experiment outputs (user study results)
├── models/                 # HuggingFace models (not tracked, ~41 GB)
├── pyproject.toml
└── requirements.txt        # Pinned dependencies
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

## Models and large data

The `models/` directory (HuggingFace checkpoints, ~41 GB) and `data/_legacy/` (455 MB) are excluded from version control via `.gitignore`. Download or generate them locally as needed.
