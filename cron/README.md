# Automated updates with cron

The `update_wheel.sh` script runs the v2 update pipeline and refreshes
logos. It's designed to be safe to run from cron.

## Setup (one-time)

1. **Make sure the script is executable** (already done if you unpacked
   the zip on a Unix system):
   ```bash
   chmod +x cron/update_wheel.sh
   ```

2. **Install dependencies** in the project's virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
   The cron script auto-detects a `.venv/` in the project root.

3. **Test the script manually first** to make sure it works in your env:
   ```bash
   ./cron/update_wheel.sh
   tail -100 cron/logs/$(date +%Y-%m-%d).log
   ```

4. **Add to crontab**: open your crontab with `crontab -e` and add one
   of these lines:

   ```cron
   # Run every Monday at 6 am (recommended cadence)
   0 6 * * 1 /absolute/path/to/genai-wheel/cron/update_wheel.sh

   # Run on the 1st and 15th of each month at 6 am
   0 6 1,15 * * /absolute/path/to/genai-wheel/cron/update_wheel.sh

   # Run daily at 6 am (more aggressive; consumes more bandwidth)
   0 6 * * * /absolute/path/to/genai-wheel/cron/update_wheel.sh
   ```

   Replace `/absolute/path/to/genai-wheel` with the real path. Cron does
   NOT expand `~` or `$HOME` — use a full path.

## What happens on each run

1. **Score every current tool** (0-10 scale) — health, press volume,
   press recency
2. **Tools scoring below 4.0/10 are removed**
3. **Discover new candidates** from the reference list, Google News, and
   roundup articles (Zapier blog, etc. — see `scraper/sources_v2.py`)
4. **Score the candidates**; fill empty slots up to the cap (default 6
   per category) with the highest-scoring ones
5. **Re-render `index.html`**
6. **Refresh logos** (cached if recent)
7. **Append a one-line summary** to `data/update_log.jsonl`

## What gets logged

- `cron/logs/YYYY-MM-DD.log` — full stdout/stderr from the run, kept per
  day for troubleshooting
- `data/update_log.jsonl` — one JSON line per run with what changed:
  ```json
  {"ran_at": "2026-05-29T06:00:00+00:00", "changes": [{"category": "Chatbot", "removed": [], "added": ["Mistral Le Chat"]}]}
  ```

## Concurrency

A lock file at `cron/.update.lock` prevents overlapping runs. If a
previous run is still going when the next one fires, the new run exits
immediately. The lock auto-clears on script exit (including crashes).

## Tuning the pipeline

- **Adjust the cap**: edit `MAX_TOOLS_PER_CATEGORY` in
  `scraper/updater_v2.py`, or pass `--cap N` to `main.py`
- **Adjust the stay threshold**: edit `STAY_THRESHOLD` in
  `scraper/relevance_v2.py` (default 4.0 out of 10)
- **Add roundup sources**: append URLs to `ROUNDUP_SOURCES` in
  `scraper/sources_v2.py` — more sources mean richer discovery
- **Hard-block a defunct tool**: add it to `DEFUNCT_BLOCKLIST` in
  `scraper/relevance_v2.py` to skip it without a network check

## Reverting to v1

If you want the old pipeline back (less aggressive, 8-cap, 1.5
threshold), pass `--legacy` to `main.py`. The cron script uses v2 by
default.
