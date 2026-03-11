#!/usr/bin/env python3
"""
Parses index.html and imports all events + sources into Airtable.
"""

import json, os, re, requests, sys
from pathlib import Path

BASE_ID       = "apphFTmzmkcDwYDKn"
TOKEN         = os.environ.get("AIRTABLE_TOKEN", "")
EVENTS_TABLE  = "tbl8bJqzzAJGne65R"
SOURCES_TABLE = "tblXXOPCZWrn7GYaC"
HEADERS       = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

try:
    from bs4 import BeautifulSoup
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "beautifulsoup4", "-q"])
    from bs4 import BeautifulSoup

# ── Parse index.html ──────────────────────────────────────────────────────────

soup = BeautifulSoup(Path("index.html").read_text(), "html.parser")

# Day block mapping: id → (conflict_day, iso_date)
MONTHS = {"JANUARY":"01","FEBRUARY":"02","MARCH":"03","APRIL":"04",
          "MAY":"05","JUNE":"06","JULY":"07","AUGUST":"08",
          "SEPTEMBER":"09","OCTOBER":"10","NOVEMBER":"11","DECEMBER":"12"}

def parse_date(s):
    m = re.match(r"(\w+)\s+(\d+),\s+(\d{4})", s.strip())
    if m:
        mon, day, yr = m.group(1), m.group(2).zfill(2), m.group(3)
        return f"{yr}-{MONTHS.get(mon,'01')}-{day}"
    return None

DAY_MAP = {}
for block in soup.select(".day-block"):
    did    = block.get("id","")
    num_el = block.select_one(".day-number")
    dat_el = block.select_one(".day-date")
    if num_el and dat_el:
        try:   num = int(num_el.get_text(strip=True))
        except ValueError: num = 0
        DAY_MAP[did] = (num, parse_date(dat_el.get_text(strip=True)))

events = []
for card in soup.select(".event-card"):
    day_block    = card.find_parent(class_="day-block")
    day_id       = day_block.get("id","") if day_block else ""
    conflict_day, iso_date = DAY_MAP.get(day_id, (None, None))

    def text(sel): e = card.select_one(sel); return e.get_text(strip=True) if e else ""

    # Confidence from .confidence-pct ("100%") or bar width
    conf = None
    pct_el = card.select_one(".confidence-pct")
    if pct_el:
        try: conf = int(pct_el.get_text(strip=True).replace("%",""))
        except ValueError: pass
    if conf is None:
        bar = card.select_one(".confidence-fill")
        if bar:
            m = re.search(r"width:\s*([\d.]+)%", bar.get("style",""))
            if m:
                try: conf = int(float(m.group(1)))
                except ValueError: pass

    # Sources: .source-row > .source-name + .source-links > a.source-link
    sources = []
    for row in card.select(".source-row"):
        name_el  = row.select_one(".source-name")
        src_name = name_el.get_text(strip=True) if name_el else ""
        for a in row.select("a.source-link"):
            url = a.get("href","").strip()
            if url.startswith("http"):
                sources.append({
                    "source_name":  src_name,
                    "url":          url,
                    "display_text": a.get_text(strip=True).lstrip("↗").strip(),
                })

    events.append({
        "event_id":     text(".event-id"),
        "title":        text(".event-title"),
        "status":       card.get("data-type","confirmed"),
        "category":     text(".event-category"),
        "description":  card.select_one(".event-description").get_text(" ", strip=True) if card.select_one(".event-description") else "",
        "date":         iso_date,
        "conflict_day": conflict_day,
        "confidence":   conf,
        "tags":         [t.get_text(strip=True).upper() for t in card.select(".tag")],
        "sources":      sources,
    })

all_tags = sorted({t for e in events for t in e["tags"]})
print(f"Parsed {len(events)} events, {sum(len(e['sources']) for e in events)} sources, {len(all_tags)} unique tags")

# ── Step 1: Create Event records ─────────────────────────────────────────────

def airtable_post(table_id, records_payload):
    url = f"https://api.airtable.com/v0/{BASE_ID}/{table_id}"
    r   = requests.post(url, headers=HEADERS, json={"records": records_payload, "typecast": True})
    if r.status_code not in (200, 201):
        print(f"  ERROR {r.status_code}: {r.text}")
        sys.exit(1)
    return r.json()["records"]

print("Creating Events...")
event_airtable_ids = {}

for i in range(0, len(events), 10):
    batch   = events[i:i+10]
    payload = []
    for e in batch:
        fields = {
            "Event ID":          e["event_id"],
            "Title":             e["title"],
            "Status":            e["status"],
            "Category":          e["category"],
            "Description":       e["description"],
            "Submission Status": "approved",
        }
        if e["date"]:         fields["Date"]         = e["date"]
        if e["conflict_day"]: fields["Conflict Day"] = e["conflict_day"]
        if e["confidence"]:   fields["Confidence"]   = e["confidence"] / 100
        if e["tags"]:         fields["Tags"]         = e["tags"]
        payload.append({"fields": fields})

    created = airtable_post(EVENTS_TABLE, payload)
    for rec, ev in zip(created, batch):
        event_airtable_ids[ev["event_id"]] = rec["id"]
        print(f"  {ev['event_id']} → {rec['id']}")

# ── Step 3: Create Source records ─────────────────────────────────────────────

print("\nCreating Sources...")
all_sources = []
for e in events:
    at_id = event_airtable_ids.get(e["event_id"])
    for s in e["sources"]:
        all_sources.append({**s, "event_at_id": at_id})

for i in range(0, len(all_sources), 10):
    batch   = all_sources[i:i+10]
    payload = []
    for s in batch:
        fields = {"Source Name": s["source_name"], "Display Text": s["display_text"]}
        if s["url"]:          fields["URL"]   = s["url"]
        if s["event_at_id"]:  fields["Event"] = [s["event_at_id"]]
        payload.append({"fields": fields})
    created = airtable_post(SOURCES_TABLE, payload)
    for rec in created:
        print(f"  Source → {rec['id']}")

print(f"\nDone. {len(events)} events, {len(all_sources)} sources imported.")
