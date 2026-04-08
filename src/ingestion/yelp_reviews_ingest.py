import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]


RAW_PATH = BASE_DIR / "data/raw/yelp_dataset/yelp_academic_dataset_review.json"
OUT_PATH = BASE_DIR / "data/processed/yelp_dataset/yelp_socal_reviews.json"
BIZ_PATH = BASE_DIR / "data/processed/yelp_dataset/yelp_socal_businesses.json"

# Load your already-filtered SoCal business IDs
with open(BIZ_PATH) as f:
    socal_ids = {biz["yelp_id"] for biz in json.load(f)}

print(f"Filtering reviews for {len(socal_ids)} SoCal locations...")

results = []
with open(RAW_PATH, encoding="utf-8") as f:
    for line in f:
        review = json.loads(line)
        if review["business_id"] in socal_ids:
            results.append({
                "review_id": review["review_id"],
                "yelp_id": review["business_id"],
                "stars": review["stars"],
                "text": review["text"],
                "date": review["date"],
                "useful": review["useful"]
            })

with open(OUT_PATH, "w") as f:
    json.dump(results, f, indent=2)

print(f"Found {len(results)} reviews for SoCal locations")