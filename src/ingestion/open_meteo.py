# src/ingestion/open_meteo.py
import requests, json, time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
BASE_URL = "https://archive-api.open-meteo.com/v1/archive"

# one full year of monthly averages
START_DATE = "2024-01-01"
END_DATE   = "2024-12-31"

MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December"
]

SEASON_MAP = {
    1: "Winter", 2: "Winter",
    3: "Spring", 4: "Spring",  5: "Spring",
    6: "Summer", 7: "Summer",  8: "Summer",
    9: "Fall",  10: "Fall",   11: "Fall",
    12: "Winter"
}

def fetch_weather(lat, lng):
    params = {
        "latitude": lat,
        "longitude": lng,
        "start_date": START_DATE,
        "end_date": END_DATE,
        "daily": "temperature_2m_max,temperature_2m_min,temperature_2m_mean,precipitation_sum,windspeed_10m_max",
        "timezone": "America/Los_Angeles"
    }
    resp = requests.get(BASE_URL, params=params, timeout=10)
    resp.raise_for_status()
    return resp.json()

def parse_weather(data, location_id, location_name):
    daily = data.get("daily", {})
    times        = daily.get("time", [])
    temp_max     = daily.get("temperature_2m_max", [])
    temp_min     = daily.get("temperature_2m_min", [])
    temp_mean    = daily.get("temperature_2m_mean", [])
    precip       = daily.get("precipitation_sum", [])
    wind         = daily.get("windspeed_10m_max", [])

    # group daily values by month
    from collections import defaultdict
    monthly = defaultdict(lambda: {
        "temp_max": [], "temp_min": [], "temp_mean": [],
        "precip": [], "wind": []
    })

    for i, t in enumerate(times):
        month_num = int(t.split("-")[1])
        m = monthly[month_num]
        if temp_max[i] is not None:  m["temp_max"].append(temp_max[i])
        if temp_min[i] is not None:  m["temp_min"].append(temp_min[i])
        if temp_mean[i] is not None: m["temp_mean"].append(temp_mean[i])
        if precip[i] is not None:    m["precip"].append(precip[i])
        if wind[i] is not None:      m["wind"].append(wind[i])

    def avg(lst): return round(sum(lst) / len(lst), 2) if lst else None
    def total(lst): return round(sum(lst), 2) if lst else None

    records = []
    for month_num in sorted(monthly.keys()):
        m = monthly[month_num]
        records.append({
            "location_id": location_id,
            "location_name": location_name,
            "lat": data["latitude"],
            "lng": data["longitude"],
            "month_num": month_num,
            "month_name": MONTH_NAMES[month_num - 1],
            "season": SEASON_MAP[month_num],
            "temp_max_c": avg(m["temp_max"]),
            "temp_min_c": avg(m["temp_min"]),
            "temp_mean_c": avg(m["temp_mean"]),
            "precipitation_mm": total(m["precip"]),  # total makes more sense for rain
            "windspeed_max_kmh": avg(m["wind"]),
        })
    return records

def load_locations():
    locations = []
    for fname in ["merged_locations.json", "yelp_only_locations.json", "google_only_locations.json"]:
        with open(BASE_DIR / "data/processed/entity_resolution" / fname) as f:
            data = json.load(f)
        for loc in data:
            lid = loc.get("google_id") or loc.get("yelp_id")
            locations.append({
                "id": lid,
                "name": loc["name"],
                "lat": loc["lat"],
                "lng": loc["lng"],
                "source": loc["source"]
            })
    return locations

def fetch_weather_with_retry(lat, lng, retries=5):
    for attempt in range(retries):
        try:
            return fetch_weather(lat, lng)
        except Exception as e:
            if "429" in str(e):
                wait = 10 * (attempt + 1)  # 10s, 20s, 30s, 40s, 50s
                print(f"  Rate limited, waiting {wait}s...")
                time.sleep(wait)
            else:
                raise e
    raise Exception(f"Failed after {retries} retries")

def run():
    locations = load_locations()
    print(f"Total locations to query: {len(locations)}")

    # load already-fetched location_ids so we can resume
    out_path = BASE_DIR / "data/processed/weather_by_location.json"
    if out_path.exists():
        with open(out_path) as f:
            all_weather = json.load(f)
        done_ids = {r["location_id"] for r in all_weather}
        print(f"Resuming — {len(done_ids)} locations already fetched")
    else:
        all_weather = []
        done_ids = set()

    failed = []

    for i, loc in enumerate(locations):
        if loc["id"] in done_ids:
            print(f"[{i+1}/{len(locations)}] Skipping {loc['name']} (already done)")
            continue

        print(f"[{i+1}/{len(locations)}] {loc['name']}")
        try:
            data = fetch_weather_with_retry(loc["lat"], loc["lng"])
            records = parse_weather(data, loc["id"], loc["name"])
            all_weather.extend(records)
            time.sleep(1.5)  # increased from 0.1 to 0.5
        except Exception as e:
            print(f"  ERROR: {e}")
            failed.append(loc)
            continue

        # save every 50 locations so progress isn't lost
        if (i + 1) % 50 == 0:
            with open(out_path, "w") as f:
                json.dump(all_weather, f, indent=2)
            print(f"  Progress saved ({len(all_weather)} records)")

    with open(out_path, "w") as f:
        json.dump(all_weather, f, indent=2)

    print(f"\nDone. {len(all_weather)} monthly weather records saved")
    print(f"Failed: {len(failed)} locations")

if __name__ == "__main__":
    run()