"""
Scores GenAI tools on a 0-6 scale based on:
  - Website alive (HTTP HEAD/GET):     up to 2.0
  - Recent Google News mentions (6mo): up to 4.0 (normalised at 4 mentions)

Below DEFUNCT_THRESHOLD (1.5), a tool is considered dead and removed.
A hard-coded DEFUNCT_BLOCKLIST short-circuits known-dead tools without
hitting the network.
"""

import time
import urllib.parse
from xml.etree import ElementTree as ET

import requests

from . import cache

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFUNCT_THRESHOLD = 1.5
MAX_SCORE = 6.0

WEBSITE_POINTS = 2.0
NEWS_POINTS = 4.0
NEWS_FULL_SCORE_AT = 4  # 4+ news mentions = full 4.0 news points

HTTP_TIMEOUT = 8  # seconds
REQUEST_DELAY = 0.4  # polite delay between requests
USER_AGENT = (
    "Mozilla/5.0 (compatible; GenAIWheelBot/1.0; "
    "+https://www.imd.org/centers/digital-ai-transformation-center)"
)

DEFUNCT_BLOCKLIST = {
    # Tools confirmed shut down. Add new entries as services close.
    "Jasper Chat",   # chat product discontinued (Jasper itself continues as a writing platform)
    "Clockwise",     # Acquihired by Salesforce, shut down March 27, 2026
}


# ---------------------------------------------------------------------------
# Signal 1: website alive check
# ---------------------------------------------------------------------------

def _website_alive_score(url):
    """Return WEBSITE_POINTS if site responds with non-5xx, else 0."""
    if not url:
        return 0.0
    headers = {"User-Agent": USER_AGENT}
    try:
        resp = requests.head(url, headers=headers, timeout=HTTP_TIMEOUT, allow_redirects=True)
        if resp.status_code == 405 or resp.status_code >= 400:
            # Some servers block HEAD — fall back to GET
            resp = requests.get(url, headers=headers, timeout=HTTP_TIMEOUT, allow_redirects=True, stream=True)
            resp.close()
        if resp.status_code < 500:
            return WEBSITE_POINTS
    except requests.RequestException:
        pass
    return 0.0


# ---------------------------------------------------------------------------
# Signal 2: Google News mentions in the last 6 months
# ---------------------------------------------------------------------------

def _news_mentions(tool_name):
    """
    Count Google News RSS items in the last 6 months for `"{tool_name} AI"`.
    Returns an int (>=0). Returns 0 on any network/parse error.
    """
    query = f'"{tool_name}" AI'
    encoded = urllib.parse.quote(query)
    # when:6m restricts to last 6 months
    rss_url = (
        f"https://news.google.com/rss/search?q={encoded}+when:6m"
        f"&hl=en-US&gl=US&ceid=US:en"
    )
    headers = {"User-Agent": USER_AGENT}
    try:
        resp = requests.get(rss_url, headers=headers, timeout=HTTP_TIMEOUT)
        if resp.status_code != 200:
            return 0
        root = ET.fromstring(resp.content)
        # RSS items live under channel/item
        items = root.findall(".//item")
        return len(items)
    except (requests.RequestException, ET.ParseError):
        return 0


def _news_score(tool_name):
    count = _news_mentions(tool_name)
    if count <= 0:
        return 0.0
    if count >= NEWS_FULL_SCORE_AT:
        return NEWS_POINTS
    return NEWS_POINTS * (count / NEWS_FULL_SCORE_AT)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def score_tool(name, url, use_cache=True):
    """
    Compute a 0-6 relevance score for a single tool.

    Hits the cache first (24-hour TTL). Blocklisted tools score 0.
    """
    if name in DEFUNCT_BLOCKLIST:
        return 0.0

    if use_cache:
        cached = cache.get(name)
        if cached is not None:
            return cached

    site = _website_alive_score(url)
    time.sleep(REQUEST_DELAY)
    news = _news_score(name)
    time.sleep(REQUEST_DELAY)

    total = round(site + news, 2)
    cache.set_score(name, total)
    return total


def is_defunct(score):
    """A tool is defunct if it scores below the threshold."""
    return score < DEFUNCT_THRESHOLD
