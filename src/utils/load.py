import json
from pathlib import Path
from typing import Any, Dict, List, Union, Iterable
import gzip
import torch
import numpy as np
from datasets import tqdm
from torch.utils.data import DataLoader


def _iter_lines_text(path: Path) -> Iterable[str]:
    """
    Iteratore di righe in testo (supporta anche .gz).
    """
    if path.suffix == ".gz":
        # .jsonl.gz -> apriamo in gzip text mode
        with gzip.open(path, mode="rt", encoding="utf-8") as f:
            for line in f:
                yield line
    else:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                yield line


def load_json_or_jsonl(path: Union[str, Path]) -> List[Dict[str, Any]]:
    """
    Carica un file JSON o JSONL e restituisce sempre una lista di dict.

    - Se il file è .json: ci aspettiamo o una lista di oggetti o un singolo oggetto.
      * Se è una lista -> la ritorniamo così.
      * Se è un dict    -> ritorniamo [dict].
    - Se il file è .jsonl (o .jsonl.gz): ogni riga non vuota viene parse-ata come JSON
      e aggiunta alla lista.

    Esempio d'uso:
        triggers = load_json_or_jsonl("data/ifttt_catalog/triggers.json")
        actions  = load_json_or_jsonl("data/ifttt_catalog/actions.jsonl")
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"File not found: {p}")

    name_lower = p.name.lower()

    # Caso 1: JSONL / JSONLINES (anche gz)
    if name_lower.endswith(".jsonl") or name_lower.endswith(".jsonl.gz"):
        items: List[Dict[str, Any]] = []
        for line in _iter_lines_text(p):
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            if isinstance(obj, dict):
                items.append(obj)
            else:
                # se è qualcosa di strano (lista, stringa, ecc.), lo impacchettiamo
                items.append({"value": obj})
        return items

    # Caso 2: JSON "normale"
    if name_lower.endswith(".json") or name_lower.endswith(".json.gz"):
        if p.suffix == ".gz":
            with gzip.open(p, mode="rt", encoding="utf-8") as f:
                obj = json.load(f)
        else:
            with p.open("r", encoding="utf-8") as f:
                obj = json.load(f)

        if isinstance(obj, list):
            # assumiamo lista di dict
            return obj
        elif isinstance(obj, dict):
            # un singolo oggetto -> lo mettiamo in una lista
            return [obj]
        else:
            # fallback paranoico
            return [{"value": obj}]

    # Caso 3: estensione non riconosciuta -> proviamo a sniffare
    with p.open("r", encoding="utf-8") as f:
        first_chars = f.read(1024)
        f.seek(0)
        first_non_ws = next((c for c in first_chars if not c.isspace()), "")

        if first_non_ws in ("{", "["):
            # sembra JSON "normale"
            obj = json.load(f)
            if isinstance(obj, list):
                return obj
            elif isinstance(obj, dict):
                return [obj]
            return [{"value": obj}]
        else:
            # proviamo a trattarlo come JSONL
            items: List[Dict[str, Any]] = []
            f.seek(0)
            for line in f:
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                if isinstance(obj, dict):
                    items.append(obj)
                else:
                    items.append({"value": obj})
            return items


def generate_outputs(model, dataset, batch_size=16, max_new_tokens=340):
    loader = DataLoader(dataset, batch_size=batch_size)
    all_preds = []
    all_labels = []

    model.eval()
    for batch in tqdm(loader):
        input_ids = batch["input_ids"].to(model.device)
        attention_mask = batch["attention_mask"].to(model.device)
        labels = batch["labels"].numpy()

        with torch.no_grad():
            outputs = model.generate(
                input_ids=input_ids,
                attention_mask=attention_mask,
                max_new_tokens=max_new_tokens,
                do_sample=False
            )

        # mettiamo in shape compatibile con compute_metrics
        preds = outputs.cpu().numpy()[:, input_ids.shape[1]:]
        all_preds.append(preds)
        all_labels.append(labels)

    all_preds = np.concatenate(all_preds, axis=0)
    all_labels = np.concatenate(all_labels, axis=0)
    return all_preds, all_labels

