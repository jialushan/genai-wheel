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
  python main.py --timeout N     # max seconds for scoring phase (default 900)
"""

import argparse
import json
import os
import signal
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


class ScoringTimeout(Exception):
    """Raised when the scoring phase exceeds its overall time budget."""


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


def _run_with_timeout(callable_, timeout_seconds, *args, **kwargs):
    """
    Run `callable_(*args, **kwargs)` with a hard wall-clock timeout.
    Uses SIGALRM, which only works on Unix (which GitHub Actions uses).
    On Windows the timeout is silently ignored — the script will just run
    however long it runs.
    """
    if not hasattr(signal, "SIGALRM"):
        # Windows path — no timeout enforcement
        return callable_(*args, **kwargs)

    def _on_timeout(signum, frame):
        raise ScoringTimeout(
            f"scoring exceeded {timeout_seconds}s budget"
        )

    old_handler = signal.signal(signal.SIGALRM, _on_timeout)
    signal.alarm(timeout_seconds)
    try:
        return callable_(*args, **kwargs)
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old_handler)


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
    parser.add_argument("--timeout", type=int, default=900,
                        help="Max seconds for the scoring phase. Default 900 (15min).")
    args = parser.parse_args()

    # On non-quiet mode, flush stdout aggressively so progress is visible in
    # GitHub Actions logs in real time (default buffering hides it).
    if not args.quiet:
        sys.stdout.reconfigure(line_buffering=True)

    def out(msg=""):
        if not args.quiet:
            print(msg, flush=True)

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

    out(f"Running v{'1 (legacy)' if args.legacy else '2'} scoring + discovery "
        f"(cap={args.cap}, timeout={args.timeout}s)\n")

    try:
        if args.legacy:
            new_data, log = _run_with_timeout(
                updater.update, args.timeout, data, dry_run=args.dry_run
            )
        else:
            new_data, log = _run_with_timeout(
                updater_v2.update, args.timeout, data, cap=args.cap
            )
    except ScoringTimeout as e:
        out(f"\n⚠ {e}")
        out("Falling back to current tools.json without changes.")
        out("(The render step still runs so index.html stays fresh.)")
        new_data, log = data, [f"== TIMEOUT after {args.timeout}s — no changes applied =="]

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
