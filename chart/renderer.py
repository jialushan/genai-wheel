"""
Renders the GenAI productivity wheel as a standalone index.html file.

The generated page uses D3.js (loaded from CDN) to lay out:
  - A dark-blue square canvas
  - A central white circle with the title
  - An inner light-blue ring with 15 category labels (one per segment)
  - An outer ring where each segment displays the tools as circular logos
    laid out radially. Logos load from Clearbit Logo API with fallbacks.

Hovering a logo shows a tooltip (name + URL). Clicking opens the tool.
"""

import base64
import json
import os
from datetime import datetime, timezone

from scraper import logos as logos_mod


HEADER_LOGO_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "logos", "_imd_header.png"
)
CENTER_LOGO_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "logos", "_imd_center.png"
)


def _load_tools(tools_path):
    with open(tools_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _file_as_data_uri(path, mime):
    if not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    return f"data:{mime};base64,{b64}"


def _header_logo_data_uri():
    """Embed the IMD header logo as a base64 data URI. Returns None if missing."""
    return _file_as_data_uri(HEADER_LOGO_PATH, "image/png")


def _center_logo_data_uri():
    """Embed the cropped IMD centre lettermark as a base64 data URI."""
    return _file_as_data_uri(CENTER_LOGO_PATH, "image/png")


def _enrich_with_logos(categories):
    """For each tool, attach a `logo_uri` (data URI) if a cached logo exists.

    Also sets `logo_is_real`: True for user-uploaded or fetched logos,
    False for auto-generated SVG monograms. The renderer uses this to
    decide whether the embedded logo should take priority over live CDN
    fallbacks (real logos: yes; monograms: no).
    """
    import os as _os
    for cat in categories:
        for tool in cat["tools"]:
            uri = logos_mod.load_logo_as_data_uri(tool["name"])
            if uri:
                tool["logo_uri"] = uri
                # Find the source file to inspect size + extension
                slug = logos_mod._slug(tool["name"])
                size = 0
                is_svg_monogram = False
                for ext in ("png", "jpg", "jpeg", "webp", "gif", "ico", "svg"):
                    p = _os.path.join(logos_mod.LOGOS_DIR, f"{slug}.{ext}")
                    if _os.path.exists(p):
                        size = _os.path.getsize(p)
                        # Auto-generated monogram SVGs are ~300-400 bytes.
                        # Real logos are several KB or more.
                        is_svg_monogram = (ext == "svg" and size < 800)
                        break
                tool["logo_is_real"] = not is_svg_monogram
    return categories


def _build_html(tools_data):
    """Build the full HTML document as a string."""
    categories = _enrich_with_logos(tools_data["categories"])
    payload = json.dumps(categories, ensure_ascii=False)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    header_logo = _header_logo_data_uri()
    center_logo = _center_logo_data_uri()
    center_logo_json = json.dumps(center_logo)  # null or "data:..." string

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Generative AI Applications for Better Productivity</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  :root {{
    --imd-blue: #0057B8;
    --imd-light-blue: #D0E8F5;
    --imd-mid-blue: #E8F2FA;
    --text-on-blue: #ffffff;
  }}
  * {{ box-sizing: border-box; }}
  html, body {{
    margin: 0;
    padding: 0;
    background: var(--imd-blue);
    color: var(--text-on-blue);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    min-height: 100vh;
  }}
  .header {{
    padding: 24px 32px 0;
    display: flex;
    align-items: center;
  }}
  .header img.imd-logo {{
    height: 80px;
    width: auto;
    display: block;
  }}
  .wheel-wrap {{
    display: flex;
    justify-content: center;
    align-items: center;
    padding: 16px 16px 32px;
  }}
  svg.wheel {{
    width: 100%;
    max-width: 1000px;
    height: auto;
    display: block;
  }}
  .seg-bg {{ fill: var(--imd-mid-blue); }}
  .seg-bg.alt {{ fill: var(--imd-light-blue); }}
  .seg-divider {{ stroke: var(--imd-blue); stroke-width: 1; fill: none; }}
  .category-label {{
    font-size: 15px;
    fill: var(--imd-blue);
    font-weight: 500;
  }}
  .center-circle {{
    fill: var(--imd-light-blue);
    stroke: var(--imd-blue);
    stroke-width: 2;
  }}
  .center-title {{
    fill: var(--imd-blue);
    font-size: 28px;
    font-weight: 700;
    text-anchor: middle;
  }}
  .center-sub {{
    fill: var(--imd-blue);
    font-size: 13px;
    text-anchor: middle;
    font-weight: 500;
    opacity: 0.85;
  }}
  .tool-circle {{
    fill: #ffffff;
    stroke: var(--imd-blue);
    stroke-width: 1.5;
    cursor: pointer;
    transition: transform 0.15s ease, stroke-width 0.15s ease;
    transform-box: fill-box;
    transform-origin: center;
  }}
  .tool-group:hover .tool-circle {{
    stroke-width: 3;
  }}
  .tool-group:hover .tool-img {{
    transform: scale(1.08);
  }}
  .tool-img {{
    transition: transform 0.15s ease;
    transform-box: fill-box;
    transform-origin: center;
  }}
  .tooltip {{
    position: fixed;
    pointer-events: none;
    background: #ffffff;
    color: #111;
    border: 1px solid var(--imd-blue);
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 13px;
    box-shadow: 0 4px 12px rgba(0,0,0,0.18);
    opacity: 0;
    transition: opacity 0.1s ease;
    z-index: 10;
    max-width: 260px;
  }}
  .tooltip .t-name {{ font-weight: 600; }}
  .tooltip .t-url {{ color: #555; font-size: 12px; word-break: break-all; }}
  .footer {{
    text-align: center;
    padding: 16px;
    font-size: 12px;
    opacity: 0.85;
  }}
  .footer a {{ color: #fff; }}
</style>
</head>
<body>
  <div class="header">
    {('<img class="imd-logo" alt="IMD / Global Center for Digital and AI Transformation" src="' + header_logo + '">') if header_logo else '<div style="font-weight:700;font-size:28px;">IMD</div><div style="margin-left:18px;font-size:16px;">Global Center for Digital<br>and AI Transformation</div>'}
  </div>

  <div class="wheel-wrap">
    <svg class="wheel" viewBox="-500 -500 1000 1000" aria-label="GenAI productivity wheel"></svg>
  </div>

  <div class="footer">
    Last updated: {timestamp} ·
    <a href="https://www.imd.org/centers/digital-ai-transformation-center" target="_blank" rel="noopener">
      imd.org/centers/digital-ai-transformation-center
    </a>
  </div>

  <div class="tooltip" id="tooltip">
    <div class="t-name"></div>
    <div class="t-url"></div>
  </div>

<script src="https://cdnjs.cloudflare.com/ajax/libs/d3/7.8.5/d3.min.js"></script>
<script>
const CATEGORIES = {payload};

// Wheel geometry (in SVG user units; viewBox is -500..500)
const CENTER_R   = 150;  // inner white-blue centre circle
const LABEL_R    = 240;  // mid-ring where category labels go
const RING_INNER = 325;  // start of the outer (tool) ring
const RING_OUTER = 480;  // outer wheel edge

const svg = d3.select("svg.wheel");
const tooltip = d3.select("#tooltip");

const n = CATEGORIES.length;
const TAU = 2 * Math.PI;
const segAngle = TAU / n;

// --- Draw segment backgrounds (alternating shades) ---
const segArc = d3.arc()
  .innerRadius(CENTER_R)
  .outerRadius(RING_OUTER);

// --- Defs: gradient & filter for the "popular" highlight ring ---
const defs = svg.append("defs");

// Conic-style approximated via linearGradient at 45°. The ring spins, so the
// gradient angle just needs to look pleasing without rotation.
const grad = defs.append("linearGradient")
  .attr("id", "highlight-gradient")
  .attr("x1", "0%").attr("y1", "0%")
  .attr("x2", "100%").attr("y2", "100%");
grad.append("stop").attr("offset", "0%")  .attr("stop-color", "#0057B8");  // IMD blue
grad.append("stop").attr("offset", "50%") .attr("stop-color", "#FFB400");  // amber
grad.append("stop").attr("offset", "100%").attr("stop-color", "#0057B8");  // IMD blue

// Soft glow: the filter takes the ring's stroke and blurs/recolors it for halo
const filter = defs.append("filter")
  .attr("id", "highlight-glow")
  .attr("x", "-50%").attr("y", "-50%")
  .attr("width", "200%").attr("height", "200%");
filter.append("feGaussianBlur")
  .attr("stdDeviation", "3")
  .attr("result", "blur");
const merge = filter.append("feMerge");
merge.append("feMergeNode").attr("in", "blur");
merge.append("feMergeNode").attr("in", "SourceGraphic");

svg.selectAll("path.seg-bg")
  .data(CATEGORIES.map((c, i) => ({{
    startAngle: i * segAngle,
    endAngle: (i + 1) * segAngle,
    idx: i,
    data: c
  }})))
  .enter()
  .append("path")
  .attr("class", d => "seg-bg" + (d.idx % 2 ? " alt" : ""))
  .attr("d", segArc);

// --- Segment dividers ---
svg.selectAll("line.seg-divider")
  .data(d3.range(n))
  .enter()
  .append("line")
  .attr("class", "seg-divider")
  .attr("x1", d => Math.cos(d * segAngle - Math.PI / 2) * CENTER_R)
  .attr("y1", d => Math.sin(d * segAngle - Math.PI / 2) * CENTER_R)
  .attr("x2", d => Math.cos(d * segAngle - Math.PI / 2) * RING_OUTER)
  .attr("y2", d => Math.sin(d * segAngle - Math.PI / 2) * RING_OUTER);

// Inner ring boundary (between labels and tools)
svg.append("circle")
  .attr("r", RING_INNER)
  .attr("fill", "none")
  .attr("stroke", "var(--imd-blue)")
  .attr("stroke-width", 1);

// Outer ring boundary
svg.append("circle")
  .attr("r", RING_OUTER)
  .attr("fill", "none")
  .attr("stroke", "var(--imd-blue)")
  .attr("stroke-width", 1);

// --- Category labels (wrapped to multiple lines for long names) ---
CATEGORIES.forEach((cat, i) => {{
  const midAngle = (i + 0.5) * segAngle - Math.PI / 2;
  const x = Math.cos(midAngle) * LABEL_R;
  const y = Math.sin(midAngle) * LABEL_R;
  const words = cat.name.split(/\\s+/);
  // Greedy wrap into lines of <= 14 chars
  const lines = [];
  let buf = "";
  for (const w of words) {{
    if ((buf + " " + w).trim().length <= 14) {{
      buf = (buf + " " + w).trim();
    }} else {{
      if (buf) lines.push(buf);
      buf = w;
    }}
  }}
  if (buf) lines.push(buf);

  const text = svg.append("text")
    .attr("class", "category-label")
    .attr("x", x)
    .attr("y", y)
    .attr("text-anchor", "middle")
    .attr("dominant-baseline", "middle");
  const lineHeight = 16;
  const startDy = -((lines.length - 1) * lineHeight) / 2;
  lines.forEach((line, li) => {{
    text.append("tspan")
      .attr("x", x)
      .attr("dy", li === 0 ? startDy : lineHeight)
      .text(line);
  }});
}});

// --- Centre circle + title ---
svg.append("circle")
  .attr("class", "center-circle")
  .attr("r", CENTER_R);

const title = svg.append("text")
  .attr("class", "center-title")
  .attr("y", -44);
["Generative AI", "Applications for", "Better Productivity"].forEach((line, li) => {{
  title.append("tspan").attr("x", 0).attr("dy", li === 0 ? 0 : 34).text(line);
}});

const IMD_CENTER_URI = {center_logo_json};
if (IMD_CENTER_URI) {{
  // Centre IMD lettermark — sized 110x44 (matches ~2.5:1 aspect of the source)
  const cw = 110, ch = 44;
  svg.append("image")
    .attr("href", IMD_CENTER_URI)
    .attr("x", -cw / 2)
    .attr("y", 60)
    .attr("width", cw)
    .attr("height", ch)
    .attr("preserveAspectRatio", "xMidYMid meet");
}} else {{
  svg.append("text")
    .attr("class", "center-sub")
    .attr("y", 78)
    .text("IMD");
}}

// --- Tool logos: distribute along each segment's arc ---
// Logos are typically embedded as base64 data URIs in tool.logo_uri (preferred).
// If absent, we fall back to logo.dev (the Clearbit successor; needs a token if
// you want high-volume use), then to Google's favicon service.
function logoDevUrl(toolUrl) {{
  try {{
    const u = new URL(toolUrl);
    const host = u.hostname.replace(/^www\\./, "");
    return "https://img.logo.dev/" + host + "?size=256&format=png";
  }} catch (e) {{ return null; }}
}}
function brandfetchUrl(toolUrl) {{
  try {{
    const u = new URL(toolUrl);
    const host = u.hostname.replace(/^www\\./, "");
    return "https://cdn.brandfetch.io/" + host + "/w/256/h/256";
  }} catch (e) {{ return null; }}
}}
function faviconUrl(toolUrl) {{
  try {{
    const u = new URL(toolUrl);
    return "https://www.google.com/s2/favicons?sz=128&domain=" + u.hostname;
  }} catch (e) {{ return null; }}
}}

CATEGORIES.forEach((cat, ci) => {{
  const start = ci * segAngle - Math.PI / 2;
  const end   = (ci + 1) * segAngle - Math.PI / 2;
  const tools = cat.tools || [];
  const k = tools.length;
  if (k === 0) return;

  // Radial bands: distribute across radius and arc together
  const arcInset = 0.18 * segAngle; // keep logos clear of the divider lines
  const usableStart = start + arcInset;
  const usableEnd   = end - arcInset;
  // Decide ring layout: up to 3 in single ring, otherwise 2 rings
  const twoRings = k > 3;
  const perRing = twoRings ? Math.ceil(k / 2) : k;
  const ringRadii = twoRings
    ? [RING_INNER + (RING_OUTER - RING_INNER) * 0.36,
       RING_INNER + (RING_OUTER - RING_INNER) * 0.70]
    : [RING_INNER + (RING_OUTER - RING_INNER) * 0.5];

  tools.forEach((tool, ti) => {{
    const ring = twoRings ? Math.floor(ti / perRing) : 0;
    const idxInRing = twoRings ? (ti % perRing) : ti;
    const ringCount = twoRings
      ? (ring === 0 ? perRing : (k - perRing))
      : k;
    const r = ringRadii[ring];
    let theta;
    if (ringCount === 1) {{
      theta = (usableStart + usableEnd) / 2;
    }} else {{
      const step = (usableEnd - usableStart) / (ringCount - 1);
      theta = usableStart + idxInRing * step;
    }}
    const cx = Math.cos(theta) * r;
    const cy = Math.sin(theta) * r;
    const radius = twoRings ? 22 : 28;

    const g = svg.append("g")
      .attr("class", "tool-group")
      .style("cursor", "pointer")
      .on("mouseover", function(ev) {{
        tooltip.style("opacity", 1);
        tooltip.select(".t-name").text(tool.name);
        tooltip.select(".t-url").text(tool.url);
      }})
      .on("mousemove", function(ev) {{
        tooltip
          .style("left", (ev.clientX + 14) + "px")
          .style("top",  (ev.clientY + 14) + "px");
      }})
      .on("mouseout", function() {{
        tooltip.style("opacity", 0);
      }})
      .on("click", function() {{
        window.open(tool.url, "_blank", "noopener");
      }});

    // Highlight ring for "most popular" tools (drawn first, behind the white
    // circle). Uses a gradient stroke + glow filter + dashed pattern + slow
    // rotation animation for a polished, brand-consistent look.
    if (tool.highlighted) {{
      const ringR = radius + 5;
      const hg = g.append("g").attr("class", "highlight-ring-group");
      const ring = hg.append("circle")
        .attr("class", "highlight-ring")
        .attr("cx", cx)
        .attr("cy", cy)
        .attr("r", ringR)
        .attr("fill", "none")
        .attr("stroke", "url(#highlight-gradient)")
        .attr("stroke-width", 2.5)
        .attr("stroke-dasharray", "6 4")
        .attr("stroke-linecap", "round")
        .attr("filter", "url(#highlight-glow)");
      // Slow rotation: animate stroke-dashoffset so dashes appear to march
      ring.append("animate")
        .attr("attributeName", "stroke-dashoffset")
        .attr("from", 0)
        .attr("to", -40)
        .attr("dur", "6s")
        .attr("repeatCount", "indefinite");
    }}

    g.append("circle")
      .attr("class", "tool-circle")
      .attr("cx", cx)
      .attr("cy", cy)
      .attr("r", radius);

    // Logo source chain, tried in order.
    //   - If we have a real embedded logo (user upload or genuine brand mark
    //     that was previously fetched), use it FIRST. It's known-good and
    //     avoids the wheel showing Google's generic globe favicon for tools
    //     whose homepage doesn't expose a recognizable icon.
    //   - Otherwise (only an auto-generated monogram), try live CDNs first
    //     in case the user's browser can fetch a real brand mark, and fall
    //     back to the monogram as last resort.
    const realEmbedded = (tool.logo_uri && tool.logo_is_real) ? tool.logo_uri : null;
    const monogram     = (tool.logo_uri && !tool.logo_is_real) ? tool.logo_uri : null;
    const sources = (realEmbedded
      ? [realEmbedded, logoDevUrl(tool.url), brandfetchUrl(tool.url), faviconUrl(tool.url)]
      : [logoDevUrl(tool.url), brandfetchUrl(tool.url), faviconUrl(tool.url), monogram]
    ).filter(Boolean);

    if (sources.length > 0) {{
      const img = g.append("image")
        .attr("class", "tool-img")
        .attr("x", cx - radius * 0.8)
        .attr("y", cy - radius * 0.8)
        .attr("width", radius * 1.6)
        .attr("height", radius * 1.6)
        .attr("href", sources[0])
        .attr("preserveAspectRatio", "xMidYMid meet");

      // Walk the fallback chain on each error OR on suspiciously-small
      // images (CDNs sometimes return 1x1 placeholders instead of 404,
      // which never triggers the error event).
      let attempt = 0;
      const node = img.node();
      function tryNext() {{
        attempt += 1;
        if (attempt < sources.length) {{
          img.attr("href", sources[attempt]);
        }} else {{
          node.removeEventListener("error", onError);
          node.removeEventListener("load", onLoad);
          img.remove();
        }}
      }}
      function onError() {{ tryNext(); }}
      function onLoad() {{
        // Detect placeholder responses: <10x10 natural size = not a real logo
        // Use the underlying HTMLImageElement-like properties exposed via the
        // raw DOM API. For SVG <image>, we probe via a temporary Image() load.
        const href = img.attr("href");
        // If it's a data URI (our embedded monogram), trust it
        if (href && href.startsWith("data:")) return;
        const probe = new Image();
        probe.onload = function() {{
          if (probe.naturalWidth < 10 || probe.naturalHeight < 10) {{
            tryNext();
          }}
        }};
        probe.onerror = function() {{ tryNext(); }};
        probe.src = href;
      }}
      node.addEventListener("error", onError);
      node.addEventListener("load", onLoad);
    }}
  }});
}});
</script>
</body>
</html>
"""


def render(tools_path, output_path):
    """Read tools.json and write index.html."""
    data = _load_tools(tools_path)
    html = _build_html(data)
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    return output_path
