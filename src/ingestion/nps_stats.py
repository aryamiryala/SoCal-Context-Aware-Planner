# src/ingestion/nps_stats.py
import csv, json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]

MONTH_MAP = {
    'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4,
    'MAY': 5, 'JUN': 6, 'JUL': 7, 'AUG': 8,
    'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12
}
MONTH_NAMES = [
    'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December'
]
SEASON_MAP = {
    1: 'Winter', 2: 'Winter',
    3: 'Spring', 4: 'Spring',  5: 'Spring',
    6: 'Summer', 7: 'Summer',  8: 'Summer',
    9: 'Fall',  10: 'Fall',   11: 'Fall',
    12: 'Winter'
}

# update these paths to match your actual file locations
FILES = [
    (BASE_DIR / "data/raw/nps_dataset/joshua.csv",      "JOTR", "Joshua Tree National Park"),
    (BASE_DIR / "data/raw/nps_dataset/chanel.csv",       "CHIS", "Channel Islands National Park"),
    (BASE_DIR / "data/raw/nps_dataset/santa_monica.csv", "SAMO", "Santa Monica Mountains NRA"),
    (BASE_DIR / "data/raw/nps_dataset/cabrillo.csv",     "CABR", "Cabrillo National Monument"),
]

# year range to keep
START_YEAR = 2019
END_YEAR   = 2024

def parse_csv(fpath, park_code, park_name):
    with open(fpath, encoding='utf-8-sig') as f:
        lines = f.read().splitlines()

    # find header row (starts with 'Year')
    header_idx = next(i for i, l in enumerate(lines) if l.startswith('Year'))
    header = lines[header_idx].split(',')
    month_cols = [c for c in header if c in MONTH_MAP]

    records = []
    for line in lines[header_idx + 1:]:
        if not line.strip():
            continue
        row = next(csv.reader([line]))
        if len(row) < 2 or not row[0].strip().isdigit():
            continue
        year = int(row[0])
        if year < START_YEAR or year > END_YEAR:
            continue

        for col_name in month_cols:
            col_idx = header.index(col_name)
            val = row[col_idx].strip().replace(',', '')
            if not val:
                continue
            month_num = MONTH_MAP[col_name]
            records.append({
                'park_code': park_code,
                'park_name': park_name,
                'year': year,
                'month_num': month_num,
                'month_name': MONTH_NAMES[month_num - 1],
                'season': SEASON_MAP[month_num],
                'recreation_visitors': int(val)
            })
    return records

def run():
    all_records = []

    for fpath, park_code, park_name in FILES:
        print(f"Parsing {park_name}...")
        records = parse_csv(fpath, park_code, park_name)
        all_records.extend(records)
        print(f"  {len(records)} monthly records ({START_YEAR}-{END_YEAR})")

    out_path = BASE_DIR / "data/processed/entity_resolution/nps_visitation.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(all_records, f, indent=2)

    print(f"\nDone. Saved {len(all_records)} records to {out_path}")

if __name__ == "__main__":
    run()