"""
v2 update orchestrator.

Differences from v1:
  - Cap is configurable (default 6, was hard-coded 8)
  - Uses 0–10 multi-signal score (was 0–6 binary+count)
  - Aggressive rotation: drops the lowest-scoring tool below FADING_THRESHOLD
    on every run (not just defunct ones)
  - Replacement: if a candidate scores higher than the lowest current tool
    by a SWAP_MARGIN, it replaces that tool
  - Returns detailed change log with score breakdowns for the cron log file
"""

from . import relevance_v2 as relevance
from . import sources_v2 as sources
from . import popularity
from datetime import datetime, timezone

DEFAULT_CAP = 6
SWAP_MARGIN = 1.5     # candidate must beat the worst current tool by 1.5+ to swap


def _score_all_existing(category_name, tools):
    """Score every current tool. Return list of (tool, score_dict)."""
    out = []
    for tool in tools:
        sd = relevance.score_tool(tool["name"], tool["url"], category_name)
        out.append((tool, sd))
    return out


def _drop_fading(scored, log):
    """Remove tools that are fading/defunct. Return kept list."""
    kept = []
    for tool, sd in scored:
        if relevance.is_fading(sd):
            reason = "SHUTDOWN" if sd["shutdown_detected"] else f"score={sd['score']}"
            log.append(f"  - DROP    {tool['name']:<22} ({reason})")
        else:
            kept.append((tool, sd))
    return kept


def _enforce_cap(kept, cap, log):
    """If over cap, drop the lowest-scoring kept tools until we're at cap."""
    if len(kept) <= cap:
        return kept
    kept.sort(key=lambda x: -x[1]["score"])
    over = kept[cap:]
    for tool, sd in over:
        log.append(f"  - TRIM    {tool['name']:<22} (score={sd['score']}, over cap)")
    return kept[:cap]


def _discover_and_score(category_name, kept, log):
    """Find new candidates and score them; return sorted by score desc."""
    existing_names = [t["name"] for t, _ in kept]
    candidates = sources.discover_candidates(category_name, existing_names)
    scored_candidates = []
    for name, url in candidates:
        sd = relevance.score_tool(name, url, category_name)
        if not relevance.is_fading(sd):
            scored_candidates.append(({"name": name, "url": url}, sd))
    scored_candidates.sort(key=lambda x: -x[1]["score"])
    return scored_candidates


def _fill_and_swap(kept, candidates, cap, log):
    """Fill empty slots, then consider swaps."""
    open_slots = cap - len(kept)
    kept_names = {t["name"] for t, _ in kept}

    # Fill open slots first
    while open_slots > 0 and candidates:
        cand, sd = candidates.pop(0)
        if cand["name"] in kept_names:
            continue  # already in kept, skip
        kept.append((cand, sd))
        kept_names.add(cand["name"])
        log.append(f"  + ADD     {cand['name']:<22} (score={sd['score']})")
        open_slots -= 1

    # Then consider swaps: if a remaining candidate beats the worst-kept
    # tool by SWAP_MARGIN, swap them.
    while candidates:
        if not kept:
            break
        kept.sort(key=lambda x: x[1]["score"])
        worst_tool, worst_sd = kept[0]
        cand, cand_sd = candidates[0]
        if cand["name"] in kept_names:
            candidates.pop(0)
            continue
        if cand_sd["score"] - worst_sd["score"] >= SWAP_MARGIN:
            log.append(
                f"  ↔ SWAP    {worst_tool['name']} (score={worst_sd['score']}) "
                f"→ {cand['name']} (score={cand_sd['score']})"
            )
            kept_names.remove(worst_tool["name"])
            kept[0] = (cand, cand_sd)
            kept_names.add(cand["name"])
            candidates.pop(0)
        else:
            break

    return kept


def _global_dedup(new_categories, scores_by_cat, log, cap):
    """
    Enforce unique-category assignment for each tool.

    If a tool name appears in 2+ categories, keep it only in the category
    where it scored highest; remove the duplicates from the others. Any slots
    that open up as a result are then refilled by the standard discovery +
    swap pipeline.

    Tie-breaking: if scores are exactly equal across categories, keep the
    one whose category appears first in tools.json (deterministic).
    """
    # Find duplicates: name → [(cat_idx, tool_dict, score), ...]
    tool_locations = {}
    for ci, cat in enumerate(new_categories):
        for tool in cat["tools"]:
            sd = scores_by_cat.get((tool["name"], cat["name"]))
            score = sd["score"] if sd else 0.0
            tool_locations.setdefault(tool["name"], []).append((ci, tool, score))

    duplicates = {n: locs for n, locs in tool_locations.items() if len(locs) > 1}
    if not duplicates:
        return new_categories, []

    log.append("\n[Global dedup]")
    removed_from_categories = []  # (cat_idx, category_name) where we lost a tool
    for name, locs in duplicates.items():
        # Sort by (score desc, original cat order asc) → keep first
        locs.sort(key=lambda x: (-x[2], x[0]))
        winner = locs[0]
        losers = locs[1:]
        loser_names = ", ".join(
            f"'{new_categories[l[0]]['name']}'" for l in losers
        )
        log.append(
            f"  ◆ DEDUP   {name}: keep in '{new_categories[winner[0]]['name']}' "
            f"(score={winner[2]}); remove from {loser_names}"
        )
        for cat_idx, tool, _ in losers:
            new_categories[cat_idx]["tools"] = [
                t for t in new_categories[cat_idx]["tools"]
                if t["name"] != name
            ]
            removed_from_categories.append(
                (cat_idx, new_categories[cat_idx]["name"])
            )

    return new_categories, removed_from_categories


def _refill_after_dedup(new_categories, removed_locations, log, cap):
    """After dedup, some categories may be below cap. Try to refill them."""
    if not removed_locations:
        return new_categories
    for cat_idx, cat_name in removed_locations:
        kept_tools = new_categories[cat_idx]["tools"]
        if len(kept_tools) >= cap:
            continue
        log.append(f"\n[Refill after dedup: {cat_name}]")
        # Rebuild scored-kept list to feed into _fill_and_swap
        kept_scored = []
        for t in kept_tools:
            sd = relevance.score_tool(t["name"], t["url"], cat_name)
            kept_scored.append((t, sd))
        # Discover new candidates excluding everything globally assigned
        all_assigned_names = {
            t["name"] for cat in new_categories for t in cat["tools"]
        }
        candidates = sources.discover_candidates(cat_name, all_assigned_names)
        scored_candidates = []
        for cname, curl in candidates:
            sd = relevance.score_tool(cname, curl, cat_name)
            if not relevance.is_fading(sd):
                scored_candidates.append(({"name": cname, "url": curl}, sd))
        scored_candidates.sort(key=lambda x: -x[1]["score"])
        kept_scored = _fill_and_swap(kept_scored, scored_candidates, cap, log)
        kept_scored.sort(key=lambda x: -x[1]["score"])
        new_categories[cat_idx]["tools"] = [t for t, _ in kept_scored]

    return new_categories


def update(tools_data, cap=DEFAULT_CAP):
    """Run v2 update. Return (new_data, log_lines)."""
    log = [f"== v2 update, cap={cap}, threshold={relevance.FADING_THRESHOLD} =="]
    new_categories = []
    scores_by_cat = {}  # (tool_name, category_name) -> score_dict

    for category in tools_data["categories"]:
        name = category["name"]
        log.append(f"\n[{name}] currently {len(category['tools'])}")

        scored = _score_all_existing(name, category["tools"])
        kept = _drop_fading(scored, log)
        kept = _enforce_cap(kept, cap, log)
        candidates = _discover_and_score(name, kept, log)
        kept = _fill_and_swap(kept, candidates, cap, log)

        # Sort kept by score desc for stable, readable output
        kept.sort(key=lambda x: -x[1]["score"])
        log.append(f"  → final: {len(kept)} tools, avg score "
                   f"{sum(sd['score'] for _, sd in kept)/max(len(kept),1):.2f}")

        # Track scores so the dedup pass can compare across categories
        for tool, sd in kept:
            scores_by_cat[(tool["name"], name)] = sd

        new_categories.append({
            "name": name,
            "tools": [t for t, _ in kept],
        })

    # Global dedup: each tool name lives in exactly one category
    new_categories, removed_locations = _global_dedup(
        new_categories, scores_by_cat, log, cap
    )
    new_categories = _refill_after_dedup(new_categories, removed_locations, log, cap)

    # Record this run for momentum tracking on future runs
    timestamp = datetime.now(timezone.utc).isoformat()
    popularity.record_run(scores_by_cat, timestamp)

    # Compute popularity index per category and tag the top tools
    scored_by_cat_for_popularity = {}
    for cat in new_categories:
        scored_by_cat_for_popularity[cat["name"]] = [
            (t, scores_by_cat.get((t["name"], cat["name"]), {}))
            for t in cat["tools"]
        ]
    highlights = popularity.pick_top_per_category(scored_by_cat_for_popularity)

    log.append("\n[Popularity highlights]")
    for cat in new_categories:
        top_names = highlights.get(cat["name"], [])
        # Tag tools (and untag the rest) so the renderer can draw the ring
        for t in cat["tools"]:
            t["highlighted"] = (t["name"] in top_names)
        # Log the choice and the index gap context
        if top_names:
            tag = " + ".join(top_names) if len(top_names) > 1 else top_names[0]
            log.append(f"  ★ {cat['name']:<40} → {tag}")
        else:
            log.append(f"  · {cat['name']:<40} → (none)")

    return {"categories": new_categories}, log
