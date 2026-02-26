"""
CodeBERT Embeddings for IFTTT Filter Code

Computes embeddings for applet filter code using CodeBERT.
Used for:
1. Semantic clustering of code
2. Code-to-Code similarity
3. Analyzing code distribution
"""

import json
import os
import sys
import numpy as np
import torch
from transformers import AutoTokenizer, AutoModel
from sklearn.cluster import KMeans
from sklearn.manifold import TSNE
import matplotlib.pyplot as plt
import seaborn as sns

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "../../data/reports/code_embeddings")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Load model
print("Loading CodeBERT model...")
tokenizer = AutoTokenizer.from_pretrained("microsoft/codebert-base")
model = AutoModel.from_pretrained("microsoft/codebert-base")

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
model.to(device)
print(f"Using device: {device}")

def load_data():
    """Load applets"""
    with open(os.path.join(BASE_DIR, "../../data/ifttt_catalog/applets_real_clean.json"), 'r', encoding='utf-8') as f:
        real_applets = json.load(f)
    
    with open(os.path.join(BASE_DIR, "../../data/test/applets_13k_gpt_final.json"), 'r', encoding='utf-8') as f:
        synth_applets = json.load(f)
    
    # Filter synthetic (must have code)
    synth_filtered = [a for a in synth_applets 
                     if a.get('filter_code') and a.get('filter_code').strip() != ''
                     and a.get('tapir_score', 0) > 0.99]
    
    # Filter real (must have code)
    real_filtered = [a for a in real_applets 
                    if a.get('filter_code') and a.get('filter_code').strip() != '']
    
    return real_filtered, synth_filtered

def compute_code_embeddings(applets, batch_size=32):
    """Compute CodeBERT embeddings for applet code"""
    print(f"Computing embeddings for {len(applets)} applets...")
    
    embeddings = []
    
    for i in range(0, len(applets), batch_size):
        batch = applets[i:i+batch_size]
        codes = [a['filter_code'] for a in batch]
        
        # Tokenize
        inputs = tokenizer(codes, return_tensors="pt", padding=True, truncation=True, max_length=512)
        inputs = {k: v.to(device) for k, v in inputs.items()}
        
        with torch.no_grad():
            outputs = model(**inputs)
            # Use CLS token embedding (index 0)
            batch_embeddings = outputs.last_hidden_state[:, 0, :].cpu().numpy()
            embeddings.append(batch_embeddings)
        
        if (i + batch_size) % 100 == 0:
            print(f"Processed {i + batch_size}/{len(applets)}")
            
    return np.vstack(embeddings)

def visualize_code_space(real_emb, synth_emb):
    """Visualize code embedding space"""
    print("\nVisualizing code space...")
    
    # Combine for t-SNE
    X = np.vstack([real_emb, synth_emb])
    labels = ['Real'] * len(real_emb) + ['Synthetic'] * len(synth_emb)
    
    # t-SNE
    tsne = TSNE(n_components=2, random_state=42, perplexity=min(30, len(X)-1))
    X_2d = tsne.fit_transform(X)
    
    plt.figure(figsize=(10, 8))
    
    # Plot Synthetic first (background)
    mask_synth = [l == 'Synthetic' for l in labels]
    plt.scatter(X_2d[mask_synth, 0], X_2d[mask_synth, 1], 
               c='coral', marker='^', label='Synthetic', 
               alpha=0.5, s=30, edgecolors='none')
    
    # Plot Real (foreground)
    mask_real = [l == 'Real' for l in labels]
    plt.scatter(X_2d[mask_real, 0], X_2d[mask_real, 1], 
               c='steelblue', marker='o', label='Real', 
               alpha=0.8, s=50, edgecolors='black', linewidth=0.5)
    
    plt.title('CodeBERT Space: Real vs Synthetic Code', fontweight='bold', fontsize=14)
    plt.xlabel('t-SNE 1')
    plt.ylabel('t-SNE 2')
    plt.legend()
    
    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, 'code_space.png'), dpi=300)
    print("Saved: code_space.png")
    plt.close()

def main():
    print("="*70)
    print("CODEBERT EMBEDDING ANALYSIS")
    print("="*70)
    
    # Load data
    print("\nLoading data...")
    real_applets, synth_applets = load_data()
    
    print(f"Real applets with code: {len(real_applets)}")
    print(f"Synthetic applets with code: {len(synth_applets)}")
    
    # Sample synthetic if too many (optional, but good for speed)
    # synth_applets = synth_applets[:2000] 
    
    # Compute embeddings
    print("\nComputing Real embeddings...")
    real_emb = compute_code_embeddings(real_applets)
    
    print("\nComputing Synthetic embeddings...")
    synth_emb = compute_code_embeddings(synth_applets)
    
    # Visualize
    visualize_code_space(real_emb, synth_emb)
    
    # Save embeddings (optional, can be large)
    # np.save(os.path.join(OUTPUT_DIR, 'real_embeddings.npy'), real_emb)
    # np.save(os.path.join(OUTPUT_DIR, 'synth_embeddings.npy'), synth_emb)
    
    print(f"\n{'='*70}")
    print(f"COMPLETE! Results saved to: {OUTPUT_DIR}")
    print(f"{'='*70}")

if __name__ == "__main__":
    main()
