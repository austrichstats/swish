# Swish Court Finder

Pickleball court database and interactive map for the Swish team. Pulls real court data from the Google Places API (New) and displays it on a shareable map hosted via GitHub Pages.

**Live site:** [austrichstats.github.io/swish](https://austrichstats.github.io/swish/)

## What's Here

```
court-scraper/
  scrape_courts.py     # Google Places API scraper (incremental, safe to re-run)
data/
  courts.json          # Full raw dataset (4,200 entries, gitignored)
  raw_places.json      # Search checkpoint (gitignored)
docs/
  index.html           # Leaflet.js map viewer (GitHub Pages source)
  courts.json          # Filtered dataset served to the map (1,403 courts)
  photos/              # Court photos from Google Places
  swish-logo.webp      # Swish branding asset
```

## Map Features

- 1,403 verified pickleball courts across 75 US cities
- Street and satellite map layers (with state lines)
- Clustered markers that expand on zoom
- Court popups with photo, rating, hours, phone, website
- Directions (Google Maps) and Street View links
- Search/filter by name or city
- Styled to match Swish branding
- Mobile responsive

## Setup

### Prerequisites

- Python 3.10+
- A Google Cloud project with **Places API (New)** enabled
- An API key (restricted to Places API only)

### Install

```bash
cd ~/Desktop/Repos/swish
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Configure

Create `.env` at the repo root:

```
GOOGLE_API_KEY=your_key_here
```

### Run the Scraper

```bash
python court-scraper/scrape_courts.py
```

The scraper is incremental:
- Skips previously searched queries
- Skips already enriched courts
- Enriches up to 300 new courts per run (stays within free tier)
- Downloads a photo for each newly enriched court

### Preview Locally

```bash
cd docs && python3 -m http.server 8000
# Open http://localhost:8000
```

### Deploy

Push to GitHub — Pages serves from the `docs/` folder automatically.

```bash
git add docs/
git commit -m "Update court data"
git push
```

## API Usage (Free Tier)

| API | Free Monthly Limit | Typical Run |
|-----|-------------------|-------------|
| Text Search (Pro) | 5,000 | ~150-400 |
| Place Details (Enterprise) | 1,000 | ~300 |
| Place Photos (Basic) | 5,000 | ~300 |

Total cost to date: **$0**

## Data Filtering

The scraper pulls broadly (~4,200 results) then the live site shows only verified pickleball courts (1,403) by filtering out generic parks, vacation rentals, coaching services, pro shops, and associations. The full dataset is preserved locally in `data/courts.json`.
