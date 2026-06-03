"""
Relevance scoring v2 — free signals only, no LLM.

Score scale: 0.0–10.0.
Composed of four signals:

  Site alive          0–2 pts   HTTP check + parking-page detection
  News count          0–3 pts   Google News RSS items, last 6 months
  News recency        0–2 pts   Days since most recent article
  Category mentions   0–3 pts   "{name} {category}" news result count

A tool is considered defunct/fading if it scores below FADING_THRESHOLD (4.0)
*or* if the shutdown-keyword scanner finds a "shut down / discontinued /
acquired and folded into" hit in its own news headlines.
"""

import re
import time
import urllib.parse
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree as ET

import requests

from . import cache

# --- Tuning ---------------------------------------------------------------

FADING_THRESHOLD = 4.0
MAX_SCORE = 10.0

SITE_POINTS = 2.0
NEWS_COUNT_POINTS = 3.0
NEWS_RECENCY_POINTS = 2.0
CATEGORY_POINTS = 3.0

NEWS_COUNT_FULL = 6        # 6+ news items in 6mo = full count score
RECENCY_FULL_DAYS = 30     # ≤30 days old = full recency
RECENCY_ZERO_DAYS = 365    # ≥1 year old = zero recency
CATEGORY_FULL = 5          # 5+ category-mention results = full

HTTP_TIMEOUT = 4        # Tighter than v1's 8s — GitHub Actions IPs are
                        # commonly rate-limited by news.google.com to near-
                        # timeout. 4s ensures the whole run finishes in
                        # under 15 minutes even on a fully-throttled IP.
REQUEST_DELAY = 0.4
USER_AGENT = (
    "Mozilla/5.0 (compatible; GenAIWheelBot/2.0; "
    "+https://www.imd.org/centers/digital-ai-transformation-center)"
)

SHUTDOWN_PATTERNS = [
    r"\bshut(?:s|ting)?\s+down\b",
    r"\bdiscontinued\b",
    r"\bsunset(?:ting|ted)?\b",
    r"\bshutting\s+down\b",
    r"\bclosing\s+down\b",
    r"\bend\s+of\s+life\b",
    r"\bceasing\s+operations?\b",
    r"\bclos(?:es|ing|ed)\s+its?\s+(?:doors|services?|operations?)\b",
]
SHUTDOWN_RE = re.compile("|".join(SHUTDOWN_PATTERNS), re.IGNORECASE)

DEFUNCT_BLOCKLIST = {
    "Jasper Chat",
    "Clockwise",  # Acquihired by Salesforce, shut down March 27, 2026
}

PARKING_INDICATORS = [
    "domain is for sale", "buy this domain", "domain parking",
    "this website is for sale", "godaddy", "namecheap parking",
    "sedoparking", "parked free",
]


# --- Site-alive signal ----------------------------------------------------

def _site_alive_score(url):
    """0–2 pts. Returns (score, reason)."""
    if not url:
        return 0.0, "no url"
    headers = {"User-Agent": USER_AGENT}
    try:
        resp = requests.get(
            url, headers=headers, timeout=HTTP_TIMEOUT,
            allow_redirects=True, stream=True,
        )
        if resp.status_code >= 400:
            return 0.0, f"http {resp.status_code}"
        body = b""
        for chunk in resp.iter_content(chunk_size=4096):
            body += chunk
            if len(body) >= 16384:
                break
        resp.close()
        text = body.decode("utf-8", errors="ignore").lower()
        if any(p in text for p in PARKING_INDICATORS):
            return 0.0, "parking page"
        return SITE_POINTS, "alive"
    except requests.RequestException as e:
        return 0.0, f"err: {type(e).__name__}"


# --- News signals ---------------------------------------------------------

def _fetch_news_items(query, months=6):
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
        items = []
        for item in root.findall(".//item"):
            title_el = item.find("title")
            date_el = item.find("pubDate")
            title = title_el.text if title_el is not None and title_el.text else ""
            pub_dt = None
            if date_el is not None and date_el.text:
                try:
                    pub_dt = parsedate_to_datetime(date_el.text)
                except (TypeError, ValueError):
                    pub_dt = None
            items.append((title, pub_dt))
        return items
    except (requests.RequestException, ET.ParseError):
        return []


def _news_signals(tool_name):
    items = _fetch_news_items(f'"{tool_name}" AI', months=6)
    count = len(items)
    count_score = NEWS_COUNT_POINTS * min(count / NEWS_COUNT_FULL, 1.0)

    most_recent = None
    for _, pub_dt in items:
        if pub_dt is None:
            continue
        if most_recent is None or pub_dt > most_recent:
            most_recent = pub_dt

    recency_score = 0.0
    if most_recent is not None:
        days = (datetime.now(timezone.utc) - most_recent).days
        if days <= RECENCY_FULL_DAYS:
            recency_score = NEWS_RECENCY_POINTS
        elif days >= RECENCY_ZERO_DAYS:
            recency_score = 0.0
        else:
            span = RECENCY_ZERO_DAYS - RECENCY_FULL_DAYS
            ratio = 1.0 - (days - RECENCY_FULL_DAYS) / span
            recency_score = NEWS_RECENCY_POINTS * ratio

    shutdown_hit = any(SHUTDOWN_RE.search(title or "") for title, _ in items)
    return round(count_score, 2), round(recency_score, 2), shutdown_hit, count


def _category_mentions(tool_name, category):
    items = _fetch_news_items(f'"{tool_name}" "{category}"', months=6)
    count = len(items)
    score = CATEGORY_POINTS * min(count / CATEGORY_FULL, 1.0)
    return round(score, 2), count


# --- Public API -----------------------------------------------------------

def score_tool(name, url, category, use_cache=True):
    """Compute the v2 score. Returns a dict with all signal breakdowns."""
    if name in DEFUNCT_BLOCKLIST:
        return {
            "score": 0.0, "site": 0.0, "news_count": 0.0, "news_recency": 0.0,
            "category": 0.0, "shutdown_detected": True, "n_news": 0,
            "n_category": 0, "reason": "blocklist",
        }

    cache_key = f"v2:{name}:{category}"
    if use_cache:
        cached = cache.get(cache_key)
        if cached is not None and isinstance(cached, dict):
            return cached

    site, site_reason = _site_alive_score(url)
    time.sleep(REQUEST_DELAY)
    count_s, recency_s, shutdown, n_news = _news_signals(name)
    time.sleep(REQUEST_DELAY)
    cat_s, n_cat = _category_mentions(name, category)
    time.sleep(REQUEST_DELAY)

    total = round(site + count_s + recency_s + cat_s, 2)
    result = {
        "score": total, "site": site,
        "news_count": count_s, "news_recency": recency_s,
        "category": cat_s, "shutdown_detected": shutdown,
        "n_news": n_news, "n_category": n_cat,
        "reason": site_reason,
    }
    cache.set_score(cache_key, result)
    return result


def is_fading(score_dict):
    return score_dict["score"] < FADING_THRESHOLD or score_dict["shutdown_detected"]
