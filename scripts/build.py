#!/usr/bin/env python3
"""
Fetches approved events + sources from Airtable and injects a JSON data block
into index.html. JavaScript in the page renders cards dynamically from the JSON.
"""

import json, os, sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

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
    for evt_rec_id in f.get("Event", []):
        sources_by_event[evt_rec_id].append(f)

# ── Load day summaries ────────────────────────────────────────────────────────

day_summaries = json.loads((ROOT / "_data" / "day_summaries.json").read_text())

# ── Group events by conflict day ──────────────────────────────────────────────

events_by_day = defaultdict(list)
for rec in raw_events:
    day = int(rec.get("fields", {}).get("Conflict Day") or 0)
    events_by_day[day].append(rec)

sorted_days = sorted(events_by_day.keys())

# ── Build JSON data structure ─────────────────────────────────────────────────

CONFLICT_START = datetime(2026, 2, 28)

def auto_date_display(day_num):
    d = CONFLICT_START + timedelta(days=day_num - 1)
    return d.strftime("%B %-d, %Y").upper()

days_data = []
for day_num in sorted_days:
    meta = day_summaries.get(str(day_num), {})
    days_data.append({
        "day":         day_num,
        "id":          f"day{day_num}",
        "dateDisplay": meta.get("date_display") or auto_date_display(day_num),
        "summary":     meta.get("summary", ""),
    })

events_data = []
skipped = []
for rec in raw_events:
    f       = rec.get("fields", {})
    status  = f.get("Status", "confirmed")
    conf    = f.get("Confidence")
    pct     = int(conf * 100) if conf and conf <= 1 else (int(conf) if conf else None)
    evt_id  = f.get("Event ID", "")
    day_num = int(f.get("Conflict Day") or 0)

    date = f.get("Date", "")
    if not date:
        if day_num:
            date = (CONFLICT_START + timedelta(days=day_num - 1)).strftime("%Y-%m-%d")
            print(f"  WARNING: {evt_id} missing Date — derived from Conflict Day {day_num}: {date}")
        else:
            print(f"  SKIPPING {evt_id}: missing both Date and Conflict Day")
            skipped.append(evt_id)
            continue

    # Build sources list grouped by source name
    by_name = defaultdict(list)
    for s in sources_by_event.get(rec["id"], []):
        name = s.get("Source Name", "")
        url  = s.get("URL", "")
        text = s.get("Display Text", "") or url
        if url:
            by_name[name].append({"url": url, "text": text})
    sources = [{"name": name, "links": links} for name, links in by_name.items()]

    events_data.append({
        "id":          evt_id.lower(),
        "eventId":     evt_id,
        "type":        status,
        "category":    f.get("Category", ""),
        "title":       f.get("Title", ""),
        "description": f.get("Description", ""),
        "sources":     sources,
        "confidence":  pct,
        "tags":        f.get("Tags", []),
        "date":        date,
        "day":         day_num,
    })

if skipped:
    print(f"\n  SKIPPED {len(skipped)} event(s) with no date or conflict day: {', '.join(skipped)}")

archive_data = {"days": days_data, "events": events_data}

# ── Inject JSON into index.html ───────────────────────────────────────────────

try:
    from bs4 import BeautifulSoup
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "beautifulsoup4", "-q"])
    from bs4 import BeautifulSoup

index_path = ROOT / "index.html"
soup = BeautifulSoup(index_path.read_text(), "html.parser")

data_script = soup.find("script", {"id": "archive-data"})
if not data_script:
    sys.exit("Error: <script id='archive-data'> not found in index.html")

data_script.string = json.dumps(archive_data, ensure_ascii=False, separators=(",", ":"))

ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
ts_el = soup.find("span", {"id": "build-timestamp"})
if ts_el:
    ts_el.string = ts

index_path.write_text(str(soup))
print(f"\nRebuilt index.html — {len(events_data)} events across {len(sorted_days)} days. Timestamp: {ts}")
