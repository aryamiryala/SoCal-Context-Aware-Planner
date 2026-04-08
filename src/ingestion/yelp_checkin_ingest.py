import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]

RAW_PATH = BASE_DIR / "data/raw/yelp_dataset/yelp_academic_dataset_checkin.json"
OUT_PATH = BASE_DIR / "data/processed/yelp_dataset/yelp_socal_checkins.json"
BIZ_PATH = BASE_DIR / "data/processed/yelp_dataset/yelp_socal_businesses.json"

with open(BIZ_PATH) as f:
    socal_ids = {biz["yelp_id"] for biz in json.load(f)}

print(f"Filtering checkins for {len(socal_ids)} SoCal locations...")

results = []
with open(RAW_PATH, encoding="utf-8") as f:
    for line in f:
        checkin = json.loads(line)
        if checkin["business_id"] in socal_ids:
            # 'date' is a comma-separated string of timestamps
            dates = checkin["date"].split(", ")
            results.append({
                "yelp_id": checkin["business_id"],
                "checkin_count": len(dates),
                "dates": dates  # you'll parse month/season from these later
            })

with open(OUT_PATH, "w") as f:
    json.dump(results, f, indent=2)

print(f"Found checkin data for {len(results)} SoCal locations")