"""
Entry point for the GenAI wheel updater.

Usage:
  python main.py                 # v2 update + render (default)
  python main.py --legacy        # use the v1 pipeline
  python main.py --dry-run       # preview changes; write nothing
  python main.py --render-only   # skip scoring; just regenerate index.html
  python main.py --refresh-logos # download fresh logos, then re-render
  python main.py --cap N         # max tools per category (default 6)
  python main.py --quiet         # suppress progress output (for cron)
"""

import argparse
import json
import os
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from chart import renderer
from scraper import updater          # v1
from scraper import updater_v2       # v2 (default)
from scraper import logos as logos_mod

TOOLS_PATH = os.path.join(ROOT, "data", "tools.json")
OUTPUT_PATH = os.path.join(ROOT, "index.html")
LOG_DIR = os.path.join(ROOT, "logs")


def _load_tools():
    with open(TOOLS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_tools(data):
    with open(TOOLS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _write_run_log(log_lines):
    """Persist a per-run log to logs/YYYY-MM-DD-HHMM.log for cron audit trail."""
    os.makedirs(LOG_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d-%H%M")
    path = os.path.join(LOG_DIR, f"{stamp}.log")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(log_lines) + "\n")
    return path


def main():
    parser = argparse.ArgumentParser(description="Update and render the GenAI productivity wheel.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview what would change without writing anything.")
    parser.add_argument("--render-only", action="store_true",
                        help="Skip scoring; just regenerate index.html from current tools.json.")
    parser.add_argument("--refresh-logos", action="store_true",
                        help="Download fresh logos for every tool into data/logos/, then re-render.")
    parser.add_argument("--legacy", action="store_true",
                        help="Use the v1 scoring pipeline instead of v2 (default is v2).")
    parser.add_argument("--quiet", action="store_true",
                        help="Suppress stdout; only write the log file. Useful for cron.")
    parser.add_argument("--cap", type=int, default=6,
                        help="Max tools per category (v2 only). Default 6.")
    args = parser.parse_args()

    def out(msg=""):
        if not args.quiet:
            print(msg)

    if args.refresh_logos:
        out("Downloading logos for every tool")
        out("(tries logo.dev → brandfetch → google favicon → monogram)\n")
        report = logos_mod.refresh_all()
        out("\nSummary by source:")
        for source, count in sorted(report["by_source"].items(), key=lambda x: -x[1]):
            out(f"  {source:<22} {count}")
        fallback_count = sum(
            n for s, n in report["by_source"].items() if "monogram" in s
        )
        if fallback_count:
            out(f"\n  {fallback_count} tool(s) fell back to monogram (no real logo found).")
        out(f"\nRegenerating chart at {OUTPUT_PATH}")
        renderer.render(TOOLS_PATH, OUTPUT_PATH)
        out("Done.")
        return

    if args.render_only:
        out(f"[render-only] Regenerating chart from {TOOLS_PATH}")
        renderer.render(TOOLS_PATH, OUTPUT_PATH)
        out(f"  → wrote {OUTPUT_PATH}")
        return

    out("Loading current tools…")
    data = _load_tools()

    if args.legacy:
        out("Running v1 scoring + discovery (legacy mode)\n")
        new_data, log = updater.update(data, dry_run=args.dry_run)
    else:
        out(f"Running v2 scoring + discovery (cap={args.cap})\n")
        new_data, log = updater_v2.update(data, cap=args.cap)

    for line in log:
        out(line)

    # Always write run log for audit trail (cron-friendly)
    log_path = _write_run_log(log)
    out(f"\nRun log written to {log_path}")

    if args.dry_run:
        out("\n[dry-run] No files written.")
        return

    out("\nWriting updated tools.json")
    _save_tools(new_data)

    out(f"Rendering chart to {OUTPUT_PATH}")
    renderer.render(TOOLS_PATH, OUTPUT_PATH)
    out("Done.")


if __name__ == "__main__":
    main()
