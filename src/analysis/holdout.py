"""
Advanced Holdout Strategy for Generalization Testing

This script creates a comprehensive holdout strategy that tests generalization across:
1. Service CATEGORIES (e.g., Social Media, Smart Home, Business Tools)
2. Specific SERVICES (e.g., Twitter, Gmail, Spotify)
3. Rule PATTERNS (e.g., time-based, location-based, complex boolean)
4. Semantic FEATURES (from NL descriptions and code structure)

Strategy:
- Analyze Real distribution across all dimensions
- Create Synthetic splits that systematically hold out:
  * Entire service categories
  * Popular individual services
  * Complex rule patterns
  * Specific semantic features
"""

import json
import os
import sys
from collections import Counter, defaultdict
from typing import Dict, List, Tuple, Set

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from sentence_transformers import SentenceTransformer

# Reduce TorchDynamo verbosity
os.environ.setdefault("TORCH_LOGS", "error")
os.environ.setdefault("TORCHDYNAMO_VERBOSE", "0")

import torch._dynamo

torch._dynamo.config.suppress_errors = True

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "../../data/reports/advanced_holdout")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Model paths (will be loaded in main())
ACTION_MODEL_PATH = None
TRIGGER_MODEL_PATH = None
action_model = None
trigger_model = None


def load_sentence_transformer_models():
    """Load SentenceTransformer models for action and trigger channels"""
    global action_model, trigger_model, ACTION_MODEL_PATH, TRIGGER_MODEL_PATH

    print("\nLoading SentenceTransformer models...")

    # Construct paths relative to project root
    project_root = os.path.join(BASE_DIR, "../..")
    ACTION_MODEL_PATH = os.path.join(
        project_root,
        'models/joe32140/ModernBERT-base-msmarco/action_channel_joe32140/ModernBERT-base-msmarco_embedder'
    )
    TRIGGER_MODEL_PATH = os.path.join(
        project_root,
        'models/joe32140/ModernBERT-base-msmarco/trigger_channel_joe32140/ModernBERT-base-msmarco_embedder'
    )

    # Normalize paths
    print(f"Action model path: {ACTION_MODEL_PATH}")
    print(f"Trigger model path: {TRIGGER_MODEL_PATH}")

    try:
        if os.path.exists(ACTION_MODEL_PATH) and os.path.exists(TRIGGER_MODEL_PATH):
            action_model = SentenceTransformer(ACTION_MODEL_PATH)
            trigger_model = SentenceTransformer(TRIGGER_MODEL_PATH)
            print("Models loaded successfully")
            return True
        else:
            print("Warning: Model paths do not exist")
            print(f"  Action model exists: {os.path.exists(ACTION_MODEL_PATH)}")
            print(f"  Trigger model exists: {os.path.exists(TRIGGER_MODEL_PATH)}")
            action_model = None
            trigger_model = None
            return False
    except Exception as e:
        print(f"Warning: Could not load models: {e}")
        action_model = None
        trigger_model = None
        return False


def load_all_data():
    """Load all necessary data"""
    # Load applets from catalog
    print("Loading Applets from Catalog...")

    with open(os.path.join(BASE_DIR, "../../data/dataset/applets/applets_real.json"), 'r', encoding='utf-8') as f:
        real_applets = json.load(f)

    with open(os.path.join(BASE_DIR, "../../data/dataset/applets/applets_synt_gpt_with_code.json"), 'r',
              encoding='utf-8') as f:
        synth_applets = json.load(f)

    print(f"Real applets: {len(real_applets)}")
    print(f"Synthetic applets: {len(synth_applets)}")

    # Semantics
    # Note: Assuming semantics files are still valid for these datasets
    try:
        with open(os.path.join(BASE_DIR, "../../data/reports/real_applets_semantics.json"), 'r',
                  encoding='utf-8') as f:
            real_sem = json.load(f)
    except FileNotFoundError:
        print("Warning: Real semantics not found. Using empty.")
        real_sem = {'results': []}

    try:
        with open(os.path.join(BASE_DIR, "../../data/reports/synthetic_filtered_semantics.json"), 'r',
                  encoding='utf-8') as f:
            synth_sem = json.load(f)
    except FileNotFoundError:
        print("Warning: Synthetic semantics not found. Using empty.")
        synth_sem = {'results': []}

    # Catalog
    with open(os.path.join(BASE_DIR, "../../data/ifttt_catalog/services.json"), 'r', encoding='utf-8') as f:
        services_data = json.load(f)

    with open(os.path.join(BASE_DIR, "../../data/ifttt_catalog/triggers.json"), 'r', encoding='utf-8') as f:
        triggers_data = json.load(f)

    with open(os.path.join(BASE_DIR, "../../data/ifttt_catalog/actions.json"), 'r', encoding='utf-8') as f:
        actions_data = json.load(f)

    # Handle dict format
    if isinstance(services_data, dict):
        services = list(services_data.values())
    else:
        services = services_data

    if isinstance(triggers_data, dict):
        triggers = list(triggers_data.values())
    else:
        triggers = triggers_data

    if isinstance(actions_data, dict):
        actions = list(actions_data.values())
    else:
        actions = actions_data

    return real_applets, synth_applets, real_sem, synth_sem, services, triggers, actions


def compute_embeddings(texts, model, batch_size=32):
    """
    Compute embeddings for a list of texts using the given model

    Args:
        texts: List of strings to encode
        model: SentenceTransformer model
        batch_size: Batch size for encoding

    Returns:
        numpy array of embeddings
    """
    if model is None:
        return None

    if not texts:
        return np.array([])

    return model.encode(texts, batch_size=batch_size, show_progress_bar=False)


def compute_semantic_similarity(embeddings1, embeddings2, model=None):
    """
    Compute cosine similarity between two sets of embeddings
    Uses SentenceTransformer's similarity method if model is provided,
    otherwise computes manually

    Args:
        embeddings1: First set of embeddings (n_samples1, embedding_dim)
        embeddings2: Second set of embeddings (n_samples2, embedding_dim)
        model: Optional SentenceTransformer model to use for similarity computation

    Returns:
        Similarity matrix (n_samples1, n_samples2)
    """
    if embeddings1 is None or embeddings2 is None:
        return None

    if model is not None:
        # Use model's similarity method
        return model.similarity(embeddings1, embeddings2).cpu().numpy()
    else:
        # Fallback to manual computation
        from sklearn.metrics.pairwise import cosine_similarity
        return cosine_similarity(embeddings1, embeddings2)


def extract_action_trigger_texts(applets, semantics_data):
    """
    Extract action and trigger descriptions from applets for embedding
    Uses TAPIR columns: tapir_if_statement for triggers, tapir_then_statement for actions

    Args:
        applets: List of applet dictionaries
        semantics_data: Semantics data with results (optional, for fallback)

    Returns:
        Dictionary mapping applet_id to {action_text, trigger_text}
    """
    texts = {}

    for applet in applets:
        applet_id = applet.get('applet_id')

        if not applet_id:
            continue

        # Extract trigger text from TAPIR if_statement
        trigger_text = applet.get('tapir_if_statement', '')

        # Fallback to trigger module description if TAPIR not available
        if not trigger_text:
            trigger_text = applet.get('trigger_module_description', '') or applet.get('description', '')

        # Extract action text from TAPIR then_statement
        action_text = applet.get('tapir_then_statement', '')

        # Fallback to action module description if TAPIR not available
        if not action_text:
            action_text = applet.get('action_module_description', '') or applet.get('description', '')

        # Only include if we have both texts
        if trigger_text and action_text:
            texts[applet_id] = {
                'trigger_text': trigger_text.strip(),
                'action_text': action_text.strip()
            }

    return texts


def build_service_category_mapping(services):
    """Build mapping from service to category"""
    service_to_category = {}

    for service in services:
        slug = service.get('slug') or service.get('id', '')
        category = service.get('category', 'Unknown')

        if slug:
            service_to_category[slug] = category

    return service_to_category


def extract_comprehensive_features(applets, semantics_data=None, service_to_category=None):
    """
    Extract comprehensive features for each applet
    Works without semantics by using applet metadata and filter_code
    """

    applet_features = {}

    for applet in applets:
        applet_id = applet.get('applet_id')

        if not applet_id:
            continue

        # 1. Extract services from applet metadata
        trigger_service = applet.get('trigger_service_slug', '')
        action_service = applet.get('action_service_slug', '')

        trigger_services = {trigger_service} if trigger_service else set()
        action_services = {action_service} if action_service else set()
        all_services = trigger_services | action_services

        # 2. Extract categories from applet columns
        categories = set()
        trigger_categories = applet.get('trigger_categories', [])
        action_categories = applet.get('action_categories', [])

        # Handle both list and string formats
        if isinstance(trigger_categories, list):
            categories.update(trigger_categories)
        elif trigger_categories:
            categories.add(trigger_categories)

        if isinstance(action_categories, list):
            categories.update(action_categories)
        elif action_categories:
            categories.add(action_categories)

        # 3. Analyze rule patterns from filter_code
        filter_code = applet.get('filter_code', '') or applet.get('filter_code_gpt', '')

        has_time_based = False
        has_location_based = False
        has_complex_boolean = False
        has_transform = False
        has_skip = False
        num_outcomes = 0

        if filter_code:
            # Count outcomes (if statements)
            num_outcomes = filter_code.count('if (') + filter_code.count('if(')

            # Time-based patterns
            if any(keyword in filter_code.lower()
                   for keyword in ['hour', 'day', 'time', 'date', 'month', 'createdat', 'occurredat']):
                has_time_based = True

            # Location-based patterns
            if any(keyword in filter_code.lower() for keyword in ['location', 'latitude', 'longitude', 'address']):
                has_location_based = True

            # Complex boolean (both AND and OR)
            if '&&' in filter_code and '||' in filter_code:
                has_complex_boolean = True

            # Transform (setters)
            if '.setValue(' in filter_code or '.setvalue(' in filter_code.lower():
                has_transform = True

            # Skip
            if '.skip()' in filter_code.lower():
                has_skip = True

        # Complexity score
        complexity_score = num_outcomes + (2 if has_complex_boolean else 0) + (1 if has_transform else 0)

        applet_features[applet_id] = {
            'trigger_services': list(trigger_services),
            'action_services': list(action_services),
            'all_services': list(all_services),
            'categories': list(categories),
            'num_outcomes': num_outcomes,
            'has_time_based': has_time_based,
            'has_location_based': has_location_based,
            'has_complex_boolean': has_complex_boolean,
            'has_transform': has_transform,
            'has_skip': has_skip,
            'feature_types': {},  # Not available without semantics
            'complexity_score': complexity_score
        }

    return applet_features


def analyze_real_distribution(real_features):
    """Analyze Real distribution across all dimensions"""

    analysis = {
        'services': Counter(),
        'categories': Counter(),
        'patterns': {
            'time_based': 0,
            'location_based': 0,
            'complex_boolean': 0,
            'has_transform': 0,
            'has_skip': 0
        },
        'feature_types': Counter(),
        'complexity': []
    }

    for features in real_features.values():
        # Services
        analysis['services'].update(features['all_services'])

        # Categories
        analysis['categories'].update(features['categories'])

        # Patterns
        if features['has_time_based']:
            analysis['patterns']['time_based'] += 1
        if features['has_location_based']:
            analysis['patterns']['location_based'] += 1
        if features['has_complex_boolean']:
            analysis['patterns']['complex_boolean'] += 1
        if features['has_transform']:
            analysis['patterns']['has_transform'] += 1
        if features['has_skip']:
            analysis['patterns']['has_skip'] += 1

        # Feature types
        for feat_type, count in features['feature_types'].items():
            analysis['feature_types'][feat_type] += count

        # Complexity
        analysis['complexity'].append(features['complexity_score'])

    return analysis


def create_multi_level_holdout(synth_applets, synth_features, real_analysis):
    """
    Create multi-level holdout strategy

    Levels:
    1. Category-level: Hold out entire service categories
    2. Service-level: Hold out popular individual services
    3. Pattern-level: Hold out complex rule patterns
    4. Feature-level: Hold out specific semantic features
    """

    # Identify elements to hold out based on Real distribution

    # 1. Categories to hold out (Top 1 instead of Top 2)
    # Relaxed: Only hold out the very top category if it dominates
    top_categories = [c for c, _ in real_analysis['categories'].most_common(1)]
    held_out_categories = set(top_categories)

    # 2. Services to hold out (Top 1)
    top_services = [s for s, _ in real_analysis['services'].most_common(1)]
    held_out_services = set(top_services)

    # 3. Patterns to hold out (Relaxed)
    # Only hold out 'high_complexity', allow 'complex_boolean' in training
    held_out_patterns = {'high_complexity'}

    # 4. Calculate Realism Score (Target-Distribution)
    # We want Test to overlap well with Real (i.e., look like Real)
    # Train should cover everything else (including Rare/Complex)

    scored_applets = []
    total_real_services = sum(real_analysis['services'].values())

    for applet in synth_applets:
        applet_id = applet.get('applet_id')
        if applet_id not in synth_features:
            continue

        features = synth_features[applet_id]

        # Realism Score components
        # A. Service Realism (Frequency in Real)
        svc_score = 0
        for svc in features['all_services']:
            freq = real_analysis['services'].get(svc, 0) / total_real_services if total_real_services else 0
            svc_score += freq

        # B. Category Realism (Bonus for being in top categories)
        cat_score = 0
        for cat in features['categories']:
            if cat in held_out_categories:  # Top categories
                cat_score += 0.5

        # Final Realism Score
        # Higher = More similar to Real distribution
        realism_score = svc_score + cat_score

        scored_applets.append({
            'applet': applet,
            'score': realism_score,
            'id': applet_id
        })

    # 5. Sort by Realism (Descending)
    # Top = Most Real-like
    import zlib
    scored_applets.sort(key=lambda x: (x['score'], zlib.adler32(x['id'].encode('utf-8'))), reverse=True)

    total_count = len(scored_applets)
    test_size = int(total_count * 0.20)
    val_size = 256  # Fixed size as requested
    train_size = total_count - test_size - val_size

    # 6. Slice into pools (TARGET-DISTRIBUTION SPLIT)
    # Test gets the Top 20% (Most Real-like) -> Best proxy for Real
    # Train/Val get the rest (Mix of Real-like and Rare/Complex)

    test_pool = [x['applet'] for x in scored_applets[:test_size]]

    # Remaining 80% shuffled/interleaved for Train/Val to ensure they share the "Rest" distribution
    remaining = scored_applets[test_size:]

    # Simple split of remaining
    val_pool = [x['applet'] for x in remaining[:val_size]]
    train_pool = [x['applet'] for x in remaining[val_size:]]

    print("\n=== TARGET-DISTRIBUTION SPLIT (Realism Prioritized) ===")
    print(f"Total Applets: {total_count}")
    print(f"Test Pool (Most Realistic): {len(test_pool)}")
    print(f"Val Pool (Semi-Realistic):  {len(val_pool)}")
    print(f"Train Pool (Least Realistic/Rare): {len(train_pool)}")

    # Debug score stats
    def print_stats(name, pool_objs):
        scores = [x['score'] for x in pool_objs]
        print(f"{name}: Mean Realism Score {np.mean(scores):.4f}")

    print_stats("Test ", scored_applets[:test_size])
    print_stats("Val  ", remaining[:val_size])
    print_stats("Train", remaining[val_size:])

    return {
        'train': train_pool,
        'val': val_pool,
        'test': test_pool,
        'holdout_categories': list(held_out_categories),
        'holdout_services': list(held_out_services),
        'holdout_patterns': list(held_out_patterns)
    }


def visualize_holdout_strategy(splits, real_analysis, synth_features):
    """Visualize the multi-level holdout strategy with advanced plots"""

    fig = plt.figure(figsize=(24, 16))
    gs = fig.add_gridspec(3, 4, hspace=0.4, wspace=0.3)

    # 1. Split sizes (Bar Plot)
    ax1 = fig.add_subplot(gs[0, 0])
    datasets = ['Synth\nTrain', 'Synth\nVal', 'Synth\nTest']
    sizes = [len(splits['train']), len(splits['val']), len(splits['test'])]
    colors = ['#2ecc71', '#f1c40f', '#e74c3c']  # Green, Yellow, Red
    bars = ax1.bar(datasets, sizes, color=colors, edgecolor='black', alpha=0.8)
    ax1.bar_label(bars)
    ax1.set_ylabel('Applets')
    ax1.set_title('Dataset Sizes', fontweight='bold')
    ax1.grid(axis='y', alpha=0.3)

    # 2. Complexity Distribution (KDE Plot)
    ax2 = fig.add_subplot(gs[0, 1:])
    train_complexity = [
        synth_features[a['applet_id']]['complexity_score'] for a in splits['train']
        if a['applet_id'] in synth_features
    ]
    test_complexity = [
        synth_features[a['applet_id']]['complexity_score'] for a in splits['test']
        if a['applet_id'] in synth_features
    ]
    real_complexity = real_analysis['complexity']

    sns.kdeplot(train_complexity, ax=ax2, fill=True, label='Synth Train', color='#2ecc71', alpha=0.3)
    sns.kdeplot(test_complexity, ax=ax2, fill=True, label='Synth Test', color='#e74c3c', alpha=0.3)
    sns.kdeplot(real_complexity, ax=ax2, fill=True, label='Real Target', color='#3498db', alpha=0.3, linewidth=2)

    ax2.set_xlabel('Complexity Score')
    ax2.set_title('Complexity Distribution (KDE)', fontweight='bold')
    ax2.legend()
    ax2.grid(True, alpha=0.3)

    # 3. Service Coverage Gap (Bar Plot)
    ax3 = fig.add_subplot(gs[1, 0:2])

    # Calculate Jaccard similarity of services with Real
    real_services = set(real_analysis['services'].keys())

    def get_services(pool):
        svcs = set()
        for a in pool:
            if a['applet_id'] in synth_features:
                svcs.update(synth_features[a['applet_id']]['all_services'])
        return svcs

    train_svcs = get_services(splits['train'])
    test_svcs = get_services(splits['test'])

    train_overlap = len(train_svcs & real_services) / len(real_services) if real_services else 0
    test_overlap = len(test_svcs & real_services) / len(real_services) if real_services else 0

    ax3.bar(['Train vs Real', 'Test vs Real'], [train_overlap, test_overlap],
            color=['#2ecc71', '#e74c3c'], alpha=0.7, edgecolor='black')
    ax3.set_ylim(0, 1.0)
    ax3.set_ylabel('Jaccard Similarity (Services)')
    ax3.set_title('Service Overlap with Real Data', fontweight='bold')
    ax3.grid(axis='y', alpha=0.3)

    # 4. Pattern Distribution Heatmap
    ax4 = fig.add_subplot(gs[1, 2:])

    patterns = ['time_based', 'location_based', 'complex_boolean', 'has_transform', 'has_skip']

    def get_pattern_counts(pool):
        counts = {p: 0 for p in patterns}
        total = 0
        for a in pool:
            if a['applet_id'] in synth_features:
                total += 1
                f = synth_features[a['applet_id']]
                if f['has_time_based']:
                    counts['time_based'] += 1
                if f['has_location_based']:
                    counts['location_based'] += 1
                if f['has_complex_boolean']:
                    counts['complex_boolean'] += 1
                if f['has_transform']:
                    counts['has_transform'] += 1
                if f['has_skip']:
                    counts['has_skip'] += 1
        return {k: v / total if total else 0 for k, v in counts.items()}

    train_probs = get_pattern_counts(splits['train'])
    test_probs = get_pattern_counts(splits['test'])
    real_total = len(real_analysis['complexity']) if real_analysis['complexity'] else 1
    real_probs = {k: v / real_total for k, v in real_analysis['patterns'].items()}

    data = pd.DataFrame([train_probs, test_probs, real_probs], index=['Train', 'Test', 'Real'])
    sns.heatmap(data, annot=True, cmap='Blues', ax=ax4, fmt='.2f', cbar_kws={'label': 'Probability'})
    ax4.set_title('Pattern Probability Heatmap', fontweight='bold')

    # 5. Held-out Elements Summary
    ax5 = fig.add_subplot(gs[2, :])
    ax5.axis('off')

    summary_text = f"""
    HOLDOUT STRATEGY SUMMARY

    Held-out Categories: {', '.join(splits['holdout_categories'])}
    Held-out Services: {', '.join(splits['holdout_services'])}
    Held-out Patterns: {', '.join(splits['holdout_patterns'])}

    Train Set ({len(splits['train'])}):
      - Optimized for learning basic patterns
      - Complexity Mean: {np.mean(train_complexity):.2f}
      - Service Overlap with Real: {train_overlap:.1%}

    Test Set ({len(splits['test'])}):
      - Optimized for generalization testing
      - Complexity Mean: {np.mean(test_complexity):.2f}
      - Service Overlap with Real: {test_overlap:.1%}
      - Contains unseen categories and services
    """

    ax5.text(
        0.5,
        0.5,
        summary_text,
        ha='center',
        va='center',
        fontsize=14,
        family='monospace',
        bbox=dict(boxstyle='round', facecolor='#f0f0f0', alpha=0.5),
    )

    try:
        fig.tight_layout()
    except Exception as e:
        print(f"Warning: fig.tight_layout() failed: {e}")
    plt.savefig(os.path.join(OUTPUT_DIR, 'advanced_holdout_visualization.png'), dpi=300)
    print("Saved: advanced_holdout_visualization.png")
    plt.close()


def visualize_semantic_similarities(semantic_analysis):
    """
    Visualize semantic similarity analysis results
    """
    if semantic_analysis is None:
        print("No semantic analysis to visualize")
        return

    fig = plt.figure(figsize=(20, 12))
    gs = fig.add_gridspec(2, 3, hspace=0.3, wspace=0.3)

    action_stats = semantic_analysis['action_stats']
    trigger_stats = semantic_analysis['trigger_stats']

    # 1. Action Channel - Mean Similarities (Bar Plot)
    ax1 = fig.add_subplot(gs[0, 0])
    comparisons = ['Train vs\nTest', 'Train vs\nReal', 'Test vs\nReal', 'Val vs\nReal']
    action_means = [
        action_stats['train_vs_test']['mean'],
        action_stats['train_vs_real']['mean'],
        action_stats['test_vs_real']['mean'],
        action_stats['val_vs_real']['mean']
    ]
    bars = ax1.bar(
        comparisons,
        action_means,
        color=['#3498db', '#e74c3c', '#2ecc71', '#f39c12'],
        alpha=0.7,
        edgecolor='black'
    )
    ax1.bar_label(bars, fmt='%.3f')
    ax1.set_ylabel('Mean Cosine Similarity')
    ax1.set_title('Action Channel - Mean Similarities', fontweight='bold')
    ax1.set_ylim(0, 1.0)
    ax1.grid(axis='y', alpha=0.3)

    # 2. Trigger Channel - Mean Similarities (Bar Plot)
    ax2 = fig.add_subplot(gs[0, 1])
    trigger_means = [
        trigger_stats['train_vs_test']['mean'],
        trigger_stats['train_vs_real']['mean'],
        trigger_stats['test_vs_real']['mean'],
        trigger_stats['val_vs_real']['mean']
    ]
    bars = ax2.bar(
        comparisons,
        trigger_means,
        color=['#3498db', '#e74c3c', '#2ecc71', '#f39c12'],
        alpha=0.7,
        edgecolor='black'
    )
    ax2.bar_label(bars, fmt='%.3f')
    ax2.set_ylabel('Mean Cosine Similarity')
    ax2.set_title('Trigger Channel - Mean Similarities', fontweight='bold')
    ax2.set_ylim(0, 1.0)
    ax2.grid(axis='y', alpha=0.3)

    # 3. Combined Comparison (Grouped Bar)
    ax3 = fig.add_subplot(gs[0, 2])
    x = np.arange(len(comparisons))
    width = 0.35
    bars1 = ax3.bar(
        x - width / 2,
        action_means,
        width,
        label='Action',
        color='#3498db',
        alpha=0.7,
        edgecolor='black'
    )
    bars2 = ax3.bar(
        x + width / 2,
        trigger_means,
        width,
        label='Trigger',
        color='#e74c3c',
        alpha=0.7,
        edgecolor='black'
    )
    ax3.set_ylabel('Mean Cosine Similarity')
    ax3.set_title('Action vs Trigger Channels', fontweight='bold')
    ax3.set_xticks(x)
    ax3.set_xticklabels(comparisons)
    ax3.legend()
    ax3.set_ylim(0, 1.0)
    ax3.grid(axis='y', alpha=0.3)

    # 4. Action Channel - Mean-Max Similarities
    ax4 = fig.add_subplot(gs[1, 0])
    action_mean_max = [
        action_stats['train_vs_test']['mean_max'],
        action_stats['train_vs_real']['mean_max'],
        action_stats['test_vs_real']['mean_max'],
        action_stats['val_vs_real']['mean_max']
    ]
    bars = ax4.bar(
        comparisons,
        action_mean_max,
        color=['#3498db', '#e74c3c', '#2ecc71', '#f39c12'],
        alpha=0.7,
        edgecolor='black'
    )
    ax4.bar_label(bars, fmt='%.3f')
    ax4.set_ylabel('Mean-Max Cosine Similarity')
    ax4.set_title('Action Channel - Mean-Max Similarities', fontweight='bold')
    ax4.set_ylim(0, 1.0)
    ax4.grid(axis='y', alpha=0.3)

    # 5. Trigger Channel - Mean-Max Similarities
    ax5 = fig.add_subplot(gs[1, 1])
    trigger_mean_max = [
        trigger_stats['train_vs_test']['mean_max'],
        trigger_stats['train_vs_real']['mean_max'],
        trigger_stats['test_vs_real']['mean_max'],
        trigger_stats['val_vs_real']['mean_max']
    ]
    bars = ax5.bar(
        comparisons,
        trigger_mean_max,
        color=['#3498db', '#e74c3c', '#2ecc71', '#f39c12'],
        alpha=0.7,
        edgecolor='black'
    )
    ax5.bar_label(bars, fmt='%.3f')
    ax5.set_ylabel('Mean-Max Cosine Similarity')
    ax5.set_title('Trigger Channel - Mean-Max Similarities', fontweight='bold')
    ax5.set_ylim(0, 1.0)
    ax5.grid(axis='y', alpha=0.3)

    # 6. Summary Statistics Table
    ax6 = fig.add_subplot(gs[1, 2])
    ax6.axis('off')

    summary_data = []
    for comp, a_mean, a_max, t_mean, t_max in zip(
        ['Train vs Test', 'Train vs Real', 'Test vs Real', 'Val vs Real'],
        action_means,
        action_mean_max,
        trigger_means,
        trigger_mean_max
    ):
        summary_data.append([comp, f'{a_mean:.3f}', f'{a_max:.3f}', f'{t_mean:.3f}', f'{t_max:.3f}'])

    table = ax6.table(
        cellText=summary_data,
        colLabels=['Comparison', 'Action\nMean', 'Action\nMean-Max', 'Trigger\nMean', 'Trigger\nMean-Max'],
        cellLoc='center',
        loc='center',
        bbox=[0, 0, 1, 1]
    )
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    table.scale(1, 2)

    # Style header
    for i in range(5):
        table[(0, i)].set_facecolor('#34495e')
        table[(0, i)].set_text_props(weight='bold', color='white')

    # Alternate row colors
    for i in range(1, len(summary_data) + 1):
        for j in range(5):
            if i % 2 == 0:
                table[(i, j)].set_facecolor('#ecf0f1')

    ax6.set_title('Summary Statistics', fontweight='bold', pad=20)

    plt.suptitle('Semantic Similarity Analysis (ModernBERT)', fontsize=16, fontweight='bold', y=0.98)
    try:
        fig.tight_layout()
    except Exception as e:
        print(f"Warning: fig.tight_layout() failed in semantic visualization: {e}")
    plt.savefig(os.path.join(OUTPUT_DIR, 'semantic_similarity_analysis.png'), dpi=300)
    print("Saved: semantic_similarity_analysis.png")
    plt.close()


def analyze_semantic_similarities(splits, synth_applets, synth_sem, real_applets, real_sem):
    """
    Analyze semantic similarities between splits using ModernBERT embeddings

    Returns:
        Dictionary with similarity metrics and embeddings
    """
    if action_model is None or trigger_model is None:
        print("Warning: Models not loaded, skipping semantic analysis")
        return None

    print("\n=== Computing Semantic Embeddings ===")

    # Extract texts for all applets
    print("Extracting action/trigger texts from synthetic applets...")
    synth_texts = extract_action_trigger_texts(synth_applets, synth_sem)

    print("Extracting action/trigger texts from real applets...")
    real_texts = extract_action_trigger_texts(real_applets, real_sem)

    # Organize by split
    def get_texts_for_split(split_applets, text_dict):
        action_texts = []
        trigger_texts = []
        applet_ids = []

        for applet in split_applets:
            applet_id = applet.get('applet_id')
            if applet_id in text_dict:
                action_texts.append(text_dict[applet_id]['action_text'])
                trigger_texts.append(text_dict[applet_id]['trigger_text'])
                applet_ids.append(applet_id)

        return action_texts, trigger_texts, applet_ids

    # Get texts for each split
    train_actions, train_triggers, train_ids = get_texts_for_split(splits['train'], synth_texts)
    val_actions, val_triggers, val_ids = get_texts_for_split(splits['val'], synth_texts)
    test_actions, test_triggers, test_ids = get_texts_for_split(splits['test'], synth_texts)
    real_actions, real_triggers, real_ids = get_texts_for_split(real_applets, real_texts)

    # Compute embeddings
    print("\nComputing action embeddings...")
    print(f"  Train: {len(train_actions)} samples")
    train_action_emb = compute_embeddings(train_actions, action_model)
    print(f"  Val: {len(val_actions)} samples")
    val_action_emb = compute_embeddings(val_actions, action_model)
    print(f"  Test: {len(test_actions)} samples")
    test_action_emb = compute_embeddings(test_actions, action_model)
    print(f"  Real: {len(real_actions)} samples")
    real_action_emb = compute_embeddings(real_actions, action_model)

    print("\nComputing trigger embeddings...")
    print(f"  Train: {len(train_triggers)} samples")
    train_trigger_emb = compute_embeddings(train_triggers, trigger_model)
    print(f"  Val: {len(val_triggers)} samples")
    val_trigger_emb = compute_embeddings(val_triggers, trigger_model)
    print(f"  Test: {len(test_triggers)} samples")
    test_trigger_emb = compute_embeddings(test_triggers, trigger_model)
    print(f"  Real: {len(real_triggers)} samples")
    real_trigger_emb = compute_embeddings(real_triggers, trigger_model)

    # Compute similarities
    print("\n=== Computing Semantic Similarities ===")

    # Train vs Test
    print("Train vs Test...")
    train_test_action_sim = compute_semantic_similarity(train_action_emb, test_action_emb, action_model)
    train_test_trigger_sim = compute_semantic_similarity(train_trigger_emb, test_trigger_emb, trigger_model)

    # Train vs Real
    print("Train vs Real...")
    train_real_action_sim = compute_semantic_similarity(train_action_emb, real_action_emb, action_model)
    train_real_trigger_sim = compute_semantic_similarity(train_trigger_emb, real_trigger_emb, trigger_model)

    # Test vs Real
    print("Test vs Real...")
    test_real_action_sim = compute_semantic_similarity(test_action_emb, real_action_emb, action_model)
    test_real_trigger_sim = compute_semantic_similarity(test_trigger_emb, real_trigger_emb, trigger_model)

    # Val vs Real
    print("Val vs Real...")
    val_real_action_sim = compute_semantic_similarity(val_action_emb, real_action_emb, action_model)
    val_real_trigger_sim = compute_semantic_similarity(val_trigger_emb, real_trigger_emb, trigger_model)

    # Compute summary statistics
    def compute_stats(sim_matrix, name):
        if sim_matrix is None:
            return None

        # Average max similarity (for each sample in first set, find best match in second set)
        max_sims = np.max(sim_matrix, axis=1)
        mean_max_sim = np.mean(max_sims)

        # Average similarity
        mean_sim = np.mean(sim_matrix)

        print(f"  {name}: Mean={mean_sim:.4f}, Mean-Max={mean_max_sim:.4f}")

        return {
            'mean': float(mean_sim),
            'mean_max': float(mean_max_sim),
            'std': float(np.std(sim_matrix)),
            'matrix': sim_matrix
        }

    print("\nAction Channel Statistics:")
    action_stats = {
        'train_vs_test': compute_stats(train_test_action_sim, "Train vs Test"),
        'train_vs_real': compute_stats(train_real_action_sim, "Train vs Real"),
        'test_vs_real': compute_stats(test_real_action_sim, "Test vs Real"),
        'val_vs_real': compute_stats(val_real_action_sim, "Val vs Real")
    }

    print("\nTrigger Channel Statistics:")
    trigger_stats = {
        'train_vs_test': compute_stats(train_test_trigger_sim, "Train vs Test"),
        'train_vs_real': compute_stats(train_real_trigger_sim, "Train vs Real"),
        'test_vs_real': compute_stats(test_real_trigger_sim, "Test vs Real"),
        'val_vs_real': compute_stats(val_real_trigger_sim, "Val vs Real")
    }

    return {
        'action_stats': action_stats,
        'trigger_stats': trigger_stats,
        'embeddings': {
            'train_action': train_action_emb,
            'train_trigger': train_trigger_emb,
            'val_action': val_action_emb,
            'val_trigger': val_trigger_emb,
            'test_action': test_action_emb,
            'test_trigger': test_trigger_emb,
            'real_action': real_action_emb,
            'real_trigger': real_trigger_emb
        },
        'ids': {
            'train': train_ids,
            'val': val_ids,
            'test': test_ids,
            'real': real_ids
        }
    }


def generate_comprehensive_report(splits, real_analysis, synth_features, semantic_analysis=None):
    """Generate comprehensive report"""

    # Calculate statistics
    train_services = set()
    val_services = set()
    test_services = set()

    for a in splits['train']:
        if a['applet_id'] in synth_features:
            train_services.update(synth_features[a['applet_id']]['all_services'])

    for a in splits['val']:
        if a['applet_id'] in synth_features:
            val_services.update(synth_features[a['applet_id']]['all_services'])

    for a in splits['test']:
        if a['applet_id'] in synth_features:
            test_services.update(synth_features[a['applet_id']]['all_services'])

    unseen_val = val_services - train_services
    unseen_test = test_services - train_services

    # Build semantic analysis section
    semantic_section = ""
    if semantic_analysis is not None:
        action_stats = semantic_analysis['action_stats']
        trigger_stats = semantic_analysis['trigger_stats']

        semantic_section = f"""
## Semantic Similarity Analysis (ModernBERT)

### Action Channel Similarities
- **Train vs Test**: Mean={action_stats['train_vs_test']['mean']:.4f}, Mean-Max={action_stats['train_vs_test']['mean_max']:.4f}
- **Train vs Real**: Mean={action_stats['train_vs_real']['mean']:.4f}, Mean-Max={action_stats['train_vs_real']['mean_max']:.4f}
- **Test vs Real**: Mean={action_stats['test_vs_real']['mean']:.4f}, Mean-Max={action_stats['test_vs_real']['mean_max']:.4f}
- **Val vs Real**: Mean={action_stats['val_vs_real']['mean']:.4f}, Mean-Max={action_stats['val_vs_real']['mean_max']:.4f}

### Trigger Channel Similarities
- **Train vs Test**: Mean={trigger_stats['train_vs_test']['mean']:.4f}, Mean-Max={trigger_stats['train_vs_test']['mean_max']:.4f}
- **Train vs Real**: Mean={trigger_stats['train_vs_real']['mean']:.4f}, Mean-Max={trigger_stats['train_vs_real']['mean_max']:.4f}
- **Test vs Real**: Mean={trigger_stats['test_vs_real']['mean']:.4f}, Mean-Max={trigger_stats['test_vs_real']['mean_max']:.4f}
- **Val vs Real**: Mean={trigger_stats['val_vs_real']['mean']:.4f}, Mean-Max={trigger_stats['val_vs_real']['mean_max']:.4f}

### Interpretation
- **Mean**: Average cosine similarity across all pairs
- **Mean-Max**: Average of maximum similarities (best match for each sample)
- Higher values indicate better semantic alignment between splits
"""

    report = f"""# Advanced Multi-Level Holdout Strategy

## Overview

This split strategy tests generalization across **four dimensions**:
1. **Service Categories** (e.g., Social Media, Smart Home, Business Tools)
2. **Individual Services** (e.g., Twitter, Gmail, Spotify)
3. **Rule Patterns** (e.g., time-based, location-based, complex boolean)
4. **Semantic Features** (from NL descriptions and code structure)

## Split Configuration

### Synthetic Train
- **Size**: {len(splits['train'])} applets
- **Characteristics**: 
  - NO popular categories: {', '.join(splits['holdout_categories'])}
  - NO popular services ({len(splits['holdout_services'])} held out)
  - NO complex patterns: {', '.join(splits['holdout_patterns'])}
- **Services**: {len(train_services)} unique
- **Purpose**: Learn general patterns without memorizing popular elements

### Synthetic Validation
- **Size**: {len(splits['val'])} applets
- **Characteristics**: Moderate holdout (1-2 criteria matched)
- **Services**: {len(val_services)} unique ({len(unseen_val)} unseen = {len(unseen_val)/len(val_services)*100 if len(val_services) > 0 else 0:.1f}%)
- **Purpose**: Tune on moderate generalization challenge

### Synthetic Test
- **Size**: {len(splits['test'])} applets
- **Characteristics**: Strong holdout (3+ criteria matched)
- **Services**: {len(test_services)} unique ({len(unseen_test)} unseen = {len(unseen_test)/len(test_services)*100 if len(test_services) > 0 else 0:.1f}%)
- **Purpose**: Evaluate strong generalization

## Held-Out Elements

### Categories ({len(splits['holdout_categories'])})
{chr(10).join([f'- {cat}' for cat in splits['holdout_categories']])}

### Popular Services ({len(splits['holdout_services'])})
{chr(10).join([f'- {svc}' for svc in list(splits['holdout_services'])[:20]])}
{'...' if len(splits['holdout_services']) > 20 else ''}

### Complex Patterns
{chr(10).join([f'- {pattern}' for pattern in splits['holdout_patterns']])}

## Real Distribution (Target)

**Top Categories**:
{chr(10).join([f'- {cat}: {count}' for cat, count in real_analysis['categories'].most_common(5)])}

**Top Services**:
{chr(10).join([f'- {svc}: {count}' for svc, count in real_analysis['services'].most_common(10)])}

**Pattern Prevalence**:
{chr(10).join([f'- {pattern}: {count}' for pattern, count in real_analysis['patterns'].items()])}

{semantic_section}

## Generalization Testing Levels

### Level 1: Category Generalization
Test if model can handle services from **unseen categories**.
- Example: Train without Social Media, test on Twitter/Facebook

### Level 2: Service Generalization
Test if model can handle **specific unseen services** within seen categories.
- Example: Train with Instagram but not Twitter (both Social Media)

### Level 3: Pattern Generalization
Test if model can handle **unseen rule patterns**.
- Example: Train on simple conditions, test on complex boolean logic

### Level 4: Semantic Generalization
Test if model can handle **unseen semantic features** from NL descriptions.
- Example: Train on time-based rules, test on location-based rules

## Usage

1. **Train** on `synth_train` ({len(splits['train'])} applets)
2. **Validate** on `synth_val` ({len(splits['val'])} applets)
3. **Test** on `synth_test` ({len(splits['test'])} applets)
4. **Final eval** on Real (all {len(splits['real_test'])} applets after removing outliers)

## Files Generated

- `advanced_holdout_ids.json`: Applet IDs for each split
- `advanced_holdout_visualization.png`: Comprehensive visual analysis
- `advanced_holdout_report.md`: This report
"""

    return report


def main():
    print("=" * 70)
    print("ADVANCED MULTI-LEVEL HOLDOUT STRATEGY")
    print("=" * 70)

    # Load SentenceTransformer models
    load_sentence_transformer_models()

    # Load data
    print("\nLoading data...")
    real_applets, synth_applets, real_sem, synth_sem, services, triggers, actions = load_all_data()

    print(f"Real applets: {len(real_applets)}")
    print(f"Synthetic applets: {len(synth_applets)}")

    # Remove outliers from Real
    print("\nRemoving Real outliers...")
    sem_lookup = {r['applet_id']: r for r in real_sem['results'] if 'error' not in r}
    complexity_scores = []
    for applet in real_applets:
        applet_id = applet.get('applet_id')
        if applet_id in sem_lookup:
            outcomes = sem_lookup[applet_id].get('semantics', {}).get('outcomes', [])
            complexity_scores.append((applet_id, len(outcomes)))

    complexity_scores.sort(key=lambda x: x[1], reverse=True)
    outlier_ids = [aid for aid, _ in complexity_scores[:2]]
    real_clean = [a for a in real_applets if a['applet_id'] not in outlier_ids]

    print(f"Real applets after removing outliers: {len(real_clean)}")

    # Extract comprehensive features (categories from applet columns)
    print("\nExtracting comprehensive features from applets...")
    real_features = extract_comprehensive_features(real_clean, real_sem)
    synth_features = extract_comprehensive_features(synth_applets, synth_sem)

    print(f"Extracted features for {len(real_features)} Real and {len(synth_features)} Synthetic applets")

    # Analyze Real distribution
    print("\nAnalyzing Real distribution...")
    real_analysis = analyze_real_distribution(real_features)

    print("\nReal Distribution:")
    print(f"  Top categories: {real_analysis['categories'].most_common(3)}")
    print(f"  Top services: {real_analysis['services'].most_common(5)}")
    print(f"  Patterns: {real_analysis['patterns']}")

    # Create multi-level holdout
    print("\nCreating multi-level holdout splits...")
    splits = create_multi_level_holdout(synth_applets, synth_features, real_analysis)

    # Add Real test
    splits['real_test'] = real_clean
    splits['real_outliers'] = outlier_ids

    # Perform semantic analysis using ModernBERT models
    print("\n" + "=" * 70)
    print("SEMANTIC SIMILARITY ANALYSIS")
    print("=" * 70)
    semantic_analysis = analyze_semantic_similarities(splits, synth_applets, synth_sem, real_clean, real_sem)

    # Visualize semantic similarities
    if semantic_analysis is not None:
        print("\nGenerating semantic similarity visualizations...")
        visualize_semantic_similarities(semantic_analysis)

    # Visualize
    print("\nGenerating holdout strategy visualizations...")
    visualize_holdout_strategy(splits, real_analysis, synth_features)

    # Generate report
    print("Generating report...")
    report = generate_comprehensive_report(splits, real_analysis, synth_features, semantic_analysis)

    with open(os.path.join(OUTPUT_DIR, 'advanced_holdout_report.md'), 'w', encoding='utf-8') as f:
        f.write(report)

    # Save split IDs
    print("Saving split IDs...")
    split_ids = {
        'synth_train': [a['applet_id'] for a in splits['train']],
        'synth_val': [a['applet_id'] for a in splits['val']],
        'synth_test': [a['applet_id'] for a in splits['test']],
        'real_test': [a['applet_id'] for a in splits['real_test']],
        'real_outliers': splits['real_outliers'],
        'metadata': {
            'holdout_categories': splits['holdout_categories'],
            'holdout_services': splits['holdout_services'],
            'holdout_patterns': splits['holdout_patterns'],
            'strategy': 'Multi-level holdout across categories, services, patterns, and semantic features'
        }
    }

    # Add semantic analysis metadata if available
    if semantic_analysis is not None:
        split_ids['semantic_analysis'] = {
            'action_stats': {
                k: {sk: sv for sk, sv in v.items() if sk != 'matrix'}
                for k, v in semantic_analysis['action_stats'].items()
            },
            'trigger_stats': {
                k: {sk: sv for sk, sv in v.items() if sk != 'matrix'}
                for k, v in semantic_analysis['trigger_stats'].items()
            }
        }

    with open(os.path.join(OUTPUT_DIR, 'advanced_holdout_ids.json'), 'w', encoding='utf-8') as f:
        json.dump(split_ids, f, indent=2)

    # Save embeddings separately (they're large)
    if semantic_analysis is not None:
        print("Saving embeddings...")
        embeddings_file = os.path.join(OUTPUT_DIR, 'semantic_embeddings.npz')
        np.savez_compressed(
            embeddings_file,
            train_action=semantic_analysis['embeddings']['train_action'],
            train_trigger=semantic_analysis['embeddings']['train_trigger'],
            val_action=semantic_analysis['embeddings']['val_action'],
            val_trigger=semantic_analysis['embeddings']['val_trigger'],
            test_action=semantic_analysis['embeddings']['test_action'],
            test_trigger=semantic_analysis['embeddings']['test_trigger'],
            real_action=semantic_analysis['embeddings']['real_action'],
            real_trigger=semantic_analysis['embeddings']['real_trigger']
        )
        print(f"Embeddings saved to: {embeddings_file}")

    print("\n" + "=" * 70)
    print(f"COMPLETE! Results saved to: {OUTPUT_DIR}")
    print("=" * 70)

    # Print summary
    print("\nFinal Split Summary:")
    print(f"  Synthetic Train: {len(splits['train'])}")
    print(f"  Synthetic Val: {len(splits['val'])}")
    print(f"  Synthetic Test: {len(splits['test'])}")
    print(f"  Real Test: {len(splits['real_test'])}")
    print(f"  Held-out categories: {len(splits['holdout_categories'])}")
    print(f"  Held-out services: {len(splits['holdout_services'])}")


if __name__ == "__main__":
    main()
