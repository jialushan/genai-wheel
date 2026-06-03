"""
v2 candidate discovery.

Three sources, combined and deduped:
  1. Curated reference list (scraper/reference.py) — high signal, low noise
  2. Google News domain extraction — surfaces new `.ai`/`.io`/`.app` startups
     mentioned in category-relevant news headlines
  3. Reddit category-thread scraping — surfaces practitioner favorites that
     don't always make press coverage

Each candidate is just (name, url). Scoring happens in the updater.
"""

import re
import time
import urllib.parse
from xml.etree import ElementTree as ET

import requests

from .reference import tools_for_category

USER_AGENT = (
    "Mozilla/5.0 (compatible; GenAIWheelBot/2.0; "
    "+https://www.imd.org/centers/digital-ai-transformation-center)"
)
HTTP_TIMEOUT = 4    # Tight timeout to bound runtime on rate-limited IPs.
REQUEST_DELAY = 0.4

DOMAIN_PATTERN = re.compile(
    r"\b([a-zA-Z][a-zA-Z0-9\-]{1,40})\.(ai|io|app)\b",
    re.IGNORECASE,
)

# Domains we never want to propose as candidate tools
BLOCKED_DOMAINS = {
    "google.com", "news.google.com", "youtube.com", "twitter.com", "x.com",
    "facebook.com", "linkedin.com", "github.com", "medium.com",
    "reddit.com", "wikipedia.org",
    "openai.com", "anthropic.com",
}

# Single-word stubs that are usually not real product names
BLOCKED_STUBS = {"www", "news", "rss", "blog", "docs", "api", "app", "help"}


def _fetch_news_titles(query, months=3, max_items=40):
    encoded = urllib.parse.quote(query)
    rss_url = (
        f"https://news.google.com/rss/search?q={encoded}+when:{months}m"
        f"&hl=en-US&gl=US&ceid=US:en"
    )
    try:
        resp = requests.get(rss_url, headers={"User-Agent": USER_AGENT}, timeout=HTTP_TIMEOUT)
        if resp.status_code != 200:
            return []
        root = ET.fromstring(resp.content)
        texts = []
        for item in root.findall(".//item")[:max_items]:
            t = item.find("title")
            d = item.find("description")
            buf = ""
            if t is not None and t.text:
                buf += " " + t.text
            if d is not None and d.text:
                buf += " " + d.text
            if buf:
                texts.append(buf)
        return texts
    except (requests.RequestException, ET.ParseError):
        return []


def _extract_domain_candidates(texts):
    seen, out = set(), []
    for text in texts:
        for m in DOMAIN_PATTERN.finditer(text):
            stub = m.group(1).lower()
            tld = m.group(2).lower()
            domain = f"{stub}.{tld}"
            if domain in BLOCKED_DOMAINS or stub in BLOCKED_STUBS:
                continue
            if domain in seen:
                continue
            seen.add(domain)
            name = stub.replace("-", " ").title()
            out.append((name, f"https://{domain}"))
    return out


def _reddit_thread_titles(subreddit, query):
    """
    Use Reddit's old JSON search endpoint (no auth required for public).
    Returns concatenated thread titles + body text.
    """
    url = f"https://old.reddit.com/r/{subreddit}/search.json?q={urllib.parse.quote(query)}&restrict_sr=1&sort=relevance&t=year&limit=20"
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=HTTP_TIMEOUT)
        if resp.status_code != 200:
            return []
        data = resp.json()
        texts = []
        for post in data.get("data", {}).get("children", []):
            d = post.get("data", {})
            buf = (d.get("title") or "") + " " + (d.get("selftext") or "")
            if buf.strip():
                texts.append(buf)
        return texts
    except (requests.RequestException, ValueError):
        return []


# Per-category Reddit subreddits where practitioners discuss tools
CATEGORY_SUBREDDITS = {
    "Agentic AI": ["LocalLLaMA", "AI_Agents"],
    "Chatbot": ["singularity", "OpenAI"],
    "Conducting research": ["AcademicResearch", "PhD"],
    "Creating and editing images": ["StableDiffusion", "midjourney"],
    "Creating and editing presentations": ["productivity"],
    "Creating and editing sound": ["AIMusic", "WeAreTheMusicMakers"],
    "Creating and editing text": ["writing", "ChatGPT"],
    "Creating and editing video": ["aivideo", "StableDiffusion"],
    "Email management": ["productivity", "Office365"],
    "Learning and education": ["edtech", "Teachers"],
    "Scheduling management": ["productivity", "GetMotivated"],
    "Task automation": ["automation", "nocode"],
    "Transcription": ["productivity", "podcasting"],
    "Translation and localization": ["translator"],
    "Writing and analyzing code": ["ChatGPTCoding", "cursor"],
}


def discover_candidates(category_name, existing_names):
    """Return [(name, url), ...] for `category_name` excluding existing_names."""
    existing_lower = {n.lower() for n in existing_names}
    candidates = []
    seen = set()

    # 1. Curated reference list
    for name, url in tools_for_category(category_name):
        k = name.lower()
        if k in existing_lower or k in seen:
            continue
        candidates.append((name, url))
        seen.add(k)

    # 2. Google News domain scrape
    time.sleep(REQUEST_DELAY)
    titles = _fetch_news_titles(f'"{category_name}" AI tool')
    for name, url in _extract_domain_candidates(titles):
        k = name.lower()
        if k in existing_lower or k in seen:
            continue
        candidates.append((name, url))
        seen.add(k)

    # 3. Reddit thread scrape (best practitioner buzz signal)
    for sub in CATEGORY_SUBREDDITS.get(category_name, [])[:1]:
        time.sleep(REQUEST_DELAY)
        texts = _reddit_thread_titles(sub, f"best {category_name} tools")
        for name, url in _extract_domain_candidates(texts):
            k = name.lower()
            if k in existing_lower or k in seen:
                continue
            candidates.append((name, url))
            seen.add(k)

    return candidates
