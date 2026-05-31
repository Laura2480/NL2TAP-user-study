"""
Fine-tuning script for NL2TAP filter code generation.

Reproduces the fine-tuning procedure described in Section 5.1 of the paper.

Models:
    - CodeLlama-7B-Instruct
    - Codestral-7B (Mamba2)
    - DeepSeek-Coder-6.7B-Instruct
    - Qwen2.5-Coder-7B-Instruct

Hyperparameters (Section 5.1):
    LoRA rank=16, alpha=32, dropout=0.05
    5 epochs, AdamW, lr=2e-4, cosine scheduling, warmup 3%
    Batch size 4, gradient accumulation 1, max seq 1536

Two training configurations:
    FT-NI:          intent only (no catalog grounding)
    FT-NI+Catalog:  intent + platform catalog (trigger/action descriptions)

Usage:
    # Single model, single seed
    python scripts/fine_tune.py --model qwen --seed 42 --variant FT-NI

    # All models, all seeds, both variants (full reproduction)
    python scripts/fine_tune.py --all-models --all-seeds --all-variants

Requires: torch, transformers, peft, trl, datasets, pandas
"""

import argparse
import gc
import json
import os
import random
import re
import sys
import time

import numpy as np
import pandas as pd
import torch
from datasets import Dataset
from peft import LoraConfig
from transformers import AutoModelForCausalLM, AutoTokenizer
from trl import SFTConfig, SFTTrainer

# ── Model registry ────────────────────────────────────────────────────────────

MODELS = {
    "deepseek":  "deepseek-ai/deepseek-coder-6.7b-instruct",
    "codestral": "mistralai/Mamba-Codestral-7B-v0.1",
    "qwen":      "Qwen/Qwen2.5-Coder-7B-Instruct",
    "codellama": "codellama/CodeLlama-7b-Instruct-hf",
}

LORA_TARGETS = {
    "deepseek":  ["q_proj", "k_proj", "v_proj", "o_proj"],
    "codestral": ["x_proj", "in_proj", "embeddings"],
    "qwen":      ["q_proj", "k_proj", "v_proj", "o_proj"],
    "codellama": ["q_proj", "k_proj", "v_proj", "o_proj"],
}

# ── Paper hyperparameters (Section 5.1) ───────────────────────────────────────

LORA_RANK    = 16
LORA_ALPHA   = 32
LORA_DROPOUT = 0.05
NUM_EPOCHS   = 5
LR           = 2e-4
WARMUP_RATIO = 0.03
MAX_GRAD_NORM = 0.3
BATCH_SIZE   = 4
GRAD_ACCUM   = 1
MAX_SEQ      = 1536
EVAL_RATIO   = 0.1
SEEDS        = [42, 123, 456, 789, 1024]
SEPARATOR    = "<|INST|>"

# ── Prompt builders ───────────────────────────────────────────────────────────

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")


def _load_catalogs():
    """Load IFTTT trigger/action catalogs, indexed by api_endpoint_slug."""
    with open(os.path.join(DATA_DIR, "triggers.json"), encoding="utf-8") as f:
        triggers_list = json.load(f)
    with open(os.path.join(DATA_DIR, "actions.json"), encoding="utf-8") as f:
        actions_list = json.load(f)
    triggers = {t["api_endpoint_slug"]: t for t in triggers_list if "api_endpoint_slug" in t}
    actions = {a["api_endpoint_slug"]: a for a in actions_list if "api_endpoint_slug" in a}
    return triggers, actions


def _build_catalog_block(row, triggers, actions):
    """Build the catalog grounding section for a single rule."""
    parts = []

    # Trigger ingredients
    for tkey in row.get("trigger_apis", []):
        tdef = triggers.get(tkey, {})
        for ing in tdef.get("ingredients", []):
            key = ing.get("filter_code_key")
            if not key:
                continue
            desc = ing.get("description", "")
            dtype = ing.get("dtype", "")
            line = f"- JS accessor: `{key}`"
            if dtype:
                line += f" | type: {dtype}"
            if desc:
                line += f" | description: {desc}"
            parts.append(line)

    # Action setters and skip methods
    for akey in row.get("action_apis", []):
        adef = actions.get(akey, {})
        for fld in adef.get("fields", []):
            method = fld.get("filter_code_method")
            if not method:
                continue
            helper = fld.get("helper_text") or fld.get("label", "")
            parts.append(f"- JS method: `{method}` | helper: {helper}")
        sk = adef.get("skip_method")
        if sk:
            parts.append(f"- Skip: `{sk}`")

    return "\n".join(parts)


HEADER = (
    "You are an expert JavaScript developer with specialized knowledge of "
    "filter code for trigger-action rules.\n"
    "A trigger-action rule defines an automation in which one or more trigger "
    "events, possibly combined through logical operators (AND, OR), lead to "
    "the execution of one or more actions.\n"
    "Filter code refines such rules by specifying when actions should be "
    "executed versus suppressed, and how action parameters should be computed.\n"
)


def build_prompt_ft_ni(row):
    """FT-NI: intent only, no catalog."""
    intent = row.get("user_intent_example", "")
    return (
        HEADER +
        f"\nYour task is to produce JavaScript filter code for the following intent:\n"
        f"{intent}\n\n"
        "Write ONLY the JavaScript Filter Code.\n"
    )


def build_prompt_ft_ni_catalog(row, triggers, actions):
    """FT-NI+Catalog: intent + platform catalog grounding."""
    intent = row.get("user_intent_example", "")
    rule_desc = row.get("rule_description", "")
    catalog = _build_catalog_block(row, triggers, actions)
    return (
        HEADER +
        f"\nYour task is to produce JavaScript filter code for the following intent:\n"
        f"{intent}\n\n"
        f"Rule description:\n{rule_desc}\n\n"
        f"Available platform elements:\n{catalog}\n\n"
        "Write ONLY the JavaScript Filter Code.\n"
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def set_seed(seed):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    os.environ["PYTHONHASHSEED"] = str(seed)


def prepare_dataset(train_data, variant, seed, triggers=None, actions=None):
    """Build text column (prompt + separator + target) and split train/eval."""
    records = []
    for row in train_data:
        if variant == "FT-NI":
            prompt = build_prompt_ft_ni(row)
        else:
            prompt = build_prompt_ft_ni_catalog(row, triggers, actions)
        text = prompt + SEPARATOR + (row.get("filter_code") or "")
        records.append({"text": text})

    random.seed(seed)
    random.shuffle(records)

    n_eval = max(1, int(len(records) * EVAL_RATIO))
    train_ds = Dataset.from_list(records[n_eval:])
    eval_ds = Dataset.from_list(records[:n_eval])

    print(f"  Split: {len(train_ds)} train, {len(eval_ds)} eval (seed={seed})")
    return train_ds, eval_ds


# ── Training ──────────────────────────────────────────────────────────────────

def train_single(model_key, seed, variant, train_data, output_base,
                 num_epochs=NUM_EPOCHS, triggers=None, actions=None):
    set_seed(seed)

    model_id = MODELS[model_key]
    output_dir = os.path.join(
        output_base,
        f"{model_key}_{variant.replace('+', '_')}_{seed}"
    )

    # Skip if already done
    if os.path.exists(os.path.join(output_dir, "training_metadata.json")):
        print(f"\n[SKIP] Already trained: {output_dir}")
        return output_dir

    print(f"\n{'='*70}")
    print(f"Training: {model_key} | {variant} | seed={seed} | epochs={num_epochs}")
    print(f"  Model: {model_id}")
    print(f"  LoRA: r={LORA_RANK}, alpha={LORA_ALPHA}, dropout={LORA_DROPOUT}")
    print(f"{'='*70}\n")

    t0 = time.time()

    # Compute dtype
    if torch.cuda.is_available() and torch.cuda.get_device_capability()[0] >= 8:
        compute_dtype = torch.bfloat16
    else:
        compute_dtype = torch.float16

    # Tokenizer
    tokenizer = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True)
    tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "right"

    # Model (16-bit, as described in the paper)
    model = AutoModelForCausalLM.from_pretrained(
        model_id, trust_remote_code=True,
        device_map={"": 0}, torch_dtype=compute_dtype,
    )
    model.config.use_cache = False

    # LoRA
    lora_config = LoraConfig(
        r=LORA_RANK, lora_alpha=LORA_ALPHA, lora_dropout=LORA_DROPOUT,
        bias="none", task_type="CAUSAL_LM",
        target_modules=LORA_TARGETS[model_key],
    )

    # Dataset
    train_ds, eval_ds = prepare_dataset(
        train_data, variant, seed, triggers, actions
    )

    # SFT config
    sft_config = SFTConfig(
        output_dir=output_dir,
        num_train_epochs=num_epochs,
        per_device_train_batch_size=BATCH_SIZE,
        per_device_eval_batch_size=BATCH_SIZE,
        gradient_accumulation_steps=GRAD_ACCUM,
        learning_rate=LR,
        warmup_ratio=WARMUP_RATIO,
        lr_scheduler_type="cosine",
        max_grad_norm=MAX_GRAD_NORM,
        logging_steps=10,
        eval_strategy="epoch",
        save_strategy="epoch",
        save_total_limit=1,
        load_best_model_at_end=True,
        metric_for_best_model="eval_loss",
        greater_is_better=False,
        fp16=(compute_dtype == torch.float16),
        bf16=(compute_dtype == torch.bfloat16),
        gradient_checkpointing=True,
        gradient_checkpointing_kwargs={"use_reentrant": False},
        report_to="none",
        seed=seed, data_seed=seed,
        dataset_text_field="text",
        max_length=MAX_SEQ, packing=False,
    )

    trainer = SFTTrainer(
        model=model, train_dataset=train_ds, eval_dataset=eval_ds,
        args=sft_config, peft_config=lora_config, processing_class=tokenizer,
    )

    train_result = trainer.train()
    eval_result = trainer.evaluate()

    # Save adapter
    adapter_dir = os.path.join(output_dir, "adapter")
    os.makedirs(adapter_dir, exist_ok=True)
    trainer.model.save_pretrained(adapter_dir)
    tokenizer.save_pretrained(adapter_dir)

    total_time = time.time() - t0

    # Save metadata
    metadata = {
        "model_id": model_id, "model_key": model_key,
        "variant": variant, "seed": seed,
        "lora_rank": LORA_RANK, "lora_alpha": LORA_ALPHA,
        "lora_dropout": LORA_DROPOUT, "num_epochs": num_epochs,
        "learning_rate": LR, "batch_size": BATCH_SIZE,
        "max_seq_length": MAX_SEQ,
        "train_samples": len(train_ds), "eval_samples": len(eval_ds),
        "train_loss": train_result.metrics.get("train_loss"),
        "eval_loss": eval_result.get("eval_loss"),
        "total_runtime_seconds": total_time,
    }
    with open(os.path.join(output_dir, "training_metadata.json"), "w") as f:
        json.dump(metadata, f, indent=2)

    print(f"  Train loss: {metadata['train_loss']:.4f}")
    print(f"  Eval loss:  {metadata['eval_loss']:.4f}")
    print(f"  Time: {total_time/60:.1f} min")

    # Cleanup
    del trainer, model
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    return output_dir


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Fine-tuning for NL2TAP (replication)")
    parser.add_argument("--model", choices=list(MODELS.keys()), nargs="+")
    parser.add_argument("--all-models", action="store_true")
    parser.add_argument("--seed", type=int, nargs="+")
    parser.add_argument("--all-seeds", action="store_true")
    parser.add_argument("--variant", choices=["FT-NI", "FT-NI+Catalog"])
    parser.add_argument("--all-variants", action="store_true")
    parser.add_argument("--epochs", type=int, default=NUM_EPOCHS)
    parser.add_argument("--output", default="models/", help="Output directory")
    args = parser.parse_args()

    models = list(MODELS.keys()) if args.all_models else (args.model or [])
    seeds = SEEDS if args.all_seeds else (args.seed or [])
    variants = ["FT-NI", "FT-NI+Catalog"] if args.all_variants else ([args.variant] if args.variant else [])

    if not models or not seeds or not variants:
        parser.error("Specify --model/--all-models, --seed/--all-seeds, --variant/--all-variants")

    # Load training data from replication package
    train_path = os.path.join(DATA_DIR, "dataset_train.json")
    with open(train_path, encoding="utf-8") as f:
        train_data = json.load(f)
    print(f"Loaded {len(train_data)} training samples from {train_path}")

    # Load catalogs (needed for FT-NI+Catalog)
    triggers, actions = _load_catalogs()

    os.makedirs(args.output, exist_ok=True)

    runs = [(m, s, v) for m in models for v in variants for s in seeds]
    print(f"Planned: {len(runs)} runs ({models} x {variants} x {seeds})\n")

    for model_key, seed, variant in runs:
        train_single(
            model_key, seed, variant, train_data, args.output,
            num_epochs=args.epochs,
            triggers=triggers, actions=actions,
        )

    print(f"\nAll {len(runs)} runs complete!")


if __name__ == "__main__":
    main()
