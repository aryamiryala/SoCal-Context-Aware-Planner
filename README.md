# SoCal-Context-Aware-Planner

# Data Collection Summary

## Sources

### 1. Yelp Open Dataset
- **URL:** https://business.yelp.com/data/resources/open-dataset/
- **How:** Downloaded academic dataset, filtered to SoCal bounding box (lat 32.5–35.0, lon -120.5 to -114.0) with outdoor-relevant categories
- **Script:** `src/ingestion/yelp_ingest.py`
- **Output:**
  - `yelp_socal_businesses.json` — 116 businesses (heavily Santa Barbara)
  - `yelp_socal_reviews.json` — 4,956 reviews (used for NLP pipeline)
  - `yelp_socal_checkins.json` — 113 checkins (used as CrowdLevel proxy)
- **Note:** Santa Barbara skew meant Yelp is used primarily for review text in the NLP pipeline, not as the primary location source

---

### 2. Google Places API
- **URL:** https://developers.google.com/maps/documentation/places/web-service
- **How:** Queried Nearby Search + Place Details endpoints across 10 SoCal search centers (LA, SD, Palm Springs, Big Bear, Joshua Tree, Laguna Beach, Ventura, Santa Monica, Malibu, Santa Barbara) with 7 outdoor keywords (hiking, beach, park, outdoor, nature, camping, trail)
- **Script:** `src/ingestion/google_places.py`
- **Cleaning:** `src/processing/clean_google_places.py` — dropped places with no rating/reviews, filtered to relevant outdoor types, applied bounding box
- **Output:** `google_places_cleaned.json` — 1,309 places
- **Fields captured:** name, place_id, lat/lng, types, rating, user_ratings_total, price_level, reviews (up to 5 full texts), opening_hours

---

### 3. Open-Meteo Historical Weather API
- **URL:** https://archive-api.open-meteo.com/v1/archive
- **How:** Queried daily weather for each location's lat/lng for full year 2024, then aggregated to monthly averages in Python
- **Script:** `src/ingestion/open_meteo.py`
- **Output:** `weather_by_location.json` — 16,884 records (1,407 locations × 12 months)
- **Fields captured:** temp_max_c, temp_min_c, temp_mean_c, precipitation_mm, windspeed_max_kmh, month_name, season
- **Note:** No API key required. Free with no rate limit (used 1.5–3s sleep between requests to stay under limit)

---

### 4. NPS Visitor Use Statistics
- **URL:** https://irma.nps.gov/Stats/
- **How:** Manually downloaded monthly visitation CSVs for each park from the IRMA portal (Recreation Visits By Month report, 2019–2024)
- **Script:** `src/ingestion/nps_stats.py`
- **Parks collected:**
  - Joshua Tree National Park (JOTR)
  - Channel Islands National Park (CHIS)
  - Santa Monica Mountains NRA (SAMO)
  - Cabrillo National Monument (CABR)
- **Output:** `nps_visitation.json` — 288 records (4 parks × 6 years × 12 months)
- **Fields captured:** park_code, park_name, year, month_num, month_name, season, recreation_visitors

---

## Entity Resolution (Yelp + Google)
- **Script:** `src/processing/entity_resolution.py`
- **Algorithm:** Fuzzy name matching (threshold 85/100) + Haversine distance (threshold 200m)
- **Results:**
  - Merged nodes: 17 (Yelp + Google matched)
  - Yelp-only nodes: 99
  - Google-only nodes: 1,292
  - **Total location nodes: 1,408**
- **Match quality:** 16/17 scored 100/100 name similarity, 1 scored 85 (verified correct)

---

## Course Requirements

| Requirement | Target | Actual |
|---|---|---|
| Distinct sources | 3+ | 4 ✅ |
| Total documents | 5,000+ | 6,494 ✅ |
| Structured source 500+ records | 1 | Google Places 1,309 ✅ |

**Document count breakdown:**
- Google Places: 1,309
- Yelp businesses: 116
- Yelp reviews: 4,956
- Yelp checkins: 113
- **Total: 6,494**

---

## Processed Files

```
data/processed/
├── entity_resolution/
│   ├── merged_locations.json       ← 17 records
│   ├── yelp_only_locations.json    ← 99 records
│   └── google_only_locations.json  ← 1,292 records
├── weather_by_location.json        ← 16,884 records
├── nps_visitation.json             ← 288 records
└── yelp_dataset/
    ├── yelp_socal_businesses.json  ← 116 records
    ├── yelp_socal_reviews.json     ← 4,956 records
    └── yelp_socal_checkins.json    ← 113 records
```