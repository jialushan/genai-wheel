# Cron setup

This directory contains the configuration for running the GenAI wheel
updater on an automatic schedule.

## What runs

`python main.py --quiet` — the v2 pipeline (default), in quiet mode so it
writes a log file but nothing to stdout. The log lives at
`logs/YYYY-MM-DD-HHMM.log` for audit.

## Recommended schedule

**Weekly** is the sweet spot. The GenAI landscape moves fast, but a daily
run wastes resources and creates excessive churn in the chart. Run it
Mondays at 4am, when news activity has had the weekend to settle.

## Setting up cron

```bash
# Open your crontab
crontab -e

# Add this line (adjust the path to where you installed the project):
0 4 * * 1 cd /path/to/genai-wheel && /usr/bin/python3 main.py --quiet >> logs/cron.out 2>&1
```

Field breakdown:
- `0 4 * * 1` = Mondays at 04:00
- `cd /path/to/genai-wheel` = run from the project root (matters for relative paths)
- `/usr/bin/python3` = absolute path to Python (cron doesn't inherit your PATH)
- `--quiet` = no stdout chatter, but the per-run log file is still written
- `>> logs/cron.out 2>&1` = append any unexpected errors to a separate cron log

## Verifying it works

Test the exact command you put in the crontab, run it manually first:

```bash
cd /path/to/genai-wheel && /usr/bin/python3 main.py --quiet
echo "Exit code: $?"
ls -la logs/
```

If exit code is 0 and a new `logs/YYYY-MM-DD-HHMM.log` appears, cron will
work. If exit code is non-zero, fix the error before scheduling.

## Logo refresh

Logos don't change as often as the tool list. Refresh them monthly:

```bash
# Add this to crontab too — first Monday of the month at 4:30am
30 4 1-7 * 1 cd /path/to/genai-wheel && /usr/bin/python3 main.py --refresh-logos --quiet
```

## Monitoring

Each run writes a structured log with score breakdowns:

```
== v2 update, cap=6, threshold=4.0 ==

[Chatbot] currently 8
  - DROP    OldDeadBot             (SHUTDOWN)
  - DROP    FadingChat             (score=2.5)
  ↔ SWAP    DeepSeek (score=6.5) → Mistral Le Chat (score=8.0)
  → final: 6 tools, avg score 8.25
```

Tail the latest log to see what changed:

```bash
ls -t logs/*.log | head -1 | xargs cat
```

## Disk space

Each run produces ~5 KB of log. Over a year of weekly runs that's ~250 KB.
Add a logrotate config or this monthly cleanup line to be tidy:

```bash
# Delete logs older than 6 months
find /path/to/genai-wheel/logs -name "*.log" -mtime +180 -delete
```
