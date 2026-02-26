import os
import sys
from sentence_transformers import SentenceTransformer

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(BASE_DIR, "../../"))

ACTION_MODEL_PATH = os.path.join(project_root, 'models/joe32140/ModernBERT-base-msmarco/action_channel_joe32140/ModernBERT-base-msmarco_embedder')
TRIGGER_MODEL_PATH = os.path.join(project_root, 'models/joe32140/ModernBERT-base-msmarco/trigger_channel_joe32140/ModernBERT-base-msmarco_embedder')

print(f"Project Root: {project_root}")
print(f"Action Path: {ACTION_MODEL_PATH}")
print(f"Exists: {os.path.exists(ACTION_MODEL_PATH)}")

try:
    print("Loading Action Model...")
    model = SentenceTransformer(ACTION_MODEL_PATH)
    print("Success!")
except Exception as e:
    print(f"Error loading model: {e}")
