"""
Discovers candidate GenAI tools for each category.

Two sources:
  1. The curated REFERENCE_TOOLS list (`scraper/reference.py`).
  2. Google News headlines for each category — we scan for `.ai`/`.io`/`.app`
     domains mentioned in news items and propose them as candidates.

Discovered candidates are returned as (name, url) tuples; scoring and final
selection are handled by the updater.
"""

import re
import time
import urllib.parse
from xml.etree import ElementTree as ET

import requests

from .reference import tools_for_category

USER_AGENT = (
    "Mozilla/5.0 (compatible; GenAIWheelBot/1.0; "
    "+https://www.imd.org/centers/digital-ai-transformation-center)"
)
HTTP_TIMEOUT = 8
REQUEST_DELAY = 0.4

# Match domains like example.ai, example.io, example.app (no subdomains kept)
DOMAIN_PATTERN = re.compile(
    r"\b([a-zA-Z][a-zA-Z0-9\-]{1,40})\.(ai|io|app)\b",
    re.IGNORECASE,
)

# Domains we never want to propose (false positives from news boilerplate)
BLOCKED_DOMAINS = {
    "google.com", "news.google.com", "youtube.com", "twitter.com",
    "facebook.com", "linkedin.com", "github.com", "medium.com",
    "openai.com", "anthropic.com",  # Already covered by their flagship products
}


def _category_news_query(category_name):
    """Build a Google News RSS query for a category."""
    return f'"{category_name}" AI tool'


def _fetch_news_titles(query, max_items=30):
    """Fetch Google News RSS item titles for a query (last 3 months)."""
    encoded = urllib.parse.quote(query)
    rss_url = (
        f"https://news.google.com/rss/search?q={encoded}+when:3m"
        f"&hl=en-US&gl=US&ceid=US:en"
    )
    headers = {"User-Agent": USER_AGENT}
    try:
        resp = requests.get(rss_url, headers=headers, timeout=HTTP_TIMEOUT)
        if resp.status_code != 200:
            return []
        root = ET.fromstring(resp.content)
        titles = []
        for item in root.findall(".//item")[:max_items]:
            title_el = item.find("title")
            desc_el = item.find("description")
            text = ""
            if title_el is not None and title_el.text:
                text += " " + title_el.text
            if desc_el is not None and desc_el.text:
                text += " " + desc_el.text
            if text:
                titles.append(text)
        return titles
    except (requests.RequestException, ET.ParseError):
        return []


def _extract_domain_candidates(texts):
    """
    Pull out (name, url) pairs from a list of text blobs.
    Uses naive heuristics: domain stub becomes the name; full domain the URL.
    """
    seen = set()
    candidates = []
    for text in texts:
        for match in DOMAIN_PATTERN.finditer(text):
            stub = match.group(1).lower()
            tld = match.group(2).lower()
            domain = f"{stub}.{tld}"
            if domain in BLOCKED_DOMAINS or stub in {"www", "news", "rss"}:
                continue
            if domain in seen:
                continue
            seen.add(domain)
            name = stub.replace("-", " ").title()
            url = f"https://{domain}"
            candidates.append((name, url))
    return candidates


def discover_candidates(category_name, existing_names):
    """
    Return a list of (name, url) candidates for `category_name` that are not
    already in `existing_names`.

    Combines the curated reference list with live news-scraped domains.
    """
    existing_lower = {n.lower() for n in existing_names}
    candidates = []
    seen_names = set()

    # 1. Curated reference list (high quality, deterministic).
    for name, url in tools_for_category(category_name):
        key = name.lower()
        if key in existing_lower or key in seen_names:
            continue
        candidates.append((name, url))
        seen_names.add(key)

    # 2. Live Google News scrape (best-effort).
    time.sleep(REQUEST_DELAY)
    titles = _fetch_news_titles(_category_news_query(category_name))
    for name, url in _extract_domain_candidates(titles):
        key = name.lower()
        if key in existing_lower or key in seen_names:
            continue
        candidates.append((name, url))
        seen_names.add(key)

    return candidates
