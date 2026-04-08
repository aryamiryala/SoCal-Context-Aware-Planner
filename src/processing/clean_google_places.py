# src/processing/clean_google_places.py
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]

# only keep places that have at least one of these types
RELEVANT_TYPES = {
    "park", "campground", "natural_feature", "tourist_attraction",
    "rv_park", "amusement_park", "aquarium", "zoo", "stadium",
    "hiking_area", "beach", "national_park", "state_park",
    "nature_reserve", "trail", "waterfall", "lake", "mountain"
}

# bounding box — same as yelp
LAT_MIN, LAT_MAX = 32.5, 35.0
LON_MIN, LON_MAX = -120.5, -114.0

def is_relevant(place):
    types = set(place.get("types", []))
    return bool(types & RELEVANT_TYPES)

def in_bounds(place):
    loc = place.get("geometry", {}).get("location", {})
    lat, lng = loc.get("lat", 0), loc.get("lng", 0)
    return LAT_MIN <= lat <= LAT_MAX and LON_MIN <= lng <= LON_MAX

def clean_place(place):
    loc = place["geometry"]["location"]
    return {
        "google_id": place["place_id"],
        "name": place["name"],
        "formatted_address": place.get("formatted_address"),
        "lat": loc["lat"],
        "lng": loc["lng"],
        "types": place.get("types", []),
        "rating": place.get("rating"),
        "user_ratings_total": place.get("user_ratings_total"),
        "price_level": place.get("price_level"),
        "opening_hours": place.get("opening_hours", {}).get("weekday_text"),
        "open_now": place.get("opening_hours", {}).get("open_now"),
        "reviews": [
            {
                "text": r.get("text"),
                "rating": r.get("rating"),
                "time": r.get("time"),
                "relative_time": r.get("relative_time_description")
            }
            for r in place.get("reviews", [])
            if r.get("text")
        ],
        "source": "google"
    }

def run():
    with open(BASE_DIR / "data/raw/google_dataset/google_places_socal.json") as f:
        places = json.load(f)
    print(f"Raw places: {len(places)}")

    # step 1: drop missing rating/reviews
    has_data = [p for p in places if p.get("rating") and p.get("reviews")]
    print(f"After dropping no-rating/no-review: {len(has_data)}")

    # step 2: filter to relevant types
    relevant = [p for p in has_data if is_relevant(p)]
    print(f"After type filter: {len(relevant)}")

    # step 3: filter to bounding box
    in_bbox = [p for p in relevant if in_bounds(p)]
    print(f"After bounding box filter: {len(in_bbox)}")

    # step 4: clean and standardize schema
    cleaned = [clean_place(p) for p in in_bbox]

    out_path = BASE_DIR / "data/processed/google_dataset/google_places_cleaned.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(cleaned, f, indent=2)

    print(f"\nSaved {len(cleaned)} cleaned places to {out_path}")

if __name__ == "__main__":
    run()