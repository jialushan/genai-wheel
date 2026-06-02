# Setup guide: GitHub Actions + GitHub Pages

This will give you:

- **Automatic biweekly updates** every other Monday at ~05:00 Geneva time
- **A public URL** for the wheel (e.g. `https://yourusername.github.io/genai-wheel/`)
- **A manual "run now" button** in the GitHub UI for when you want to force a refresh
- **An audit trail** — every run produces a git commit with the changes and a log file

The whole setup takes about 10 minutes.

---

## Step 1 — Create the GitHub repository

If you already have a GitHub account, skip the account-creation parts.

1. Go to https://github.com/new
2. Name it `genai-wheel` (or anything else; the URL will match the name)
3. Set it to **Public** (required for free GitHub Pages on free accounts; Private works on paid plans)
4. Don't initialize with a README — we already have one
5. Click **Create repository**

You'll land on an empty repo page. Keep that tab open; you'll need the URL.

---

## Step 2 — Push this project to the repo

In a terminal on your laptop, in the unzipped `genai-wheel` directory:

```bash
cd genai-wheel
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/YOUR-USERNAME/genai-wheel.git
git push -u origin main
```

Replace `YOUR-USERNAME` with your actual GitHub username.

GitHub may ask you to authenticate. If you don't have a token set up:

- Visit https://github.com/settings/tokens?type=beta
- Generate a new **fine-grained token** scoped to just this repo with "Contents: Read and write"
- Paste it when prompted as your password

---

## Step 3 — Enable GitHub Pages

1. In the repo, click **Settings** (top tab)
2. In the left sidebar, click **Pages**
3. Under **Build and deployment**, set:
   - **Source**: `GitHub Actions`
4. Save (it auto-saves)

Don't worry about choosing a branch — our workflow handles deployment.

---

## Step 4 — Enable Actions to write to the repo

1. Still in **Settings**, click **Actions → General** in the sidebar
2. Scroll to **Workflow permissions** at the bottom
3. Select **Read and write permissions**
4. Click **Save**

This lets the biweekly updater commit its changes back to the repo.

---

## Step 5 — Trigger the first deployment manually

1. Click the **Actions** tab in the repo
2. In the left sidebar, click **Deploy to GitHub Pages**
3. Click the **Run workflow** dropdown → **Run workflow** (green button)
4. Wait ~30 seconds. Refresh the page; you should see a green checkmark.

When complete, your wheel is live at:

```
https://YOUR-USERNAME.github.io/genai-wheel/
```

GitHub usually takes 1-2 minutes after the first deployment for DNS to propagate.

---

## Step 6 — Test the updater (optional but recommended)

1. **Actions** tab → **Biweekly GenAI wheel update** in the sidebar
2. Click **Run workflow** dropdown → **Run workflow** (manual triggers skip the biweekly cadence check, so this runs immediately)
3. Wait 5-15 minutes — it scores ~120 candidates against Google News and refreshes logos
4. When complete, check the repo: there should be a new commit titled `chore: biweekly wheel update (YYYY-MM-DD) [skip ci]`
5. Open `https://YOUR-USERNAME.github.io/genai-wheel/` in a fresh tab — the deployment auto-triggers from the commit, so the page should reflect the update within ~1 minute

---

## What happens automatically from now on

Every Monday at 04:00 UTC (≈ 05:00 Geneva winter / 06:00 summer):

1. GitHub Actions wakes up
2. Checks the ISO week number; if odd, skips. If even, proceeds.
3. Runs `python main.py --quiet`:
   - Scores every current tool
   - Drops defunct/fading ones
   - Discovers new candidates
   - Fills/swaps slots
   - Computes popularity highlights
   - Renders `index.html`
   - Writes a log to `logs/`
4. Commits the changes (`data/tools.json`, `data/score_history.json`, `index.html`, `logs/*.log`)
5. The Pages deployment workflow auto-triggers from the commit
6. Within ~1 minute, the public URL serves the updated wheel

You'll receive an email from GitHub if a run fails — by default Actions emails repo admins on failure.

---

## Monitoring what changed

To see what changed in any given run:

```bash
# In your local clone
git pull
cat logs/$(ls logs/ | tail -1)
```

Or in the GitHub UI: just click the latest commit on the repo's main page — the diff shows you which tools were dropped, added, or swapped.

---

## Adjusting cadence

The biweekly cadence is implemented as:

```yaml
schedule:
  - cron: "0 4 * * 1"    # weekly
# + ISO-week-number check (only EVEN weeks proceed)
```

**To switch to weekly:** delete the entire "Skip if not a target ISO week" step in `.github/workflows/update.yml`.

**To switch to monthly:** change cron to `0 4 1-7 * 1` (first Monday of each month) and delete the cadence check.

**To switch to daily** (not recommended — produces noisy commits): change cron to `0 4 * * *` and delete the cadence check.

---

## Stopping the auto-updates

If you ever want to pause the workflow:

1. **Actions** tab → **Biweekly GenAI wheel update**
2. Click `...` (top right) → **Disable workflow**

Re-enable the same way. Disabling stops scheduled runs but keeps the workflow file intact, so manual triggers still work.

---

## Troubleshooting

**"Workflow runs but commits nothing"** — Could be legitimate (nothing changed) or could mean scoring is broken. Check the log file the run produced for clues.

**"Pages says 404"** — Pages can take up to 10 minutes on first deployment. After that it should be near-instant. If still stuck, **Settings → Pages** and verify the source is set to "GitHub Actions" and a recent deployment shows success.

**"Permission denied to push"** — You missed Step 4. Set workflow permissions to read+write.

**"Runs use a lot of minutes"** — Each run takes 5-15 minutes; biweekly is ~12-24 minutes/month. GitHub free tier gives 2000 min/month — you're using ~1% of it.
