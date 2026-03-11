#!/usr/bin/env python3
"""
Fetches approved events + sources from Airtable and rebuilds index.html in-place.
Preserves all static HTML (CSS, header, sidebar boilerplate, footer, scripts).
Only the day-nav and timeline sections are replaced.
"""

import json, os, re, sys
from collections import defaultdict
from pathlib import Path
from html import escape

import requests

# ── Config ────────────────────────────────────────────────────────────────────

BASE_ID       = "apphFTmzmkcDwYDKn"
TOKEN         = os.environ.get("AIRTABLE_TOKEN")
if not TOKEN:
    sys.exit("Error: AIRTABLE_TOKEN environment variable is not set.")
EVENTS_TABLE  = "tbl8bJqzzAJGne65R"
SOURCES_TABLE = "tblXXOPCZWrn7GYaC"
HEADERS       = {"Authorization": f"Bearer {TOKEN}"}

ROOT = Path(__file__).parent.parent

# ── Airtable fetch (handles pagination) ───────────────────────────────────────

def fetch_all(table_id, params=None):
    records, offset = [], None
    while True:
        p = dict(params or {})
        if offset:
            p["offset"] = offset
        r = requests.get(
            f"https://api.airtable.com/v0/{BASE_ID}/{table_id}",
            headers=HEADERS, params=p
        )
        r.raise_for_status()
        data = r.json()
        records.extend(data.get("records", []))
        offset = data.get("offset")
        if not offset:
            break
    return records

# ── Fetch data ────────────────────────────────────────────────────────────────

print("Fetching events from Airtable...")
raw_events = fetch_all(EVENTS_TABLE, {
    "filterByFormula": "{Submission Status}='approved'",
    "sort[0][field]":  "Conflict Day",
    "sort[0][direction]": "asc",
    "sort[1][field]":  "Event ID",
    "sort[1][direction]": "asc",
})
print(f"  {len(raw_events)} approved events")

print("Fetching sources from Airtable...")
raw_sources = fetch_all(SOURCES_TABLE)
print(f"  {len(raw_sources)} sources")

# ── Index sources by linked event record ID ───────────────────────────────────

sources_by_event = defaultdict(list)
for s in raw_sources:
    f = s.get("fields", {})
    linked = f.get("Event", [])
    for evt_rec_id in linked:
        sources_by_event[evt_rec_id].append(f)

# ── Load day summaries ────────────────────────────────────────────────────────

day_summaries = json.loads((ROOT / "_data" / "day_summaries.json").read_text())

# ── Group events by conflict day ──────────────────────────────────────────────

events_by_day = defaultdict(list)
for rec in raw_events:
    f = rec.get("fields", {})
    day = int(f.get("Conflict Day") or 0)
    events_by_day[day].append((rec["id"], f))

sorted_days = sorted(events_by_day.keys())

# ── HTML renderers ────────────────────────────────────────────────────────────

STATUS_LABEL = {
    "confirmed":   "CONFIRMED",
    "economic":    "ECONOMIC",
    "suppressed":  "SUPPRESSED",
    "unconfirmed": "MONITORING",
}

def render_sources_block(event_rec_id):
    sources = sources_by_event.get(event_rec_id, [])
    if not sources:
        return ""

    # Group by source name
    by_name = defaultdict(list)
    for s in sources:
        name = s.get("Source Name", "")
        url  = s.get("URL", "")
        text = s.get("Display Text", "") or url
        if url:
            by_name[name].append((url, text))

    rows = []
    for name, links in by_name.items():
        link_html = "".join(
            f'<a class="source-link" href="{escape(u)}" target="_blank" rel="noopener">↗ {escape(t)}</a>'
            for u, t in links
        )
        rows.append(f'''
      <div class="source-row">
        <span class="source-name">{escape(name)}</span>
        <div class="source-links">{link_html}</div>
      </div>''')

    return "\n".join(rows)

def render_confidence(conf_pct):
    if conf_pct is None:
        return ""
    pct = int(conf_pct * 100) if conf_pct <= 1 else int(conf_pct)
    return f'''
      <div class="confidence-bar">
        <span class="confidence-label">CONFIDENCE</span>
        <div class="confidence-track"><div class="confidence-fill" style="width:{pct}%"></div></div>
        <span class="confidence-pct">{pct}%</span>
      </div>'''

def render_event_card(rec_id, fields):
    status   = fields.get("Status", "confirmed")
    evt_id   = escape(fields.get("Event ID", ""))
    category = escape(fields.get("Category", ""))
    title    = escape(fields.get("Title", ""))
    desc     = escape(fields.get("Description", ""))
    tags     = fields.get("Tags", [])
    conf     = fields.get("Confidence")

    tag_html = "".join(f'<span class="tag">{escape(t)}</span>' for t in tags)
    src_html = render_sources_block(rec_id)
    conf_html = render_confidence(conf)
    status_label = STATUS_LABEL.get(status, status.upper())

    # Anchor id uses lowercase event id (e.g. evt-001)
    anchor = evt_id.lower().replace("evt-", "evt-")

    return f'''
<div class="event-card" id="{anchor}" data-type="{escape(status)}">
  <div class="event-bar {escape(status)}"></div>
  <div class="event-body">
    <div class="event-meta">
      <span class="event-status {escape(status)}">{status_label}</span>
      <span class="event-category">{category}</span>
      <span class="event-id">{evt_id}</span>
    </div>
    <div class="event-title">{title}</div>
    <div class="event-description">{desc}</div>
    <div class="event-sources">
      <div class="sources-label">Sources</div>
      {src_html}
      {conf_html}
    </div>
    <div class="event-footer">
      <div class="event-tags">{tag_html}</div>
    </div>
  </div>
</div>'''

def day_id(day_num):
    return f"day{day_num}"

def render_day_block(day_num, events):
    meta       = day_summaries.get(str(day_num), {})
    date_disp  = meta.get("date_display", f"DAY {day_num}")
    summary    = meta.get("summary", "")
    num_padded = str(day_num).zfill(2)

    cards = "\n".join(render_event_card(rec_id, fields) for rec_id, fields in events)

    return f'''
<div class="day-block" id="{day_id(day_num)}">
  <div class="day-header">
    <div class="day-number">{num_padded}</div>
    <div class="day-info">
      <div class="day-date">{escape(date_disp)}</div>
      <div class="day-summary">{escape(summary)}</div>
    </div>
  </div>
  {cards}
</div>'''

def render_day_nav_link(day_num, count, active=(False)):
    meta      = day_summaries.get(str(day_num), {})
    date_disp = meta.get("date_display", f"DAY {day_num}")
    # Shorten date for nav: "FEBRUARY 28, 2026" → "Feb 28"
    short = re.sub(
        r"^(\w{3})\w+\s+(\d+),.*$",
        lambda m: f"{m.group(1).capitalize()} {m.group(2)}",
        date_disp
    )
    active_class = " active" if active else ""
    return (
        f'<div class="day-link{active_class}" onclick="scrollToDay(\'{day_id(day_num)}\',this)">'
        f'<span>Day {day_num} — {short}</span>'
        f'<span class="day-count">{count} events</span>'
        f'</div>'
    )

# ── Build HTML fragments ──────────────────────────────────────────────────────

day_nav_html = "\n".join(
    render_day_nav_link(d, len(events_by_day[d]), active=(i == 0))
    for i, d in enumerate(sorted_days)
)

timeline_html = "\n".join(
    render_day_block(d, events_by_day[d])
    for d in sorted_days
)

# ── Inject into index.html ────────────────────────────────────────────────────

try:
    from bs4 import BeautifulSoup
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "beautifulsoup4", "-q"])
    from bs4 import BeautifulSoup

index_path = ROOT / "index.html"
soup = BeautifulSoup(index_path.read_text(), "html.parser")

# Replace day-nav
day_nav_el = soup.find(class_="day-nav")
if day_nav_el:
    day_nav_el.clear()
    day_nav_el.append(BeautifulSoup(day_nav_html, "html.parser"))
else:
    print("WARNING: .day-nav element not found in index.html")

# Replace timeline
timeline_el = soup.find(class_="timeline")
if timeline_el:
    timeline_el.clear()
    timeline_el.append(BeautifulSoup(timeline_html, "html.parser"))
else:
    print("WARNING: .timeline element not found in index.html")

index_path.write_text(str(soup))
print(f"\nRebuilt index.html — {len(raw_events)} events across {len(sorted_days)} days.")
