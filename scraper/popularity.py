"""
Popularity index for highlighting "top 2 most popular" tools per category.

This is *separate* from the relevance score used to decide which tools stay
on the wheel. Relevance score = "should this tool be here at all?"; popularity
index = "of the tools that should be here, which two are the most prominent?"

The two questions are correlated but not identical. Examples:
  - A tool can be relevant enough to keep (score 5.5) but not popular enough
    to highlight (z-score below threshold).
  - Two tools can have identical relevance scores but different popularity
    indices if one is more dominant within its category.

Index components (0-10 each, weighted):
  News volume z-score    0.40  How far above category average in news count
  News recency           0.30  Most recent article (favors trending)
  Category dominance     0.20  News results for "{tool} {category}" specifically
  Momentum               0.10  Change since previous run (delta from history)

If the top 2 candidates are too close (z-gap to 3rd place < SIGNIFICANCE),
only top 1 is returned. This avoids highlighting two arbitrary tools when
the category has no clear leader after the #1.
"""

import json
import os
import statistics
from typing import List, Dict, Optional, Tuple

# How weights combine the four signals
WEIGHTS = {
    "volume_z": 0.40,
    "recency":  0.30,
    "dominance": 0.20,
    "momentum": 0.10,
}

# Minimum gap (in popularity index units) between #2 and #3 to justify
# highlighting two tools. Below this, we only highlight #1.
SIGNIFICANCE_GAP = 0.5

# How many runs of history to look at for momentum
MOMENTUM_WINDOW = 4  # ≈1 month of weekly runs

HISTORY_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "score_history.json"
)


def _load_history() -> dict:
    if not os.path.exists(HISTORY_PATH):
        return {}
    try:
        with open(HISTORY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save_history(history: dict) -> None:
    os.makedirs(os.path.dirname(HISTORY_PATH), exist_ok=True)
    with open(HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)


def record_run(scores_by_tool_cat: Dict[Tuple[str, str], dict], timestamp: str) -> None:
    """Append the current run's scores to score_history.json for momentum."""
    history = _load_history()
    snapshot = {}
    for (name, cat), sd in scores_by_tool_cat.items():
        key = f"{name}::{cat}"
        snapshot[key] = sd.get("score", 0.0) if isinstance(sd, dict) else 0.0
    history.setdefault("runs", []).append({
        "timestamp": timestamp,
        "scores": snapshot,
    })
    # Keep only the last 12 runs (≈3 months) to bound file size
    history["runs"] = history["runs"][-12:]
    _save_history(history)


def _momentum_for(name: str, category: str) -> float:
    """
    Compute momentum: average score change over the last MOMENTUM_WINDOW runs.
    Positive = trending up, negative = trending down.
    Scaled so a +2.0 change over the window maps to a +2.0 momentum value.
    """
    history = _load_history()
    runs = history.get("runs", [])[-MOMENTUM_WINDOW:]
    if len(runs) < 2:
        return 0.0
    key = f"{name}::{category}"
    scores = [r["scores"].get(key) for r in runs]
    scores = [s for s in scores if s is not None]
    if len(scores) < 2:
        return 0.0
    # Simple linear-fit slope, scaled
    n = len(scores)
    xs = list(range(n))
    mean_x = sum(xs) / n
    mean_y = sum(scores) / n
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, scores))
    den = sum((x - mean_x) ** 2 for x in xs)
    if den == 0:
        return 0.0
    slope = num / den
    # slope is "score change per run"; multiply by window to get total trend
    return slope * MOMENTUM_WINDOW


def _z_score(value: float, all_values: List[float]) -> float:
    """Z-score of `value` against `all_values`. Returns 0 if zero variance."""
    if len(all_values) < 2:
        return 0.0
    mean = statistics.mean(all_values)
    try:
        stdev = statistics.stdev(all_values)
    except statistics.StatisticsError:
        return 0.0
    if stdev == 0:
        return 0.0
    return (value - mean) / stdev


def _popularity_index(score_dict: dict, all_news_counts: List[int],
                       all_recencies: List[float], name: str, category: str) -> float:
    """Compute single tool's popularity index using the weighted formula."""
    if not isinstance(score_dict, dict):
        return 0.0

    # Z-score the news count against category
    n_news = score_dict.get("n_news", 0)
    z_volume = _z_score(n_news, all_news_counts)
    # Map z=2 → 10, z=-2 → 0
    volume_signal = max(0, min(10, 5 + z_volume * 2.5))

    # Recency: already in 0-2 range, rescale to 0-10
    recency_signal = score_dict.get("news_recency", 0) * 5.0

    # Category dominance: in 0-3 range, rescale to 0-10
    dominance_signal = score_dict.get("category", 0) * (10.0 / 3.0)

    # Momentum: in roughly -5 to +5 range, shift+rescale to 0-10
    momentum_raw = _momentum_for(name, category)
    momentum_signal = max(0, min(10, 5 + momentum_raw))

    return round(
        WEIGHTS["volume_z"]   * volume_signal +
        WEIGHTS["recency"]    * recency_signal +
        WEIGHTS["dominance"]  * dominance_signal +
        WEIGHTS["momentum"]   * momentum_signal,
        3
    )


def pick_top_per_category(scored_tools_by_category: Dict[str, List[Tuple[dict, dict]]]) -> Dict[str, List[str]]:
    """
    For each category, return the tool names that should be highlighted.
    Returns 1, 2, or 0 names per category based on the significance gap.

    Input: {category_name: [(tool_dict, score_dict), ...]}
    Output: {category_name: [name1] or [name1, name2]}
    """
    highlights = {}
    for category, scored in scored_tools_by_category.items():
        if not scored:
            highlights[category] = []
            continue

        # Build the popularity index for each tool in this category
        all_news = [sd.get("n_news", 0) for _, sd in scored]
        all_rec  = [sd.get("news_recency", 0) for _, sd in scored]
        indexed = []
        for tool, sd in scored:
            idx = _popularity_index(sd, all_news, all_rec, tool["name"], category)
            indexed.append((tool["name"], idx))
        indexed.sort(key=lambda x: -x[1])

        # Always highlight #1 (assuming any tools at all)
        chosen = [indexed[0][0]]

        # Check if #2 is significantly above #3
        if len(indexed) >= 3:
            gap_2_to_3 = indexed[1][1] - indexed[2][1]
            if gap_2_to_3 >= SIGNIFICANCE_GAP:
                chosen.append(indexed[1][0])
        elif len(indexed) == 2:
            chosen.append(indexed[1][0])

        highlights[category] = chosen

    return highlights
