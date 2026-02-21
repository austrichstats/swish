#!/usr/bin/env python3
"""
Swish Pickleball Court Scraper (v2)
Pulls pickleball court data from Google Places API (New).
Skips already-searched queries and already-enriched courts.
Downloads court photos and adds Street View links.

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

REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(REPO_ROOT / ".env")
API_KEY = os.getenv("GOOGLE_API_KEY")

TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
PLACE_DETAILS_URL = "https://places.googleapis.com/v1/places/{place_id}"
PHOTO_URL = "https://places.googleapis.com/v1/{photo_name}/media"

CITIES = [
    # Original 25
    "Phoenix, AZ", "Scottsdale, AZ", "Mesa, AZ",
    "Los Angeles, CA", "San Diego, CA", "Palm Springs, CA",
    "Austin, TX", "Houston, TX", "Dallas, TX",
    "Denver, CO",
    "Seattle, WA", "Portland, OR",
    "Naples, FL", "Tampa, FL", "Orlando, FL", "Miami, FL",
    "Salt Lake City, UT",
    "Las Vegas, NV",
    "Atlanta, GA",
    "Chicago, IL",
    "New York, NY",
    "Charlotte, NC",
    "Minneapolis, MN",
    "Kansas City, MO",
    "Pittsburgh, PA",
    # New cities
    "Tucson, AZ", "Gilbert, AZ", "Chandler, AZ",
    "Sacramento, CA", "San Jose, CA", "Fresno, CA",
    "San Antonio, TX", "Fort Worth, TX", "El Paso, TX",
    "Colorado Springs, CO", "Boulder, CO",
    "Spokane, WA", "Tacoma, WA",
    "Boise, ID",
    "Nashville, TN", "Memphis, TN", "Knoxville, TN",
    "Jacksonville, FL", "St. Petersburg, FL", "Fort Lauderdale, FL", "Sarasota, FL",
    "Provo, UT", "St. George, UT",
    "Reno, NV", "Henderson, NV",
    "Savannah, GA", "Augusta, GA",
    "Naperville, IL", "Schaumburg, IL",
    "Raleigh, NC", "Durham, NC", "Asheville, NC",
    "St. Louis, MO",
    "Indianapolis, IN",
    "Columbus, OH", "Cincinnati, OH", "Cleveland, OH",
    "Philadelphia, PA",
    "Boston, MA",
    "Baltimore, MD",
    "Richmond, VA", "Virginia Beach, VA",
    "Albuquerque, NM",
    "Omaha, NE",
    "Tulsa, OK", "Oklahoma City, OK",
    "Milwaukee, WI", "Madison, WI",
    "Des Moines, IA",
    "Honolulu, HI",
]

SEARCH_TEMPLATES = [
    "pickleball courts near {}",
    "pickleball club near {}",
]

TEXT_SEARCH_FIELDS = "places.id,places.displayName,places.location,places.formattedAddress,places.types"
DETAILS_FIELDS = "rating,userRatingCount,regularOpeningHours,internationalPhoneNumber,websiteUri,photos"

MAX_NEW_ENRICHMENT = 300  # Conservative — leaves buffer under 1,000/month limit


def text_search(query, page_token=None):
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


def get_place_details(place_id):
    url = PLACE_DETAILS_URL.format(place_id=place_id)
    headers = {
        "X-Goog-Api-Key": API_KEY,
        "X-Goog-FieldMask": DETAILS_FIELDS,
    }
    resp = requests.get(url, headers=headers, timeout=30)
    if resp.status_code == 429:
        print("  Rate limited, sleeping 5s...")
        time.sleep(5)
        resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.json()


def download_photo(photo_name, save_path):
    url = PHOTO_URL.format(photo_name=photo_name)
    params = {"maxHeightPx": 300, "maxWidthPx": 400, "key": API_KEY}
    resp = requests.get(url, params=params, timeout=30)
    if resp.status_code == 429:
        time.sleep(5)
        resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    save_path.write_bytes(resp.content)


def parse_hours(opening_hours):
    if not opening_hours or "weekdayDescriptions" not in opening_hours:
        return None
    hours = {}
    for desc in opening_hours["weekdayDescriptions"]:
        parts = desc.split(": ", 1)
        if len(parts) == 2:
            hours[parts[0].lower()] = parts[1]
    return hours


def load_state():
    """Load searched queries and existing court data."""
    data_dir = REPO_ROOT / "data"

    # Load searched queries from checkpoint
    checkpoint_path = data_dir / "raw_places.json"
    searched_queries = []
    if checkpoint_path.exists():
        with open(checkpoint_path) as f:
            data = json.load(f)
        if isinstance(data, dict) and "searched_queries" in data:
            searched_queries = data["searched_queries"]
        else:
            # Old format — assume original 25 cities were searched with one template
            searched_queries = [f"pickleball courts near {city}" for city in CITIES[:25]]

    # Load courts from final output (has enrichment data from previous runs)
    courts = {}
    courts_path = data_dir / "courts.json"
    if courts_path.exists():
        with open(courts_path) as f:
            court_list = json.load(f)
        for c in court_list:
            courts[c["place_id"]] = c

    return searched_queries, courts


def save_checkpoint(searched_queries):
    checkpoint_path = REPO_ROOT / "data" / "raw_places.json"
    with open(checkpoint_path, "w") as f:
        json.dump({"searched_queries": searched_queries}, f, indent=2)


def is_enriched(court):
    """Check if a court already has Place Details data."""
    return any(court.get(f) is not None for f in ["rating", "phone", "website", "hours"])


def search_new_queries(searched_queries, courts):
    """Search only queries we haven't run before. Returns updated query list."""
    searched_set = set(searched_queries)
    new_queries = []
    for city in CITIES:
        for template in SEARCH_TEMPLATES:
            q = template.format(city)
            if q not in searched_set:
                new_queries.append(q)

    if not new_queries:
        print("All queries already searched. No new Text Search calls needed.")
        return searched_queries

    print(f"\n{len(new_queries)} new queries to search...")
    total_requests = 0

    for query in new_queries:
        print(f"Searching: {query}")
        page = 0

        try:
            result = text_search(query)
            total_requests += 1
        except requests.RequestException as e:
            print(f"  ERROR: {e}, skipping")
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
                        "photo": None,
                        "street_view_url": None,
                    }

            page += 1
            next_token = result.get("nextPageToken")
            if not next_token or page >= 3:
                break

            time.sleep(0.5)
            try:
                result = text_search(query, page_token=next_token)
                total_requests += 1
            except requests.RequestException as e:
                print(f"  ERROR on page {page}: {e}")
                break

        searched_queries.append(query)
        print(f"  {len(places)} results (page {page}), {len(courts)} unique total")

    print(f"\nSearch phase complete: {len(courts)} unique courts, {total_requests} new API calls")
    return searched_queries


def enrich_new_courts(courts):
    """Enrich courts that don't have details yet. Downloads photos too."""
    photos_dir = REPO_ROOT / "docs" / "photos"
    photos_dir.mkdir(exist_ok=True)

    unenriched = [pid for pid, c in courts.items() if not is_enriched(c)]
    to_enrich = unenriched[:MAX_NEW_ENRICHMENT]

    if not to_enrich:
        print("\nAll courts already enriched (or limit reached). No new Details calls needed.")
        return

    skipped = len(unenriched) - len(to_enrich)
    print(f"\nEnriching {len(to_enrich)} new courts with Place Details + photos...")
    if skipped > 0:
        print(f"  ({skipped} more unenriched courts saved for next run)")

    photos_downloaded = 0

    for i, pid in enumerate(to_enrich):
        try:
            details = get_place_details(pid)
            courts[pid]["rating"] = details.get("rating")
            courts[pid]["user_rating_count"] = details.get("userRatingCount")
            courts[pid]["phone"] = details.get("internationalPhoneNumber")
            courts[pid]["website"] = details.get("websiteUri")
            courts[pid]["hours"] = parse_hours(details.get("regularOpeningHours"))

            # Download first photo if available
            photos = details.get("photos", [])
            if photos:
                photo_name = photos[0].get("name")
                if photo_name:
                    safe_id = pid.replace("/", "_")
                    photo_path = photos_dir / f"{safe_id}.jpg"
                    try:
                        download_photo(photo_name, photo_path)
                        courts[pid]["photo"] = f"photos/{safe_id}.jpg"
                        photos_downloaded += 1
                    except requests.RequestException as e:
                        print(f"  Photo download failed for {pid}: {e}")
        except requests.RequestException as e:
            print(f"  ERROR enriching {pid}: {e}")

        if (i + 1) % 50 == 0:
            print(f"  Enriched {i + 1}/{len(to_enrich)} ({photos_downloaded} photos)")
            time.sleep(0.2)

    print(f"Enrichment complete. {len(to_enrich)} courts enriched, {photos_downloaded} photos downloaded.")


def add_street_view_urls(courts):
    """Add Street View links for all courts (free — just a URL, no API call)."""
    added = 0
    for c in courts.values():
        if c.get("lat") and c.get("lng") and not c.get("street_view_url"):
            c["street_view_url"] = (
                f"https://www.google.com/maps/@?api=1&map_action=pano"
                f"&viewpoint={c['lat']},{c['lng']}"
            )
            added += 1
    if added:
        print(f"\nAdded Street View URLs to {added} courts.")


def main():
    if not API_KEY or API_KEY == "paste_your_key_here":
        print("ERROR: Set GOOGLE_API_KEY in .env (at repo root)")
        sys.exit(1)

    data_dir = REPO_ROOT / "data"
    data_dir.mkdir(exist_ok=True)

    # Load existing state
    searched_queries, courts = load_state()
    print(f"Loaded {len(courts)} existing courts, {len(searched_queries)} previously searched queries")

    # Phase 1: Search new cities/queries only
    searched_queries = search_new_queries(searched_queries, courts)
    save_checkpoint(searched_queries)

    # Phase 2: Enrich new courts + download photos
    enrich_new_courts(courts)

    # Phase 3: Street View URLs (free)
    add_street_view_urls(courts)

    # Save final output
    court_list = list(courts.values())
    output_path = data_dir / "courts.json"
    with open(output_path, "w") as f:
        json.dump(court_list, f, indent=2)
    print(f"\nSaved {len(court_list)} courts to {output_path}")

    docs_path = REPO_ROOT / "docs" / "courts.json"
    with open(docs_path, "w") as f:
        json.dump(court_list, f, indent=2)
    print(f"Copied to {docs_path} for GitHub Pages")

    # Summary
    enriched_count = sum(1 for c in court_list if is_enriched(c))
    photo_count = sum(1 for c in court_list if c.get("photo"))
    print(f"\nTotal: {len(court_list)} courts | {enriched_count} enriched | {photo_count} with photos")


if __name__ == "__main__":
    main()
