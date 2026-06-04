"""
Downloads logos for every tool in tools.json to data/logos/{slug}.{ext}.

Tries multiple sources in order until one succeeds:
  1. Logo.dev (img.logo.dev/{domain}) — drop-in Clearbit successor
  2. Brandfetch CDN (cdn.brandfetch.io/{domain}/w/200) — public CDN, no key
  3. Google Favicon service (s2/favicons?sz=128) — last resort, low-res
  4. Generates an SVG monogram as a final fallback

Each tool gets one file in data/logos/. The renderer reads them and embeds
them as base64 data URIs into the final index.html so the chart stays
self-contained.

Usage (via main.py):
    python main.py --refresh-logos
"""

import base64
import json
import os
import re
import time
import urllib.parse
from typing import Optional, Tuple

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGOS_DIR = os.path.join(ROOT, "data", "logos")
TOOLS_PATH = os.path.join(ROOT, "data", "tools.json")

USER_AGENT = (
    "Mozilla/5.0 (compatible; GenAIWheelBot/1.0; "
    "+https://www.imd.org/centers/digital-ai-transformation-center)"
)
HTTP_TIMEOUT = 10
REQUEST_DELAY = 0.3

# Logo.dev publishable key — replace with your own (signup at logo.dev).
# This is a placeholder; leaving it as None falls through to the next source.
LOGO_DEV_KEY = os.environ.get("LOGO_DEV_KEY")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _slug(name: str) -> str:
    """Filesystem-safe slug for a tool name."""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _domain(url: str) -> Optional[str]:
    try:
        return urllib.parse.urlparse(url).hostname.replace("www.", "")
    except Exception:
        return None


def _save(path: str, data: bytes) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)


def _try_fetch(url: str) -> Optional[Tuple[bytes, str]]:
    """Fetch URL; return (bytes, ext) on success, None on failure."""
    try:
        resp = requests.get(
            url, headers={"User-Agent": USER_AGENT},
            timeout=HTTP_TIMEOUT, allow_redirects=True,
        )
        if resp.status_code != 200 or len(resp.content) < 200:
            return None
        ctype = resp.headers.get("Content-Type", "").lower()
        if "svg" in ctype:
            ext = "svg"
        elif "png" in ctype:
            ext = "png"
        elif "jpeg" in ctype or "jpg" in ctype:
            ext = "jpg"
        elif "webp" in ctype:
            ext = "webp"
        elif "ico" in ctype:
            ext = "ico"
        else:
            # Inspect magic bytes
            if resp.content.startswith(b"\x89PNG"):
                ext = "png"
            elif resp.content.startswith(b"GIF8"):
                ext = "gif"
            elif resp.content[:4] == b"RIFF":
                ext = "webp"
            elif resp.content.startswith(b"\xff\xd8\xff"):
                ext = "jpg"
            elif b"<svg" in resp.content[:200]:
                ext = "svg"
            else:
                return None
        return resp.content, ext
    except requests.RequestException:
        return None


# ---------------------------------------------------------------------------
# Source 1: Logo.dev
# ---------------------------------------------------------------------------

def _logo_dev(domain: str) -> Optional[Tuple[bytes, str]]:
    if not LOGO_DEV_KEY:
        return None
    url = f"https://img.logo.dev/{domain}?token={LOGO_DEV_KEY}&size=256&format=png"
    return _try_fetch(url)


# ---------------------------------------------------------------------------
# Source 2: Brandfetch CDN (no key required for the public CDN endpoint)
# ---------------------------------------------------------------------------

def _brandfetch(domain: str) -> Optional[Tuple[bytes, str]]:
    url = f"https://cdn.brandfetch.io/{domain}/w/256/h/256"
    return _try_fetch(url)


# ---------------------------------------------------------------------------
# Source 3: Google favicon (low-res fallback)
# ---------------------------------------------------------------------------

def _google_favicon(domain: str) -> Optional[Tuple[bytes, str]]:
    url = f"https://www.google.com/s2/favicons?sz=128&domain={domain}"
    return _try_fetch(url)


# ---------------------------------------------------------------------------
# Source 4: Generated SVG monogram (final fallback, always succeeds)
# ---------------------------------------------------------------------------

# Soft IMD-palette-friendly color rotation for monograms
_MONOGRAM_BGS = [
    "#0057B8",  # IMD blue
    "#1F73B7",
    "#4A90D0",
    "#2A7DBB",
    "#3E5BA6",
]


def _monogram_svg(name: str, index: int) -> Tuple[bytes, str]:
    # Strip common suffix terms that don't help identify the tool
    cleaned = re.sub(r"\b(AI|\.ai|\.io|\.app|Labs|Inc)\b", "", name, flags=re.I)
    words = [w for w in re.split(r"[\s\-_.]+", cleaned) if w]
    if len(words) >= 2:
        initials = "".join(w[0] for w in words[:2]).upper()
    elif len(words) == 1:
        # Single word — try CamelCase split (ChatGPT -> CG), else first 2 chars
        camel = re.findall(r"[A-Z][a-z]*|[A-Z]+(?=[A-Z]|$)", words[0])
        if len(camel) >= 2:
            initials = (camel[0][0] + camel[1][0]).upper()
        else:
            initials = words[0][:2].upper()
    else:
        initials = name[:2].upper()

    bg = _MONOGRAM_BGS[index % len(_MONOGRAM_BGS)]
    # Shrink the font slightly for 2-char initials so they always fit
    font_size = 42 if len(initials) <= 2 else 32
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
  <circle cx="50" cy="50" r="50" fill="{bg}"/>
  <text x="50" y="50" text-anchor="middle" dominant-baseline="central"
        font-family="-apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif"
        font-size="{font_size}" font-weight="700" fill="#ffffff">{initials}</text>
</svg>"""
    return svg.encode("utf-8"), "svg"


# ---------------------------------------------------------------------------
# Main fetch routine
# ---------------------------------------------------------------------------

SOURCES = [
    ("logo.dev", _logo_dev),
    ("brandfetch", _brandfetch),
    ("favicon", _google_favicon),
]


def fetch_logo(name: str, url: str, index: int) -> Tuple[str, str]:
    """
    Fetch a logo for a single tool; write to data/logos/{slug}.{ext}.
    Returns (source_used, filepath).
    """
    slug = _slug(name)
    domain = _domain(url)
    if not domain:
        data, ext = _monogram_svg(name, index)
        path = os.path.join(LOGOS_DIR, f"{slug}.{ext}")
        _save(path, data)
        return "monogram (no domain)", path

    for source_name, fn in SOURCES:
        result = fn(domain)
        time.sleep(REQUEST_DELAY)
        if result is None:
            continue
        data, ext = result
        path = os.path.join(LOGOS_DIR, f"{slug}.{ext}")
        _save(path, data)
        return source_name, path

    # All real sources failed — generate a monogram
    data, ext = _monogram_svg(name, index)
    path = os.path.join(LOGOS_DIR, f"{slug}.{ext}")
    _save(path, data)
    return "monogram (fallback)", path


def refresh_all() -> dict:
    """Refresh logos for every tool in tools.json. Returns a per-tool report."""
    with open(TOOLS_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    os.makedirs(LOGOS_DIR, exist_ok=True)
    report = {"by_source": {}, "tools": []}
    idx = 0
    total = sum(len(c["tools"]) for c in data["categories"])

    for cat in data["categories"]:
        for tool in cat["tools"]:
            idx += 1
            source, path = fetch_logo(tool["name"], tool["url"], idx)
            report["by_source"][source] = report["by_source"].get(source, 0) + 1
            report["tools"].append({
                "category": cat["name"],
                "name": tool["name"],
                "source": source,
                "path": os.path.relpath(path, ROOT),
            })
            tag = source.ljust(22)
            print(f"  [{idx:>2}/{total}] {tag} {tool['name']}")

    return report


def load_logo_as_data_uri(name: str) -> Optional[str]:
    """Load a saved logo file and return it as a base64 data URI string.

    If multiple files exist for the same slug (e.g. an auto-generated monogram
    `chatgpt.svg` and a manually uploaded `chatgpt.png`), prefer raster
    formats over SVG. Rationale:
      - Our auto-generated monograms are always SVG.
      - User-uploaded real logos are almost always PNG/JPG/WebP.
      - Preferring raster gives a real logo priority over a leftover monogram.
      - Unlike file mtime, this rule is deterministic across `git checkout`
        (where all files get the same mtime), so behaviour is consistent
        between local dev and CI.
    """
    slug = _slug(name)
    # Priority order: raster first, SVG last
    ext_priority = [
        ("png",  "image/png"),
        ("jpg",  "image/jpeg"),
        ("jpeg", "image/jpeg"),
        ("webp", "image/webp"),
        ("gif",  "image/gif"),
        ("ico",  "image/x-icon"),
        ("svg",  "image/svg+xml"),
    ]
    for ext, mime in ext_priority:
        path = os.path.join(LOGOS_DIR, f"{slug}.{ext}")
        if os.path.exists(path):
            with open(path, "rb") as f:
                data = f.read()
            b64 = base64.b64encode(data).decode("ascii")
            return f"data:{mime};base64,{b64}"
    return None
