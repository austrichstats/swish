#!/usr/bin/env python3
"""
Swish Pickleball Court Scraper
Pulls pickleball court data from Google Places API (New) Text Search + Place Details.
Saves results to data/courts.json.

Usage:
    cd ~/Desktop/Repos/swish
    source venv/bin/activate
    python court-scraper/scrape_courts.py
"""

import json
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

# Load API key from repo root .env
REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(REPO_ROOT / ".env")
API_KEY = os.getenv("GOOGLE_API_KEY")

TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
PLACE_DETAILS_URL = "https://places.googleapis.com/v1/places/{place_id}"

CITIES = [
    "Phoenix, AZ",
    "Scottsdale, AZ",
    "Mesa, AZ",
    "Los Angeles, CA",
    "San Diego, CA",
    "Palm Springs, CA",
    "Austin, TX",
    "Houston, TX",
    "Dallas, TX",
    "Denver, CO",
    "Seattle, WA",
    "Portland, OR",
    "Naples, FL",
    "Tampa, FL",
    "Orlando, FL",
    "Miami, FL",
    "Salt Lake City, UT",
    "Las Vegas, NV",
    "Atlanta, GA",
    "Chicago, IL",
    "New York, NY",
    "Charlotte, NC",
    "Minneapolis, MN",
    "Kansas City, MO",
    "Pittsburgh, PA",
]

# Fields for Text Search (Pro tier — free up to 5,000/month)
TEXT_SEARCH_FIELDS = "places.id,places.displayName,places.location,places.formattedAddress,places.types"

# Fields for Place Details (Enterprise tier — free up to 1,000/month)
DETAILS_FIELDS = "rating,userRatingCount,regularOpeningHours,internationalPhoneNumber,websiteUri"

MAX_ENRICHMENT = 500


def text_search(query: str, page_token: str | None = None) -> dict:
    """Run a Text Search (New) request."""
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": API_KEY,
        "X-Goog-FieldMask": f"nextPageToken,{TEXT_SEARCH_FIELDS}",
    }
    body = {"textQuery": query, "pageSize": 20}
    if page_token:
        body["pageToken"] = page_token

    resp = requests.post(TEXT_SEARCH_URL, headers=headers, json=body, timeout=30)
    if resp.status_code == 429:
        print("  Rate limited, sleeping 5s...")
        time.sleep(5)
        resp = requests.post(TEXT_SEARCH_URL, headers=headers, json=body, timeout=30)
    resp.raise_for_status()
    return resp.json()


def get_place_details(place_id: str) -> dict:
    """Fetch Place Details (New) for enrichment."""
    url = PLACE_DETAILS_URL.format(place_id=place_id)
    headers = {
        "X-Goog-Api-Key": API_KEY,
        "X-Goog-FieldMask": DETAILS_FIELDS,
    }
    resp = requests.get(url, headers=headers, timeout=30)
    if resp.status_code == 429:
        print("  Rate limited on details, sleeping 5s...")
        time.sleep(5)
        resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.json()


def parse_hours(opening_hours: dict | None) -> dict | None:
    """Convert regularOpeningHours into a simple day->string dict."""
    if not opening_hours or "weekdayDescriptions" not in opening_hours:
        return None
    hours = {}
    for desc in opening_hours["weekdayDescriptions"]:
        # Format: "Monday: 6:00 AM – 10:00 PM"
        parts = desc.split(": ", 1)
        if len(parts) == 2:
            hours[parts[0].lower()] = parts[1]
    return hours


def search_all_cities() -> dict:
    """Search for pickleball courts in all cities. Returns dict keyed by place_id."""
    courts = {}
    total_requests = 0

    for city in CITIES:
        query = f"pickleball courts near {city}"
        print(f"Searching: {query}")
        page = 0

        try:
            result = text_search(query)
            total_requests += 1
        except requests.RequestException as e:
            print(f"  ERROR: {e}, skipping {city}")
            continue

        while True:
            places = result.get("places", [])
            for p in places:
                pid = p.get("id")
                if pid and pid not in courts:
                    courts[pid] = {
                        "place_id": pid,
                        "name": p.get("displayName", {}).get("text", "Unknown"),
                        "address": p.get("formattedAddress"),
                        "lat": p.get("location", {}).get("latitude"),
                        "lng": p.get("location", {}).get("longitude"),
                        "types": p.get("types", []),
                        "rating": None,
                        "user_rating_count": None,
                        "phone": None,
                        "website": None,
                        "hours": None,
                    }

            page += 1
            next_token = result.get("nextPageToken")
            if not next_token or page >= 3:
                break

            time.sleep(0.5)  # brief pause between pages
            try:
                result = text_search(query, page_token=next_token)
                total_requests += 1
            except requests.RequestException as e:
                print(f"  ERROR on page {page}: {e}")
                break

        print(f"  Found {len(places)} results (page {page}), {len(courts)} unique total")

    print(f"\nText Search complete: {len(courts)} unique courts, {total_requests} API calls")
    return courts


def enrich_courts(courts: dict) -> None:
    """Enrich top courts with Place Details. Modifies dict in-place."""
    place_ids = list(courts.keys())[:MAX_ENRICHMENT]
    print(f"\nEnriching {len(place_ids)} courts with Place Details...")

    for i, pid in enumerate(place_ids):
        try:
            details = get_place_details(pid)
            courts[pid]["rating"] = details.get("rating")
            courts[pid]["user_rating_count"] = details.get("userRatingCount")
            courts[pid]["phone"] = details.get("internationalPhoneNumber")
            courts[pid]["website"] = details.get("websiteUri")
            courts[pid]["hours"] = parse_hours(details.get("regularOpeningHours"))
        except requests.RequestException as e:
            print(f"  ERROR enriching {pid}: {e}")

        if (i + 1) % 50 == 0:
            print(f"  Enriched {i + 1}/{len(place_ids)}")
            time.sleep(0.2)

    print(f"Enrichment complete.")


def main():
    if not API_KEY or API_KEY == "paste_your_key_here":
        print("ERROR: Set GOOGLE_API_KEY in .env (at repo root)")
        sys.exit(1)

    data_dir = REPO_ROOT / "data"
    data_dir.mkdir(exist_ok=True)

    # Phase 1: Text Search
    checkpoint = data_dir / "raw_places.json"
    if checkpoint.exists():
        print(f"Loading checkpoint from {checkpoint}...")
        with open(checkpoint) as f:
            courts = json.load(f)
        print(f"  Loaded {len(courts)} courts from checkpoint")
    else:
        courts = search_all_cities()
        with open(checkpoint, "w") as f:
            json.dump(courts, f, indent=2)
        print(f"Checkpoint saved to {checkpoint}")

    # Phase 2: Enrich with Place Details
    enrich_courts(courts)

    # Save final output
    court_list = list(courts.values())
    output_path = data_dir / "courts.json"
    with open(output_path, "w") as f:
        json.dump(court_list, f, indent=2)
    print(f"\nSaved {len(court_list)} courts to {output_path}")

    # Also copy to docs/ for GitHub Pages
    docs_path = REPO_ROOT / "docs" / "courts.json"
    with open(docs_path, "w") as f:
        json.dump(court_list, f, indent=2)
    print(f"Copied to {docs_path} for GitHub Pages")


if __name__ == "__main__":
    main()
