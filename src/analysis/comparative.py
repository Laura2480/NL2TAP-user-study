"""
Comparative Analysis: Real vs Synthetic Datasets

This script performs comprehensive comparative analysis including:
1. Service category distributions (trigger/action)
2. Linguistic analysis (names, descriptions)
3. Semantic feature distributions
4. Getter/Setter pattern analysis
5. Visual reports generation
"""

import json
import os
import sys
from collections import Counter, defaultdict
from typing import Dict, List, Any
import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd
import numpy as np

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

# Set style
sns.set_style("whitegrid")
plt.rcParams['figure.figsize'] = (12, 6)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REAL_DATA = os.path.join(BASE_DIR, "../../data/ifttt_catalog/applets_real_clean.json")
SYNTHETIC_DATA = os.path.join(BASE_DIR, "../../data/test/applets_13k_gpt_final.json")
REAL_SEMANTICS = os.path.join(BASE_DIR, "../../data/reports/real_applets_semantics.json")
SYNTHETIC_SEMANTICS = os.path.join(BASE_DIR, "../../data/reports/synthetic_filtered_semantics.json")
OUTPUT_DIR = os.path.join(BASE_DIR, "../../data/reports/comparative")

os.makedirs(OUTPUT_DIR, exist_ok=True)

def load_data():
    """Load all datasets"""
    print("Loading datasets...")
    
    with open(REAL_DATA, 'r', encoding='utf-8') as f:
        real_applets = json.load(f)
    
    with open(SYNTHETIC_DATA, 'r', encoding='utf-8') as f:
        synthetic_applets = json.load(f)
    
    with open(REAL_SEMANTICS, 'r', encoding='utf-8') as f:
        real_sem = json.load(f)
    
    with open(SYNTHETIC_SEMANTICS, 'r', encoding='utf-8') as f:
        synthetic_sem = json.load(f)
    
    return real_applets, synthetic_applets, real_sem, synthetic_sem

def extract_service_categories(applets, dataset_name):
    """Extract trigger and action service distributions"""
    trigger_services = []
    action_services = []
    
    for applet in applets:
        # Extract from trigger/action fields if available
        if 'trigger_service' in applet:
            trigger_services.append(applet['trigger_service'])
        if 'action_service' in applet:
            action_services.append(applet['action_service'])
    
    return {
        'trigger': Counter(trigger_services),
        'action': Counter(action_services)
    }

def analyze_linguistic_features(applets, dataset_name):
    """Analyze linguistic patterns in names and descriptions"""
    stats = {
        'name_lengths': [],
        'desc_lengths': [],
        'name_words': [],
        'desc_words': []
    }
    
    for applet in applets:
        name = applet.get('name', '') or applet.get('tapir_rule_name', '')
        desc = applet.get('description', '') or applet.get('tapir_rule_description', '')
        
        if name:
            stats['name_lengths'].append(len(name))
            stats['name_words'].append(len(name.split()))
        
        if desc:
            stats['desc_lengths'].append(len(desc))
            stats['desc_words'].append(len(desc.split()))
    
    return stats

def analyze_semantic_features(semantics_data):
    """Extract semantic feature distributions"""
    features = {
        'trigger_features': [],
        'action_params': [],
        'getter_types': Counter(),
        'setter_fields': Counter(),
        'condition_complexity': [],
        'outcomes_per_applet': []
    }
    
    for result in semantics_data['results']:
        if 'error' in result:
            continue
        
        sem = result.get('semantics', {})
        
        # Trigger features
        for feat in sem.get('trigger_features', []):
            features['trigger_features'].append(feat['id'])
            features['getter_types'][feat['type']] += 1
        
        # Action params
        for param in sem.get('action_params', []):
            features['action_params'].append(param['id'])
        
        # Outcomes
        outcomes = sem.get('outcomes', [])
        features['outcomes_per_applet'].append(len(outcomes))
        
        for outcome in outcomes:
            # Setter fields
            for assignment in outcome.get('effect', {}).get('assignments', []):
                field = assignment.get('param', '').split('.')[-1]
                features['setter_fields'][field] += 1
    
    return features

def plot_service_distributions(real_services, synthetic_services):
    """Plot service category distributions"""
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))
    
    # Top 10 trigger services - Real
    real_trigger = real_services['trigger'].most_common(10)
    if real_trigger:
        services, counts = zip(*real_trigger)
        axes[0, 0].barh(services, counts, color='steelblue')
        axes[0, 0].set_title('Top 10 Trigger Services - Real Dataset', fontsize=14, fontweight='bold')
        axes[0, 0].set_xlabel('Count')
    
    # Top 10 trigger services - Synthetic
    synth_trigger = synthetic_services['trigger'].most_common(10)
    if synth_trigger:
        services, counts = zip(*synth_trigger)
        axes[0, 1].barh(services, counts, color='coral')
        axes[0, 1].set_title('Top 10 Trigger Services - Synthetic Dataset', fontsize=14, fontweight='bold')
        axes[0, 1].set_xlabel('Count')
    
    # Top 10 action services - Real
    real_action = real_services['action'].most_common(10)
    if real_action:
        services, counts = zip(*real_action)
        axes[1, 0].barh(services, counts, color='seagreen')
        axes[1, 0].set_title('Top 10 Action Services - Real Dataset', fontsize=14, fontweight='bold')
        axes[1, 0].set_xlabel('Count')
    
    # Top 10 action services - Synthetic
    synth_action = synthetic_services['action'].most_common(10)
    if synth_action:
        services, counts = zip(*synth_action)
        axes[1, 1].barh(services, counts, color='mediumpurple')
        axes[1, 1].set_title('Top 10 Action Services - Synthetic Dataset', fontsize=14, fontweight='bold')
        axes[1, 1].set_xlabel('Count')
    
    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, 'service_distributions.png'), dpi=300, bbox_inches='tight')
    print(f"Saved: service_distributions.png")
    plt.close()

def plot_linguistic_comparison(real_ling, synth_ling):
    """Plot linguistic feature comparisons"""
    fig, axes = plt.subplots(2, 2, figsize=(16, 10))
    
    # Name lengths
    axes[0, 0].hist([real_ling['name_lengths'], synth_ling['name_lengths']], 
                    bins=30, label=['Real', 'Synthetic'], alpha=0.7, color=['steelblue', 'coral'])
    axes[0, 0].set_title('Applet Name Length Distribution', fontsize=14, fontweight='bold')
    axes[0, 0].set_xlabel('Characters')
    axes[0, 0].set_ylabel('Frequency')
    axes[0, 0].legend()
    
    # Description lengths
    axes[0, 1].hist([real_ling['desc_lengths'], synth_ling['desc_lengths']], 
                    bins=30, label=['Real', 'Synthetic'], alpha=0.7, color=['steelblue', 'coral'])
    axes[0, 1].set_title('Description Length Distribution', fontsize=14, fontweight='bold')
    axes[0, 1].set_xlabel('Characters')
    axes[0, 1].set_ylabel('Frequency')
    axes[0, 1].legend()
    
    # Name word count
    axes[1, 0].hist([real_ling['name_words'], synth_ling['name_words']], 
                    bins=20, label=['Real', 'Synthetic'], alpha=0.7, color=['steelblue', 'coral'])
    axes[1, 0].set_title('Applet Name Word Count', fontsize=14, fontweight='bold')
    axes[1, 0].set_xlabel('Words')
    axes[1, 0].set_ylabel('Frequency')
    axes[1, 0].legend()
    
    # Description word count
    axes[1, 1].hist([real_ling['desc_words'], synth_ling['desc_words']], 
                    bins=30, label=['Real', 'Synthetic'], alpha=0.7, color=['steelblue', 'coral'])
    axes[1, 1].set_title('Description Word Count', fontsize=14, fontweight='bold')
    axes[1, 1].set_xlabel('Words')
    axes[1, 1].set_ylabel('Frequency')
    axes[1, 1].legend()
    
    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, 'linguistic_comparison.png'), dpi=300, bbox_inches='tight')
    print(f"Saved: linguistic_comparison.png")
    plt.close()

def plot_semantic_features(real_sem_feat, synth_sem_feat):
    """Plot semantic feature distributions"""
    fig, axes = plt.subplots(2, 3, figsize=(18, 10))
    
    # Getter types - Real
    if real_sem_feat['getter_types']:
        types, counts = zip(*real_sem_feat['getter_types'].most_common(10))
        axes[0, 0].bar(range(len(types)), counts, color='steelblue')
        axes[0, 0].set_xticks(range(len(types)))
        axes[0, 0].set_xticklabels(types, rotation=45, ha='right')
        axes[0, 0].set_title('Getter Types - Real', fontsize=12, fontweight='bold')
        axes[0, 0].set_ylabel('Count')
    
    # Getter types - Synthetic
    if synth_sem_feat['getter_types']:
        types, counts = zip(*synth_sem_feat['getter_types'].most_common(10))
        axes[0, 1].bar(range(len(types)), counts, color='coral')
        axes[0, 1].set_xticks(range(len(types)))
        axes[0, 1].set_xticklabels(types, rotation=45, ha='right')
        axes[0, 1].set_title('Getter Types - Synthetic', fontsize=12, fontweight='bold')
        axes[0, 1].set_ylabel('Count')
    
    # Outcomes per applet
    axes[0, 2].hist([real_sem_feat['outcomes_per_applet'], synth_sem_feat['outcomes_per_applet']], 
                    bins=15, label=['Real', 'Synthetic'], alpha=0.7, color=['steelblue', 'coral'])
    axes[0, 2].set_title('Outcomes per Applet', fontsize=12, fontweight='bold')
    axes[0, 2].set_xlabel('Number of Outcomes')
    axes[0, 2].set_ylabel('Frequency')
    axes[0, 2].legend()
    
    # Top setter fields - Real
    if real_sem_feat['setter_fields']:
        fields, counts = zip(*real_sem_feat['setter_fields'].most_common(10))
        axes[1, 0].barh(fields, counts, color='seagreen')
        axes[1, 0].set_title('Top Setter Fields - Real', fontsize=12, fontweight='bold')
        axes[1, 0].set_xlabel('Count')
    
    # Top setter fields - Synthetic
    if synth_sem_feat['setter_fields']:
        fields, counts = zip(*synth_sem_feat['setter_fields'].most_common(10))
        axes[1, 1].barh(fields, counts, color='mediumpurple')
        axes[1, 1].set_title('Top Setter Fields - Synthetic', fontsize=12, fontweight='bold')
        axes[1, 1].set_xlabel('Count')
    
    # Trigger features count comparison
    real_feat_count = len(set(real_sem_feat['trigger_features']))
    synth_feat_count = len(set(synth_sem_feat['trigger_features']))
    axes[1, 2].bar(['Real', 'Synthetic'], [real_feat_count, synth_feat_count], 
                   color=['steelblue', 'coral'])
    axes[1, 2].set_title('Unique Trigger Features', fontsize=12, fontweight='bold')
    axes[1, 2].set_ylabel('Count')
    
    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, 'semantic_features.png'), dpi=300, bbox_inches='tight')
    print(f"Saved: semantic_features.png")
    plt.close()

def generate_summary_report(real_applets, synthetic_applets, real_sem, synth_sem, 
                           real_services, synth_services, real_ling, synth_ling,
                           real_sem_feat, synth_sem_feat):
    """Generate comprehensive summary report"""
    
    report = f"""# Comparative Analysis Report: Real vs Synthetic Datasets

## Dataset Overview

| Metric | Real Dataset | Synthetic Dataset |
|--------|--------------|-------------------|
| Total Applets | {len(real_applets)} | {len(synthetic_applets)} |
| Analyzed | {real_sem['stats']['success']} | {synth_sem['stats']['success']} |
| Success Rate | {real_sem['stats']['success']/len(real_applets)*100:.1f}% | {synth_sem['stats']['success']/synth_sem['stats']['after_score_filter']*100:.1f}% |

## Service Distribution

### Trigger Services
- **Real**: {len(real_services['trigger'])} unique services
- **Synthetic**: {len(synth_services['trigger'])} unique services

**Top 3 Real Triggers**: {', '.join([s for s, _ in real_services['trigger'].most_common(3)])}
**Top 3 Synthetic Triggers**: {', '.join([s for s, _ in synth_services['trigger'].most_common(3)])}

### Action Services
- **Real**: {len(real_services['action'])} unique services
- **Synthetic**: {len(synth_services['action'])} unique services

**Top 3 Real Actions**: {', '.join([s for s, _ in real_services['action'].most_common(3)])}
**Top 3 Synthetic Actions**: {', '.join([s for s, _ in synth_services['action'].most_common(3)])}

## Linguistic Analysis

### Applet Names
- **Real**: Avg {np.mean(real_ling['name_lengths']):.1f} chars, {np.mean(real_ling['name_words']):.1f} words
- **Synthetic**: Avg {np.mean(synth_ling['name_lengths']):.1f} chars, {np.mean(synth_ling['name_words']):.1f} words

### Descriptions
- **Real**: Avg {np.mean(real_ling['desc_lengths']):.1f} chars, {np.mean(real_ling['desc_words']):.1f} words
- **Synthetic**: Avg {np.mean(synth_ling['desc_lengths']):.1f} chars, {np.mean(synth_ling['desc_words']):.1f} words

## Semantic Features

### Trigger Features (Getters)
- **Real**: {len(set(real_sem_feat['trigger_features']))} unique features
- **Synthetic**: {len(set(synth_sem_feat['trigger_features']))} unique features

**Top Getter Types (Real)**: {', '.join([f"{t}({c})" for t, c in real_sem_feat['getter_types'].most_common(3)])}
**Top Getter Types (Synthetic)**: {', '.join([f"{t}({c})" for t, c in synth_sem_feat['getter_types'].most_common(3)])}

### Action Parameters (Setters)
- **Real**: {len(set(real_sem_feat['action_params']))} unique parameters
- **Synthetic**: {len(set(synth_sem_feat['action_params']))} unique parameters

**Top Setter Fields (Real)**: {', '.join([f for f, _ in real_sem_feat['setter_fields'].most_common(3)])}
**Top Setter Fields (Synthetic)**: {', '.join([f for f, _ in synth_sem_feat['setter_fields'].most_common(3)])}

### Outcomes
- **Real**: Avg {np.mean(real_sem_feat['outcomes_per_applet']):.2f} outcomes per applet
- **Synthetic**: Avg {np.mean(synth_sem_feat['outcomes_per_applet']):.2f} outcomes per applet

## Key Findings

1. **Scale**: Synthetic dataset is {len(synthetic_applets)/len(real_applets):.1f}x larger
2. **Quality**: Synthetic code achieves {synth_sem['stats']['success']/synth_sem['stats']['after_score_filter']*100:.1f}% success rate
3. **Diversity**: Synthetic dataset covers {len(synth_services['trigger'])} trigger services vs {len(real_services['trigger'])} in real
4. **Complexity**: Similar semantic patterns (skip + transform) in both datasets
5. **Linguistic**: Synthetic descriptions are {'longer' if np.mean(synth_ling['desc_lengths']) > np.mean(real_ling['desc_lengths']) else 'shorter'} on average

## Visualizations

- `service_distributions.png`: Service category distributions
- `linguistic_comparison.png`: Name and description analysis
- `semantic_features.png`: Getter/setter patterns and outcomes
"""
    
    with open(os.path.join(OUTPUT_DIR, 'comparative_report.md'), 'w', encoding='utf-8') as f:
        f.write(report)
    
    print(f"Saved: comparative_report.md")

def main():
    print("=" * 60)
    print("COMPARATIVE ANALYSIS: Real vs Synthetic Datasets")
    print("=" * 60)
    
    # Load data
    real_applets, synthetic_applets, real_sem, synth_sem = load_data()
    
    # Filter synthetic to match analysis (no real filter_code, tapir_score > 0.99)
    synthetic_filtered = [a for a in synthetic_applets 
                         if (not a.get('filter_code') or a.get('filter_code') == '') 
                         and a.get('tapir_score', 0) > 0.99]
    
    print(f"\nDatasets loaded:")
    print(f"  Real: {len(real_applets)} applets")
    print(f"  Synthetic (filtered): {len(synthetic_filtered)} applets")
    
    # Extract features
    print("\nExtracting service categories...")
    real_services = extract_service_categories(real_applets, 'Real')
    synth_services = extract_service_categories(synthetic_filtered, 'Synthetic')
    
    print("Analyzing linguistic features...")
    real_ling = analyze_linguistic_features(real_applets, 'Real')
    synth_ling = analyze_linguistic_features(synthetic_filtered, 'Synthetic')
    
    print("Analyzing semantic features...")
    real_sem_feat = analyze_semantic_features(real_sem)
    synth_sem_feat = analyze_semantic_features(synth_sem)
    
    # Generate visualizations
    print("\nGenerating visualizations...")
    plot_service_distributions(real_services, synth_services)
    plot_linguistic_comparison(real_ling, synth_ling)
    plot_semantic_features(real_sem_feat, synth_sem_feat)
    
    # Generate report
    print("\nGenerating summary report...")
    generate_summary_report(real_applets, synthetic_filtered, real_sem, synth_sem,
                          real_services, synth_services, real_ling, synth_ling,
                          real_sem_feat, synth_sem_feat)
    
    print("\n" + "=" * 60)
    print(f"Analysis complete! Reports saved to: {OUTPUT_DIR}")
    print("=" * 60)

if __name__ == "__main__":
    main()
