"""
Core update orchestrator.

Steps performed by `update(tools_data, dry_run=False)`:
  1. Score every current tool. Drop any below the defunct threshold.
  2. For each category, ask sources.discover_candidates() for new candidates.
     Score them and fill empty slots (cap MAX_TOOLS_PER_CATEGORY).
  3. Return the updated structure plus a change log.
"""

from . import relevance
from . import sources

MAX_TOOLS_PER_CATEGORY = 8


def _score_and_filter_existing(category_name, tools, log):
    """Score each tool; keep those at/above threshold."""
    kept = []
    for tool in tools:
        score = relevance.score_tool(tool["name"], tool["url"])
        if relevance.is_defunct(score):
            log.append(f"  - REMOVED {tool['name']} (score={score})")
        else:
            kept.append(tool)
    return kept


def _fill_empty_slots(category_name, kept_tools, log):
    """Score candidates and add the best ones until the category is full."""
    slots_open = MAX_TOOLS_PER_CATEGORY - len(kept_tools)
    if slots_open <= 0:
        return kept_tools

    existing_names = [t["name"] for t in kept_tools]
    candidates = sources.discover_candidates(category_name, existing_names)

    # Score every candidate; only keep ones above threshold
    scored = []
    for name, url in candidates:
        score = relevance.score_tool(name, url)
        if not relevance.is_defunct(score):
            scored.append((score, name, url))

    # Highest scoring first
    scored.sort(key=lambda x: x[0], reverse=True)

    for score, name, url in scored[:slots_open]:
        kept_tools.append({"name": name, "url": url})
        log.append(f"  + ADDED   {name} (score={score})")

    return kept_tools


def update(tools_data, dry_run=False):
    """
    Take the parsed tools.json structure and return (new_data, log_lines).

    If dry_run is True, the returned data is still computed but the caller
    should not write it to disk.
    """
    log = []
    new_categories = []

    for category in tools_data["categories"]:
        name = category["name"]
        log.append(f"\n[{name}]")
        kept = _score_and_filter_existing(name, category["tools"], log)
        filled = _fill_empty_slots(name, kept, log)
        if len(filled) == len(category["tools"]) and not any(
            "REMOVED" in line or "ADDED" in line
            for line in log[log.index(f"\n[{name}]") + 1:]
        ):
            log.append("  (no changes)")
        new_categories.append({"name": name, "tools": filled})

    return {"categories": new_categories}, log
