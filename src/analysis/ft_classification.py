"""
F/T Function Classification using Embeddings

Classify and cluster:
- F functions: Skip condition guards (boolean expressions)
- T functions: State transformations (setter assignments)

Using embeddings of their natural language representations.
"""

import json
import os
import sys
import numpy as np
from collections import Counter, defaultdict
from sentence_transformers import SentenceTransformer
from sklearn.cluster import KMeans
from sklearn.manifold import TSNE
import matplotlib.pyplot as plt
import seaborn as sns

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "../../data/reports/ft_classification")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Load embedding model
print("Loading embedding model...")
model = SentenceTransformer('all-MiniLM-L6-v2')

def load_semantics():
    """Load semantic analysis results"""
    with open(os.path.join(BASE_DIR, "../../data/reports/real_applets_semantics.json"), 'r', encoding='utf-8') as f:
        real_sem = json.load(f)
    
    with open(os.path.join(BASE_DIR, "../../data/reports/synthetic_filtered_semantics.json"), 'r', encoding='utf-8') as f:
        synth_sem = json.load(f)
    
    return real_sem, synth_sem

def extract_f_functions(semantics_data, dataset_name):
    """Extract F functions (skip conditions) with their NL representations"""
    f_functions = []
    
    for result in semantics_data['results']:
        if 'error' in result:
            continue
        
        applet_id = result['applet_id']
        semantics = result.get('semantics', {})
        
        # Get skip conditions from outcomes
        for outcome in semantics.get('outcomes', []):
            effect = outcome.get('effect', {})
            
            # Only SKIP effects have F functions
            if effect.get('type') == 'SKIP':
                condition = outcome.get('condition', {})
                
                # Check if condition is a dict
                if not isinstance(condition, dict):
                    continue
                
                # Get _legacy expression (the F function)
                raw_expr = condition.get('raw_expr', '')
                
                if raw_expr:
                    f_functions.append({
                        'applet_id': applet_id,
                        'dataset': dataset_name,
                        'type': 'F',
                        'text': raw_expr,
                        'function_type': 'skip_condition',
                        'condition_form': condition.get('form', 'UNKNOWN')
                    })
    
    return f_functions

def extract_t_functions(semantics_data, dataset_name):
    """Extract T functions (transformations) with their NL representations"""
    t_functions = []
    
    for result in semantics_data['results']:
        if 'error' in result:
            continue
        
        applet_id = result['applet_id']
        model_summary = result.get('model_summary', {})
        
        # Get transformations
        transformations = model_summary.get('transformations', [])
        
        for transform in transformations:
            action = transform.get('action', '')
            field = transform.get('field', '')
            value = transform.get('value', '')
            
            # Create NL representation
            text = f"set {field} to {value}"
            
            t_functions.append({
                'applet_id': applet_id,
                'dataset': dataset_name,
                'type': 'T',
                'text': text,
                'action': action,
                'field': field,
                'value': value,
                'function_type': 'transformation'
            })
    
    return t_functions

def compute_embeddings(functions):
    """Compute embeddings for F/T function texts"""
    print(f"Computing embeddings for {len(functions)} functions...")
    
    texts = [f['text'] for f in functions]
    embeddings = model.encode(texts, show_progress_bar=True)
    
    for i, func in enumerate(functions):
        func['embedding'] = embeddings[i]
    
    return functions

def cluster_functions(functions, n_clusters=10):
    """Cluster functions by semantic similarity"""
    print(f"\nClustering {len(functions)} functions into {n_clusters} clusters...")
    
    embeddings = np.array([f['embedding'] for f in functions])
    
    kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    labels = kmeans.fit_predict(embeddings)
    
    for i, func in enumerate(functions):
        func['cluster'] = int(labels[i])
    
    return functions

def analyze_clusters(functions):
    """Analyze cluster composition"""
    cluster_info = defaultdict(lambda: {
        'real': 0,
        'synthetic': 0,
        'examples': []
    })
    
    for func in functions:
        cluster_id = func['cluster']
        
        if func['dataset'] == 'Real':
            cluster_info[cluster_id]['real'] += 1
        else:
            cluster_info[cluster_id]['synthetic'] += 1
        
        if len(cluster_info[cluster_id]['examples']) < 5:
            cluster_info[cluster_id]['examples'].append(func['text'])
    
    return dict(cluster_info)

def visualize_ft_space(f_functions, t_functions):
    """Visualize F and T function spaces"""
    print("\nVisualizing F/T function spaces...")
    
    fig, axes = plt.subplots(1, 2, figsize=(16, 6))
    
    # F functions
    if f_functions:
        f_embeddings = np.array([f['embedding'] for f in f_functions])
        tsne = TSNE(n_components=2, random_state=42, perplexity=min(30, len(f_embeddings)-1))
        f_2d = tsne.fit_transform(f_embeddings)
        
        for dataset in ['Real', 'Synthetic']:
            mask = [f['dataset'] == dataset for f in f_functions]
            color = 'steelblue' if dataset == 'Real' else 'coral'
            marker = 'o' if dataset == 'Real' else '^'
            axes[0].scatter(f_2d[mask, 0], f_2d[mask, 1],
                           c=color, marker=marker, label=dataset,
                           alpha=0.6, s=50, edgecolors='black', linewidth=0.5)
        
        axes[0].set_title('F Functions (Skip Conditions)', fontweight='bold', fontsize=14)
        axes[0].set_xlabel('t-SNE 1')
        axes[0].set_ylabel('t-SNE 2')
        axes[0].legend()
    
    # T functions
    if t_functions:
        t_embeddings = np.array([t['embedding'] for t in t_functions])
        tsne = TSNE(n_components=2, random_state=42, perplexity=min(30, len(t_embeddings)-1))
        t_2d = tsne.fit_transform(t_embeddings)
        
        for dataset in ['Real', 'Synthetic']:
            mask = [t['dataset'] == dataset for t in t_functions]
            color = 'seagreen' if dataset == 'Real' else 'mediumpurple'
            marker = 's' if dataset == 'Real' else 'D'
            axes[1].scatter(t_2d[mask, 0], t_2d[mask, 1],
                           c=color, marker=marker, label=dataset,
                           alpha=0.6, s=50, edgecolors='black', linewidth=0.5)
        
        axes[1].set_title('T Functions (Transformations)', fontweight='bold', fontsize=14)
        axes[1].set_xlabel('t-SNE 1')
        axes[1].set_ylabel('t-SNE 2')
        axes[1].legend()
    
    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, 'ft_function_space.png'), dpi=300, bbox_inches='tight')
    print("Saved: ft_function_space.png")
    plt.close()

def generate_report(f_functions, t_functions, f_clusters, t_clusters):
    """Generate F/T classification report"""
    
    f_real = len([f for f in f_functions if f['dataset'] == 'Real'])
    f_synth = len([f for f in f_functions if f['dataset'] == 'Synthetic'])
    
    t_real = len([t for t in t_functions if t['dataset'] == 'Real'])
    t_synth = len([t for t in t_functions if t['dataset'] == 'Synthetic'])
    
    report = f"""# F/T Function Classification Report

## Overview

This analysis classifies and clusters:
- **F functions**: Skip condition guards (boolean expressions in pseudo-NL)
- **T functions**: State transformations (setter assignments in pseudo-NL)

Using semantic embeddings to identify patterns and test generalization.

## F Functions (Skip Conditions)

**Total**: {len(f_functions)} functions
- Real: {f_real}
- Synthetic: {f_synth}

**Clusters**: {len(f_clusters)}

### Top F Function Clusters

"""
    
    for cluster_id in sorted(f_clusters.keys())[:5]:
        info = f_clusters[cluster_id]
        total = info['real'] + info['synthetic']
        
        report += f"""#### F Cluster {cluster_id}
- **Size**: {total} ({info['real']} Real, {info['synthetic']} Synthetic)
- **Examples**:
{chr(10).join([f'  - {ex}' for ex in info['examples'][:3]])}

"""
    
    report += f"""## T Functions (Transformations)

**Total**: {len(t_functions)} functions
- Real: {t_real}
- Synthetic: {t_synth}

**Clusters**: {len(t_clusters)}

### Top T Function Clusters

"""
    
    for cluster_id in sorted(t_clusters.keys())[:5]:
        info = t_clusters[cluster_id]
        total = info['real'] + info['synthetic']
        
        report += f"""#### T Cluster {cluster_id}
- **Size**: {total} ({info['real']} Real, {info['synthetic']} Synthetic)
- **Examples**:
{chr(10).join([f'  - {ex}' for ex in info['examples'][:3]])}

"""
    
    report += f"""## Generalization Implications

### F Function Coverage
- Real F functions span {len(set(f['cluster'] for f in f_functions if f['dataset'] == 'Real'))} clusters
- Synthetic F functions span {len(set(f['cluster'] for f in f_functions if f['dataset'] == 'Synthetic'))} clusters

### T Function Coverage
- Real T functions span {len(set(t['cluster'] for t in t_functions if t['dataset'] == 'Real'))} clusters
- Synthetic T functions span {len(set(t['cluster'] for t in t_functions if t['dataset'] == 'Synthetic'))} clusters

## Usage for NL→Code Task

These F/T embeddings can be used to:
1. **Identify semantic patterns** in conditions and transformations
2. **Create balanced splits** covering diverse F/T function types
3. **Test generalization** to unseen F/T patterns
4. **Guide code generation** by retrieving similar F/T examples

## Files Generated

- `ft_function_space.png`: Visualization of F and T function spaces
- `ft_functions.json`: All F/T functions with embeddings
- `ft_classification_report.md`: This report
"""
    
    return report

def main():
    print("="*70)
    print("F/T FUNCTION CLASSIFICATION")
    print("="*70)
    
    # Load semantics
    print("\nLoading semantic analysis results...")
    real_sem, synth_sem = load_semantics()
    
    # Extract F functions
    print("\nExtracting F functions (skip conditions)...")
    f_real = extract_f_functions(real_sem, 'Real')
    f_synth = extract_f_functions(synth_sem, 'Synthetic')
    f_functions = f_real + f_synth
    
    print(f"F functions: {len(f_functions)} ({len(f_real)} Real, {len(f_synth)} Synthetic)")
    
    # Extract T functions
    print("\nExtracting T functions (transformations)...")
    t_real = extract_t_functions(real_sem, 'Real')
    t_synth = extract_t_functions(synth_sem, 'Synthetic')
    t_functions = t_real + t_synth
    
    print(f"T functions: {len(t_functions)} ({len(t_real)} Real, {len(t_synth)} Synthetic)")
    
    # Compute embeddings
    if f_functions:
        f_functions = compute_embeddings(f_functions)
        f_functions = cluster_functions(f_functions, n_clusters=min(10, len(f_functions)))
        f_clusters = analyze_clusters(f_functions)
    else:
        f_clusters = {}
    
    if t_functions:
        t_functions = compute_embeddings(t_functions)
        t_functions = cluster_functions(t_functions, n_clusters=min(10, len(t_functions)))
        t_clusters = analyze_clusters(t_functions)
    else:
        t_clusters = {}
    
    # Visualize
    visualize_ft_space(f_functions, t_functions)
    
    # Generate report
    print("\nGenerating report...")
    report = generate_report(f_functions, t_functions, f_clusters, t_clusters)
    
    with open(os.path.join(OUTPUT_DIR, 'ft_classification_report.md'), 'w', encoding='utf-8') as f:
        f.write(report)
    
    # Save F/T functions
    ft_data = {
        'f_functions': [
            {k: v for k, v in f.items() if k != 'embedding'}
            for f in f_functions
        ],
        't_functions': [
            {k: v for k, v in t.items() if k != 'embedding'}
            for t in t_functions
        ]
    }
    
    with open(os.path.join(OUTPUT_DIR, 'ft_functions.json'), 'w', encoding='utf-8') as f:
        json.dump(ft_data, f, indent=2)
    
    print(f"\n{'='*70}")
    print(f"COMPLETE! Results saved to: {OUTPUT_DIR}")
    print(f"{'='*70}")
    
    print(f"\nSummary:")
    print(f"  F functions: {len(f_functions)} in {len(f_clusters)} clusters")
    print(f"  T functions: {len(t_functions)} in {len(t_clusters)} clusters")

if __name__ == "__main__":
    main()
