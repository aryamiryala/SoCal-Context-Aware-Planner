# src/processing/entity_resolution.py
import json, math
from pathlib import Path
from rapidfuzz import fuzz

BASE_DIR = Path(__file__).resolve().parents[2]

NAME_THRESHOLD = 85    # fuzzy match score 0-100
DISTANCE_THRESHOLD = 200  # meters

def haversine(lat1, lon1, lat2, lon2):
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

def run():
    with open(BASE_DIR / "data/processed/google_dataset/google_places_cleaned.json") as f:
        google_places = json.load(f)
    with open(BASE_DIR / "data/processed/yelp_dataset/yelp_socal_businesses.json") as f:
        yelp_businesses = json.load(f)
    with open(BASE_DIR / "data/processed/yelp_dataset/yelp_socal_reviews.json") as f:
        yelp_reviews = json.load(f)
    with open(BASE_DIR / "data/processed/yelp_dataset/yelp_socal_checkins.json") as f:
        yelp_checkins = json.load(f)

    # index yelp reviews and checkins by yelp_id for fast lookup
    reviews_by_yelp_id = {}
    for r in yelp_reviews:
        reviews_by_yelp_id.setdefault(r["yelp_id"], []).append(r)

    checkins_by_yelp_id = {c["yelp_id"]: c for c in yelp_checkins}

    merged = []
    yelp_only = []
    matched_yelp_ids = set()

    # try to match each Yelp business to a Google place
    for yelp in yelp_businesses:
        best_match = None
        best_score = 0

        for google in google_places:
            # name similarity
            name_score = fuzz.token_sort_ratio(
                yelp["name"].lower(),
                google["name"].lower()
            )
            if name_score < NAME_THRESHOLD:
                continue

            # geographic proximity
            dist = haversine(
                yelp["latitude"], yelp["longitude"],
                google["lat"], google["lng"]
            )
            if dist > DISTANCE_THRESHOLD:
                continue

            if name_score > best_score:
                best_score = name_score
                best_match = (google, dist)

        if best_match:
            google, dist = best_match
            matched_yelp_ids.add(yelp["yelp_id"])
            merged.append({
                # identifiers
                "yelp_id": yelp["yelp_id"],
                "google_id": google["google_id"],
                "source": "merged",
                # core location fields
                "name": google["name"],
                "formatted_address": google["formatted_address"],
                "lat": google["lat"],
                "lng": google["lng"],
                "city": yelp.get("city"),
                # activity
                "types": google["types"],
                "categories": yelp.get("categories"),
                # cost
                "price_level": google.get("price_level"),
                "price": yelp.get("price"),
                # ratings
                "google_rating": google.get("rating"),
                "yelp_stars": yelp.get("stars"),
                "user_ratings_total": google.get("user_ratings_total"),
                "yelp_review_count": yelp.get("review_count"),
                # reviews (both sources)
                "google_reviews": google.get("reviews", []),
                "yelp_reviews": reviews_by_yelp_id.get(yelp["yelp_id"], []),
                # crowd
                "checkins": checkins_by_yelp_id.get(yelp["yelp_id"]),
                "opening_hours": google.get("opening_hours"),
                # match metadata
                "match_score": best_score,
                "match_distance_m": round(dist, 2),
            })
        else:
            # no Google match — keep as yelp-only with reviews attached
            yelp_only.append({
                "yelp_id": yelp["yelp_id"],
                "google_id": None,
                "source": "yelp",
                "name": yelp["name"],
                "formatted_address": yelp.get("address"),
                "lat": yelp["latitude"],
                "lng": yelp["longitude"],
                "city": yelp.get("city"),
                "types": [],
                "categories": yelp.get("categories"),
                "price_level": None,
                "price": yelp.get("price"),
                "google_rating": None,
                "yelp_stars": yelp.get("stars"),
                "user_ratings_total": None,
                "yelp_review_count": yelp.get("review_count"),
                "google_reviews": [],
                "yelp_reviews": reviews_by_yelp_id.get(yelp["yelp_id"], []),
                "checkins": checkins_by_yelp_id.get(yelp["yelp_id"]),
                "opening_hours": None,
            })

    # google-only: all google places not matched to any yelp business
    matched_google_ids = {m["google_id"] for m in merged}
    google_only = []
    for google in google_places:
        if google["google_id"] in matched_google_ids:
            continue
        google_only.append({
            "yelp_id": None,
            "google_id": google["google_id"],
            "source": "google",
            "name": google["name"],
            "formatted_address": google["formatted_address"],
            "lat": google["lat"],
            "lng": google["lng"],
            "city": None,
            "types": google["types"],
            "categories": None,
            "price_level": google.get("price_level"),
            "price": None,
            "google_rating": google.get("rating"),
            "yelp_stars": None,
            "user_ratings_total": google.get("user_ratings_total"),
            "yelp_review_count": None,
            "google_reviews": google.get("reviews", []),
            "yelp_reviews": [],
            "checkins": None,
            "opening_hours": google.get("opening_hours"),
        })

    # save all three
    out_dir = BASE_DIR / "data/processed"
    out_dir.mkdir(parents=True, exist_ok=True)

    with open(out_dir / "merged_locations.json", "w") as f:
        json.dump(merged, f, indent=2)
    with open(out_dir / "yelp_only_locations.json", "w") as f:
        json.dump(yelp_only, f, indent=2)
    with open(out_dir / "google_only_locations.json", "w") as f:
        json.dump(google_only, f, indent=2)

    print(f"Merged nodes:      {len(merged)}")
    print(f"Yelp-only nodes:   {len(yelp_only)}")
    print(f"Google-only nodes: {len(google_only)}")
    print(f"Total KG nodes:    {len(merged) + len(yelp_only) + len(google_only)}")

if __name__ == "__main__":
    run()