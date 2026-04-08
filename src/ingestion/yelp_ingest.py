import json
import pandas as pd
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]

RAW_PATH = BASE_DIR / "data/raw/yelp_dataset/yelp_academic_dataset_business.json"
OUT_PATH = BASE_DIR / "data/processed/yelp_socal_businesses.json"

# SoCal bounding box
LAT_MIN, LAT_MAX = 32.5, 35.0
LON_MIN, LON_MAX = -120.5, -114.0

RELEVANT_CATEGORIES = {
    "hiking", "beaches", "parks", "camping", "rock climbing",
    "kayaking", "surfing", "trail", "nature", "outdoors"
}

def is_socal(biz):
    return (
        biz.get("state") == "CA" and
        LAT_MIN <= biz.get("latitude", 0) <= LAT_MAX and
        LON_MIN <= biz.get("longitude", 0) <= LON_MAX
    )

def is_relevant(biz):
    cats = biz.get("categories") or ""
    cats_lower = cats.lower()
    return any(kw in cats_lower for kw in RELEVANT_CATEGORIES)

results = []
with open(RAW_PATH, encoding="utf-8") as f:
    for line in f:
        biz = json.loads(line)
        if is_socal(biz) and is_relevant(biz):
            results.append({
                "yelp_id": biz["business_id"],
                "name": biz["name"],
                "latitude": biz["latitude"],
                "longitude": biz["longitude"],
                "address": biz.get("address"),
                "city": biz.get("city"),
                "categories": biz.get("categories"),
                "stars": biz.get("stars"),
                "price": (biz.get("attributes") or {}).get("RestaurantsPriceRange2"),
                "review_count": biz.get("review_count")
            })

with open(OUT_PATH, "w") as f:
    json.dump(results, f, indent=2)

print(f"Found {len(results)} SoCal outdoor locations")