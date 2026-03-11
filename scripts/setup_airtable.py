#!/usr/bin/env python3
"""
Creates Events, Sources, and Submissions tables in the Hormuz Archive Airtable base.
Run once to set up schema before importing data.
"""

import json, os, requests, sys

BASE_ID = "apphFTmzmkcDwYDKn"
TOKEN   = os.environ.get("AIRTABLE_TOKEN", "")
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
API     = f"https://api.airtable.com/v0/meta/bases/{BASE_ID}/tables"

TAGS = [
    "IRAN","ISRAEL","US","RUSSIA","SAUDI-ARABIA","QATAR","KUWAIT","UAE","IRAQ",
    "SOUTH-KOREA","NORTH-KOREA","UKRAINE","MILITARY","MISSILES","MINES","ESCALATION",
    "THAAD","RADAR","RADAR-CORRIDOR","SATELLITE","PLANET-LABS","IRON-DOME","UNIT-8200",
    "CVN-72","USS-LINCOLN","IRGC","OIL","BRENT","WTI","DIESEL","MARKETS","HISTORIC",
    "SUPPLY-SHOCK","FORCE-MAJEURE","PRODUCTION","STORAGE","MANIPULATION","$118","$84",
    "NIC","TRUMP","GRAHAM","PUTIN","INTELLIGENCE","CENSORSHIP","BLACKOUT","DELETED",
    "AWS","CLOUD","INSURANCE","SHIPPING","HORMUZ","ACTUARIAL","HISTORIC-FIRST","LOCKDOWN",
    "DIPLOMACY","OFF-RAMP","EMBASSY","WASHINGTON-POST","UNVERIFIED","LOW-CONFIDENCE",
    "SUPPRESSED","MONITORING","HUMANITARIAN","CIVILIAN","DAY-1","INSIDER-TRADING",
    "GPS-SPOOFING","BBC","CBS","ANALYSIS","TEHRAN","TEL-AVIV"
]

TAG_CHOICES = [{"name": t} for t in TAGS]

TABLES = [
    {
        "name": "Events",
        "fields": [
            {"name": "Event ID",          "type": "singleLineText"},
            {"name": "Title",             "type": "singleLineText"},
            {"name": "Status",            "type": "singleSelect",
             "options": {"choices": [
                 {"name": "confirmed"},
                 {"name": "economic"},
                 {"name": "suppressed"},
                 {"name": "unconfirmed"},
             ]}},
            {"name": "Category",          "type": "singleLineText"},
            {"name": "Description",       "type": "multilineText"},
            {"name": "Date",              "type": "date",
             "options": {"dateFormat": {"name": "iso"}}},
            {"name": "Conflict Day",      "type": "number",
             "options": {"precision": 0}},
            {"name": "Confidence",        "type": "percent",
             "options": {"precision": 0}},
            {"name": "Tags",              "type": "multipleSelects",
             "options": {"choices": TAG_CHOICES}},
            {"name": "Submission Status", "type": "singleSelect",
             "options": {"choices": [
                 {"name": "approved"},
                 {"name": "pending_review"},
                 {"name": "rejected"},
             ]}},
            {"name": "Submitted By",      "type": "singleLineText"},
            {"name": "Editorial Notes",   "type": "multilineText"},
        ]
    },
    {
        "name": "Sources",
        "fields": [
            {"name": "Source Name",  "type": "singleLineText"},
            {"name": "URL",          "type": "url"},
            {"name": "Display Text", "type": "singleLineText"},
        ]
    },
    {
        "name": "Submissions",
        "fields": [
            {"name": "Title",        "type": "singleLineText"},
            {"name": "Date",         "type": "date",
             "options": {"dateFormat": {"name": "iso"}}},
            {"name": "Description",  "type": "multilineText"},
            {"name": "Status Claim", "type": "singleSelect",
             "options": {"choices": [
                 {"name": "confirmed"},
                 {"name": "economic"},
                 {"name": "suppressed"},
                 {"name": "unconfirmed"},
             ]}},
            {"name": "Category",     "type": "singleLineText"},
            {"name": "Tags",         "type": "multipleSelects",
             "options": {"choices": TAG_CHOICES}},
            {"name": "Source Name",  "type": "singleLineText"},
            {"name": "Source URL",   "type": "url"},
            {"name": "Submitted By", "type": "singleLineText"},
            {"name": "Review Status","type": "singleSelect",
             "options": {"choices": [
                 {"name": "pending"},
                 {"name": "approved"},
                 {"name": "rejected"},
             ]}},
        ]
    },
]

def create_table(table):
    r = requests.post(API, headers=HEADERS, json=table)
    if r.status_code in (200, 201):
        data = r.json()
        print(f"  Created: {data['name']} ({data['id']})")
        return data
    else:
        print(f"  ERROR creating {table['name']}: {r.status_code} {r.text}")
        sys.exit(1)

def add_link_field(table_id, field_name, linked_table_id):
    url = f"https://api.airtable.com/v0/meta/bases/{BASE_ID}/tables/{table_id}/fields"
    payload = {
        "name": field_name,
        "type": "multipleRecordLinks",
        "options": {"linkedTableId": linked_table_id}
    }
    r = requests.post(url, headers=HEADERS, json=payload)
    if r.status_code in (200, 201):
        print(f"  Linked field '{field_name}' added.")
    else:
        print(f"  ERROR adding link field: {r.status_code} {r.text}")

if __name__ == "__main__":
    created = {}
    for table in TABLES:
        print(f"Creating table: {table['name']}")
        result = create_table(table)
        created[table["name"]] = result["id"]

    print("\nAdding linked record fields...")
    # Sources.Event → Events
    add_link_field(created["Sources"],     "Event",      created["Events"])
    # Submissions.Promoted To → Events
    add_link_field(created["Submissions"], "Promoted To", created["Events"])

    print(f"\nDone. Table IDs:")
    for name, tid in created.items():
        print(f"  {name}: {tid}")
    print("\nYou can now delete the default 'Table 1' manually in Airtable.")
