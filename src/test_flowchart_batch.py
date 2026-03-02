"""
Batch visual test — render flowcharts for real applets and generate
a single HTML report for manual inspection.

Usage:
    python -m src.test_flowchart_batch [--limit N] [--lang it|en] [--only-mixed]
"""
import json, sys, time, argparse
from pathlib import Path

# ── paths ──────────────────────────────────────────────────
_BASE = Path(__file__).resolve().parent.parent
DATASET      = _BASE / "data" / "dataset" / "applets" / "applets_synt_new_final.jsonl"
TRIGGERS_PATH = _BASE / "data" / "ifttt_catalog" / "triggers.json"
ACTIONS_PATH  = _BASE / "data" / "ifttt_catalog" / "actions.json"
OUTPUT_FILE   = _BASE / "test_flowchart_report.html"

# ── imports ────────────────────────────────────────────────
from src.code_parsing.feedback import run_l1_validation
from src.code_parsing.catalog_validator import build_display_labels
from src.code_parsing.flowchart import render_flowchart_html

# ── load catalog once ──────────────────────────────────────
with open(TRIGGERS_PATH, "r", encoding="utf-8") as f:
    ALL_TRIGGERS = json.load(f)
with open(ACTIONS_PATH, "r", encoding="utf-8") as f:
    ALL_ACTIONS = json.load(f)

TRIGGER_INDEX = {t["api_endpoint_slug"]: t for t in ALL_TRIGGERS}
ACTION_INDEX  = {a["api_endpoint_slug"]: a for a in ALL_ACTIONS}


def load_records(path: Path, limit: int = 0):
    with open(path, "r", encoding="utf-8") as f:
        records = [json.loads(line) for line in f if line.strip()]
    if limit > 0:
        records = records[:limit]
    return records


def process_record(rec: dict, lang: str):
    """Run L1 + build display labels + render both views."""
    code = rec.get("filter_code", "")
    trigger_slugs = rec.get("trigger_apis", [])
    action_slugs  = rec.get("action_apis", [])

    # L1
    l1 = run_l1_validation(
        code=code,
        trigger_slugs=trigger_slugs,
        action_slugs=action_slugs,
        lang=lang,
    )
    if not l1.syntax_ok or not l1.outcomes_raw:
        return None

    # display labels
    triggers = [TRIGGER_INDEX[s] for s in trigger_slugs if s in TRIGGER_INDEX]
    actions  = [ACTION_INDEX[s]  for s in action_slugs  if s in ACTION_INDEX]
    display_labels = build_display_labels(triggers, actions, trigger_slugs, action_slugs)

    # classify
    has_skip    = any(o.get("skip") for o in l1.outcomes_raw)
    has_setters = any(not o.get("skip") for o in l1.outcomes_raw)
    n_outcomes  = len(l1.outcomes_raw)

    # render both views
    html_non_expert = render_flowchart_html(
        l1.outcomes_raw, lang=lang, user_type="non_expert",
        display_labels=display_labels,
    )
    html_expert = render_flowchart_html(
        l1.outcomes_raw, lang=lang, user_type="expert",
        display_labels=display_labels,
    )

    return {
        "id": rec.get("id", "?"),
        "name": rec.get("name", ""),
        "description": rec.get("rule_description", rec.get("description", "")),
        "n_outcomes": n_outcomes,
        "has_skip": has_skip,
        "has_setters": has_setters,
        "is_mixed": has_skip and has_setters,
        "html_non_expert": html_non_expert,
        "html_expert": html_expert,
        "outcomes_raw": l1.outcomes_raw,
    }


# ── HTML report template ──────────────────────────────────
_REPORT_CSS = """
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
       margin: 0; padding: 20px; background: #f5f5f5; }
.stats { background: #fff; padding: 16px 20px; border-radius: 8px;
         margin-bottom: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
.stats h2 { margin: 0 0 8px; }
.stats table { border-collapse: collapse; }
.stats td { padding: 4px 16px 4px 0; }
.applet-card { background: #fff; border-radius: 10px; padding: 20px;
               margin-bottom: 16px; box-shadow: 0 1px 4px rgba(0,0,0,0.08); }
.applet-header { display: flex; gap: 12px; align-items: baseline; margin-bottom: 8px; }
.applet-id { font-size: 11px; color: #888; font-family: monospace; }
.applet-name { font-weight: 700; font-size: 15px; }
.applet-desc { font-size: 13px; color: #555; margin-bottom: 12px; line-height: 1.4; }
.tags { display: flex; gap: 6px; margin-bottom: 12px; }
.tag { font-size: 10px; font-weight: 700; padding: 2px 8px; border-radius: 10px;
       text-transform: uppercase; letter-spacing: 0.5px; }
.tag-skip { background: #fce4ec; color: #c62828; }
.tag-setter { background: #e8f5e9; color: #2e7d32; }
.tag-mixed { background: #fff3e0; color: #e65100; }
.tag-paths { background: #e3f2fd; color: #1565c0; }
.views { display: flex; gap: 16px; }
.view-col { flex: 1; min-width: 0; }
.view-label { font-size: 11px; font-weight: 700; color: #888;
              text-transform: uppercase; letter-spacing: 0.8px; margin-bottom: 6px; }
.view-frame { border: 1px solid #e0e0e0; border-radius: 8px; overflow: hidden; }
.view-frame iframe { width: 100%; border: none; }
.filter-bar { display: flex; gap: 8px; margin-bottom: 16px; flex-wrap: wrap; }
.filter-btn { padding: 6px 14px; border-radius: 16px; border: 1px solid #ccc;
              background: #fff; cursor: pointer; font-size: 12px; font-weight: 600; }
.filter-btn.active { background: #1565c0; color: #fff; border-color: #1565c0; }
"""

_REPORT_JS = """
function filterCards(type) {
    document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
    event.target.classList.add('active');
    document.querySelectorAll('.applet-card').forEach(card => {
        if (type === 'all') { card.style.display = ''; return; }
        card.style.display = card.dataset.tags.includes(type) ? '' : 'none';
    });
}
function autoResize(iframe) {
    try {
        iframe.style.height = iframe.contentDocument.documentElement.scrollHeight + 'px';
    } catch(e) { iframe.style.height = '400px'; }
}
"""


def build_report_html(results: list, stats: dict, lang: str) -> str:
    cards = []
    for r in results:
        tags_html = []
        tag_list = []
        if r["is_mixed"]:
            tags_html.append('<span class="tag tag-mixed">guard+action</span>')
            tag_list.append("mixed")
        elif r["has_skip"]:
            tags_html.append('<span class="tag tag-skip">skip only</span>')
            tag_list.append("skip")
        else:
            tags_html.append('<span class="tag tag-setter">setter only</span>')
            tag_list.append("setter")
        tags_html.append(f'<span class="tag tag-paths">{r["n_outcomes"]} paths</span>')
        if r["n_outcomes"] >= 3:
            tag_list.append("multi")

        # Encode flowchart HTML as srcdoc for iframes
        import html as htmlmod
        srcdoc_ne = htmlmod.escape(r["html_non_expert"])
        srcdoc_ex = htmlmod.escape(r["html_expert"])

        card = f"""
        <div class="applet-card" data-tags="{' '.join(tag_list)}">
          <div class="applet-header">
            <span class="applet-id">#{r['id']}</span>
            <span class="applet-name">{htmlmod.escape(r['name'][:80])}</span>
          </div>
          <div class="applet-desc">{htmlmod.escape(r['description'][:200])}</div>
          <div class="tags">{''.join(tags_html)}</div>
          <div class="views">
            <div class="view-col">
              <div class="view-label">Non-Expert</div>
              <div class="view-frame">
                <iframe srcdoc="{srcdoc_ne}" onload="autoResize(this)"></iframe>
              </div>
            </div>
            <div class="view-col">
              <div class="view-label">Expert</div>
              <div class="view-frame">
                <iframe srcdoc="{srcdoc_ex}" onload="autoResize(this)"></iframe>
              </div>
            </div>
          </div>
        </div>"""
        cards.append(card)

    stats_html = f"""
    <div class="stats">
      <h2>Flowchart Batch Test Report</h2>
      <table>
        <tr><td>Total records</td><td><strong>{stats['total']}</strong></td></tr>
        <tr><td>Parsed OK</td><td><strong>{stats['parsed']}</strong> ({100*stats['parsed']/max(stats['total'],1):.1f}%)</td></tr>
        <tr><td>With outcomes</td><td><strong>{stats['with_outcomes']}</strong></td></tr>
        <tr><td>Mixed (guard+action)</td><td><strong>{stats['mixed']}</strong></td></tr>
        <tr><td>Skip only</td><td><strong>{stats['skip_only']}</strong></td></tr>
        <tr><td>Setter only</td><td><strong>{stats['setter_only']}</strong></td></tr>
        <tr><td>3+ paths</td><td><strong>{stats['multi_path']}</strong></td></tr>
      </table>
    </div>"""

    filter_bar = """
    <div class="filter-bar">
      <button class="filter-btn active" onclick="filterCards('all')">All</button>
      <button class="filter-btn" onclick="filterCards('mixed')">Guard + Action</button>
      <button class="filter-btn" onclick="filterCards('skip')">Skip Only</button>
      <button class="filter-btn" onclick="filterCards('setter')">Setter Only</button>
      <button class="filter-btn" onclick="filterCards('multi')">3+ Paths</button>
    </div>"""

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Flowchart Batch Test</title>
<style>{_REPORT_CSS}</style></head>
<body>
{stats_html}
{filter_bar}
{''.join(cards)}
<script>{_REPORT_JS}</script>
</body></html>"""


def main():
    parser = argparse.ArgumentParser(description="Batch flowchart visual test")
    parser.add_argument("--limit", type=int, default=100,
                        help="Max records to process (0 = all)")
    parser.add_argument("--lang", default="it", choices=["it", "en"])
    parser.add_argument("--only-mixed", action="store_true",
                        help="Only include applets with both skip and setter paths")
    args = parser.parse_args()

    print(f"Loading dataset from {DATASET}...")
    records = load_records(DATASET, limit=args.limit)
    print(f"Loaded {len(records)} records")

    results = []
    stats = {"total": len(records), "parsed": 0, "with_outcomes": 0,
             "mixed": 0, "skip_only": 0, "setter_only": 0, "multi_path": 0}

    t0 = time.time()
    for i, rec in enumerate(records):
        if (i + 1) % 50 == 0:
            print(f"  [{i+1}/{len(records)}]...")
        r = process_record(rec, args.lang)
        if r is None:
            continue
        stats["parsed"] += 1
        stats["with_outcomes"] += 1
        if r["is_mixed"]:
            stats["mixed"] += 1
        elif r["has_skip"]:
            stats["skip_only"] += 1
        else:
            stats["setter_only"] += 1
        if r["n_outcomes"] >= 3:
            stats["multi_path"] += 1

        if args.only_mixed and not r["is_mixed"]:
            continue
        results.append(r)

    elapsed = time.time() - t0
    print(f"Processed in {elapsed:.1f}s — {stats['parsed']} parsed, "
          f"{stats['mixed']} mixed, {stats['multi_path']} multi-path")
    print(f"Rendering {len(results)} flowcharts to report...")

    html = build_report_html(results, stats, args.lang)
    OUTPUT_FILE.write_text(html, encoding="utf-8")
    print(f"Report saved to {OUTPUT_FILE}")
    print(f"Open in browser: file:///{OUTPUT_FILE.as_posix()}")


if __name__ == "__main__":
    main()
