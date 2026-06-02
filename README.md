# Generative AI Applications for Better Productivity — Wheel Chart

An auto-updating interactive wheel chart that maps the current landscape of
GenAI tools across 15 productivity categories. Built for the IMD
"Generative AI Applications for Better Productivity" course.

---

## What this is

The chart is a visual reference showing which AI tools are available for each
major productivity use case. It mirrors the wheel diagram used in the IMD
course materials, but as a live HTML page that can be refreshed whenever the
GenAI landscape changes.

Each segment of the wheel represents a category (e.g. "Chatbot", "Transcription",
"Writing and analyzing code"). Within each segment, tool logos are displayed as
clickable circles — hover to see the tool name and URL, click to open the tool
directly.

---

## The 15 categories

| Category | Example tools |
|---|---|
| Agentic AI | Devin, CrewAI, AutoGPT, Copilot Studio |
| Chatbot | ChatGPT, Claude, Gemini, Grok, DeepSeek |
| Conducting research | Perplexity, Elicit, Consensus, NotebookLM |
| Creating and editing images | Midjourney, DALL-E 3, Adobe Firefly, Ideogram |
| Creating and editing presentations | Gamma, Beautiful.ai, MagicSlides |
| Creating and editing sound | ElevenLabs, Suno, Udio, Descript |
| Creating and editing text | Claude, Grammarly, Notion AI, Writer |
| Creating and editing video | Runway, Sora, Pika, HeyGen, Kling AI |
| Email management | Superhuman, Shortwave, Fyxer, SaneBox |
| Learning and education | Khanmigo, Duolingo Max, NotebookLM |
| Scheduling management | Reclaim.ai, Motion, Clockwise, Cal.ai |
| Task automation | Zapier AI, Make, n8n, Bardeen |
| Transcription | Otter.ai, Fireflies, tl;dv, Fathom |
| Translation and localization | DeepL, Lokalise, Phrase, Weglot |
| Writing and analyzing code | GitHub Copilot, Cursor, Windsurf, Amazon Q |

---

## Project structure

```
genai-wheel/
├── main.py                   ← Entry point — run this to update the chart
├── index.html                ← Generated chart (open in any browser)
├── requirements.txt
│
├── data/
│   └── tools.json            ← Source of truth: all 15 categories + tool URLs
│
├── scraper/
│   ├── reference.py          ← Curated list of ~270 known GenAI tools
│   ├── cache.py              ← 24-hour JSON score cache
│   ├── relevance.py          ← Scores tools: website health + Google News mentions
│   ├── sources.py            ← Candidate discovery: reference list + news extraction
│   └── updater.py            ← Core update logic: score → remove defunct → add new
│
└── chart/
    └── renderer.py           ← Generates index.html from tools.json (D3.js wheel)
```

---

## How to update the chart

**Install dependencies once:**

```bash
pip install -r requirements.txt
```

**Run the updater:**

```bash
python main.py
```

This does three things in sequence:

1. **Scores every current tool** — checks whether its website is alive and
   counts how many times it has been mentioned in Google News in the last
   6 months. Tools that score below the relevance threshold are removed.

2. **Finds new tools** — pulls candidates from a curated reference list of
   ~270 known GenAI tools, and also scans Google News headlines for `.ai`,
   `.io`, and `.app` domain names mentioned in each category's news feed.
   New candidates are scored the same way; the highest-scoring ones fill
   any vacant slots (up to 8 tools per category).

3. **Re-renders the chart** — writes a fresh `index.html` with the updated
   tool set. Open it in any browser to see the result.

**Other modes:**

```bash
python main.py --dry-run       # Preview what would change — writes nothing
python main.py --render-only   # Skip scoring; just regenerate index.html
python main.py --refresh-logos # Re-download every tool's logo, then re-render
```

---

## How logos work

Logos are downloaded once and embedded into `index.html` as base64 data
URIs, so the chart is fully self-contained and works offline.

The downloader (`scraper/logos.py`) tries multiple sources for each tool:

1. **Logo.dev** — Clearbit's official successor (Clearbit's free API shut
   down December 2025). Set `LOGO_DEV_KEY` as an environment variable for
   high-volume use; sign up at https://logo.dev.
2. **Brandfetch CDN** — public logo CDN, no key required.
3. **Google Favicon** — low-res fallback for small/obscure tools.
4. **Generated monogram** — final fallback. A circular SVG with the tool's
   initials on an IMD-blue background. Never fails.

Logos live in `data/logos/{slug}.{ext}`. To **manually override** a logo,
just drop a file there (e.g. `data/logos/heygen.png`) and run
`python main.py --render-only`. The renderer will pick it up.

After a logo refresh, the tool prints a summary of which tools fell back
to monograms so you know where manual replacements are most useful.

---

## How relevance is scored

Each tool receives a score out of 6.0:

| Signal | Max points | Method |
|---|---|---|
| Website alive | 2.0 | HTTP HEAD/GET check — returns 2.0 if site responds, 0 if it times out or 5xx |
| Recent news | 4.0 | Google News RSS count for `"{tool name} AI"` in last 6 months, normalised at 4 mentions = full score |

A tool is marked **defunct** (and removed) if its score falls below **1.5**.
This catches tools whose websites have gone dark and that have disappeared
from news coverage.

Confirmed-defunct tools are also maintained in a hard-coded blocklist in
`scraper/relevance.py` so they are skipped entirely without network checks:

```python
DEFUNCT_BLOCKLIST = {
    "Tome",         # shut down March 2025
    "Jasper Chat",  # chat product discontinued
    "Writesonic",   # pivoted/rebranded
}
```

---

## The score cache

Scoring ~270 tools takes roughly 5 minutes on the first run (two HTTP
requests per tool with rate-limiting delays). To avoid repeating this on
every run, scores are cached in `data/.score_cache.json` with a 24-hour TTL.

- **First run:** full scoring (~5 min)
- **Repeat runs within 24 hours:** near-instant (all cached)
- **After 24 hours:** cache expires and everything is re-checked

The cache file is excluded from git via `.gitignore`.

---

## The chart (index.html)

The chart is a single self-contained HTML file generated by `chart/renderer.py`.
It uses D3.js (loaded from CDN) to draw an SVG wheel:

- **Outer ring:** category labels in IMD blue
- **Inner ring:** one circular logo per tool, stacked radially in each segment
- **Logos** are fetched live from Clearbit's logo API, with fallback to
  Google Favicon service, then a letter avatar if both fail
- **Hover** any logo to see the tool name and direct URL
- **Click** any logo to open the tool in a new tab
- Colours match the IMD brand palette: `#0057B8` (dark blue), `#D0E8F5` (light blue)

Because logos are loaded from the web, an internet connection is required
to display them. The chart layout and interactivity work offline.

---

## Maintaining the tool list manually

**To add a tool immediately** (without waiting for the scraper to discover it):

Edit `data/tools.json` and add an entry to the relevant category:

```json
{ "name": "New Tool", "url": "https://newtool.ai" }
```

Then run `python main.py --render-only` to regenerate the chart.

**To add a tool to the candidate pool** (so the scraper considers it on future
runs), add it to the relevant category in `scraper/reference.py`.

**To force-remove a defunct tool immediately**, add its name to
`DEFUNCT_BLOCKLIST` in `scraper/relevance.py`.

---

## Dependencies

| Package | Purpose |
|---|---|
| `requests` | HTTP requests for website checks and Google News RSS |
| `beautifulsoup4` + `lxml` | HTML parsing (used in news extraction) |

No paid APIs are used. Google News RSS and Clearbit logo lookups are both free.
