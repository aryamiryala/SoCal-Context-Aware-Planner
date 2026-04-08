# src/ingestion/google_places.py
import requests, os, json, time
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()
API_KEY = os.getenv("GOOGLE_PLACES_API_KEY")
BASE_URL = "https://maps.googleapis.com/maps/api/place"
BASE_DIR = Path(__file__).resolve().parents[2]


SOCAL_SEARCHES = [
    {"location": "34.0522,-118.2437", "name": "Los Angeles"},    # LA
    {"location": "32.7157,-117.1611", "name": "San Diego"},      # San Diego
    {"location": "33.8303,-116.5453", "name": "Palm Springs"},   # Palm Springs
    {"location": "34.2439,-116.9114", "name": "Big Bear"},       # Big Bear
    {"location": "33.8734,-115.9010", "name": "Joshua Tree"},    # Joshua Tree
    {"location": "33.5427,-117.7854", "name": "Laguna Beach"},   # Laguna Beach
    {"location": "34.2805,-119.2945", "name": "Ventura"},        # Ventura
    {"location": "34.0195,-118.4912", "name": "Santa Monica"},   # Santa Monica
    {"location": "34.0037,-118.8076", "name": "Malibu"},         # Malibu
    {"location": "34.4208,-119.6982", "name": "Santa Barbara"}
]

KEYWORDS = ["hiking", "beach", "park", "outdoor", "nature", "camping", "trail"]

def nearby_search(location, keyword, page_token=None):
    params = {
        "location": location,
        "radius": 30000,        # 30km radius
        "keyword": keyword,
        "key": API_KEY,
    }
    if page_token:
        params = {"pagetoken": page_token, "key": API_KEY}
    
    resp = requests.get(f"{BASE_URL}/nearbysearch/json", params=params)
    resp.raise_for_status()
    return resp.json()

def place_details(place_id):
    params = {
        "place_id": place_id,
        "fields": "name,place_id,geometry,types,rating,user_ratings_total,price_level,reviews,opening_hours,formatted_address",
        "key": API_KEY,
    }
    resp = requests.get(f"{BASE_URL}/details/json", params=params)
    resp.raise_for_status()
    return resp.json().get("result", {})

def run():
    out_path = BASE_DIR / "data/raw/google_dataset/google_places_socal.json"

    # load existing data so we don't re-fetch already pulled places
    if out_path.exists():
        with open(out_path) as f:
            all_places = json.load(f)
        seen_ids = {p["place_id"] for p in all_places if "place_id" in p}
        print(f"Loaded {len(all_places)} existing places, resuming...")
    else:
        all_places = []
        seen_ids = set()

    for area in SOCAL_SEARCHES:
        for keyword in KEYWORDS:
            print(f"Searching {area['name']} — {keyword}")
            page_token = None

            for page in range(3):   # up to 3 pages = 60 results per search
                data = nearby_search(area["location"], keyword, page_token)
                results = data.get("results", [])

                for place in results:
                    pid = place["place_id"]
                    if pid in seen_ids:
                        continue
                    seen_ids.add(pid)

                    # fetch full details including reviews
                    details = place_details(pid)
                    all_places.append(details)
                    time.sleep(0.1)  # stay under rate limit

                page_token = data.get("next_page_token")
                if not page_token:
                    break
                time.sleep(2)   # required before next_page_token becomes valid

    with open(out_path, "w") as f:
        json.dump(all_places, f, indent=2)

    print(f"\nDone. Saved {len(all_places)} places to {out_path}")

if __name__ == "__main__":
    run()