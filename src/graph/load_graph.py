# src/graph/load_graph.py
import json, os
from pathlib import Path
from neo4j import GraphDatabase
from dotenv import load_dotenv
import math

load_dotenv()
BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data/processed/entity_resolution"

driver = GraphDatabase.driver(
    os.getenv("NEO4J_URI"),
    auth=(os.getenv("NEO4J_USER"), os.getenv("NEO4J_PASSWORD"))
)

# ── helpers ──────────────────────────────────────────────────────────────────

def load_json(fname):
    with open(DATA_DIR / fname) as f:
        return json.load(f)

def run_query(query, params=None):
    with driver.session(database="socal") as session:
        session.run(query, params or {})

# ── constraints + indexes ─────────────────────────────────────────────────────

def create_constraints():
    print("Creating constraints...")
    queries = [
        "CREATE CONSTRAINT IF NOT EXISTS FOR (l:Location) REQUIRE l.location_id IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (a:Activity) REQUIRE a.name IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (w:WeatherCondition) REQUIRE w.weather_id IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (m:Month) REQUIRE m.month_num IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (s:Season) REQUIRE s.name IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (c:CrowdLevel) REQUIRE c.crowd_id IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (r:ReviewEvidence) REQUIRE r.review_id IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (cost:Cost) REQUIRE cost.tier IS UNIQUE",
    ]
    for q in queries:
        run_query(q)
    print("  Done.")

# ── Month + Season nodes ──────────────────────────────────────────────────────

def load_months_seasons():
    print("Loading Month and Season nodes...")
    month_data = [
        (1,"January","Winter"), (2,"February","Winter"),
        (3,"March","Spring"),   (4,"April","Spring"),
        (5,"May","Spring"),     (6,"June","Summer"),
        (7,"July","Summer"),    (8,"August","Summer"),
        (9,"September","Fall"), (10,"October","Fall"),
        (11,"November","Fall"), (12,"December","Winter")
    ]
    for month_num, month_name, season in month_data:
        run_query("""
            MERGE (s:Season {name: $season})
            MERGE (m:Month {month_num: $month_num})
              SET m.name = $month_name
            MERGE (m)-[:BELONGS_TO_SEASON]->(s)
        """, {"season": season, "month_num": month_num, "month_name": month_name})
    print("  Done.")

# ── Cost nodes ────────────────────────────────────────────────────────────────

def load_cost_nodes():
    print("Loading Cost nodes...")
    tiers = [
        (0, "Free"),
        (1, "Inexpensive"),
        (2, "Moderate"),
        (3, "Expensive"),
        (4, "Very Expensive")
    ]
    for tier, label in tiers:
        run_query("""
            MERGE (c:Cost {tier: $tier})
              SET c.label = $label
        """, {"tier": tier, "label": label})
    print("  Done.")

# ── Distance Computation ──────────────────────────────────────────────────────

def haversine_miles(lat1, lng1, lat2=34.0522, lng2=-118.2437):
    """Distance in miles from a point to LA (default origin)."""
    R = 3958.8
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

# ── Activity nodes ────────────────────────────────────────────────────────────

ACTIVITY_TYPE_MAP = {
    "park":               "Park",
    "campground":         "Camping",
    "rv_park":            "Camping",
    "natural_feature":    "Nature",
    "tourist_attraction": "Attraction",
    "hiking_area":        "Hiking",
    "beach":              "Beach",
    "museum":             "Cultural",
    "aquarium":           "Cultural",
    "zoo":                "Cultural",
    "stadium":            "Recreation",
    "amusement_park":     "Recreation",
    "travel_agency":      "Attraction",
}

SEASON_FEASIBILITY = {
    "Hiking":     ["Spring", "Fall", "Winter"],
    "Beach":      ["Summer", "Spring"],
    "Camping":    ["Spring", "Summer", "Fall"],
    "Park":       ["Spring", "Summer", "Fall", "Winter"],
    "Nature":     ["Spring", "Fall"],
    "Attraction": ["Spring", "Summer", "Fall", "Winter"],
    "Cultural":   ["Spring", "Summer", "Fall", "Winter"],
    "Recreation": ["Spring", "Summer", "Fall", "Winter"],
}

def load_activities():
    print("Loading Activity nodes...")

    # Explicitly seed Beach and Hiking since no Google type reliably maps to them
    for activity in ["Beach", "Hiking"]:
        run_query("MERGE (a:Activity {name: $name})", {"name": activity})
        for season in SEASON_FEASIBILITY.get(activity, []):
            run_query("""
                MATCH (a:Activity {name: $activity})
                MATCH (s:Season {name: $season})
                MERGE (a)-[:FEASIBLE_IN_SEASON]->(s)
            """, {"activity": activity, "season": season})

    # Discover remaining activity types from location data
    activities = set()
    for fname in ["merged_locations.json", "google_only_locations.json", "yelp_only_locations.json"]:
        for loc in load_json(fname):
            for t in loc.get("types", []):
                if t in ACTIVITY_TYPE_MAP:
                    activities.add(ACTIVITY_TYPE_MAP[t])

    for activity in activities:
        run_query("MERGE (a:Activity {name: $name})", {"name": activity})
        for season in SEASON_FEASIBILITY.get(activity, []):
            run_query("""
                MATCH (a:Activity {name: $activity})
                MATCH (s:Season {name: $season})
                MERGE (a)-[:FEASIBLE_IN_SEASON]->(s)
            """, {"activity": activity, "season": season})

    print(f"  Loaded {len(activities) + 2} activity types.")

# ── Location nodes ────────────────────────────────────────────────────────────

def get_crowd_level(user_ratings_total):
    if user_ratings_total is None:   return "Unknown"
    elif user_ratings_total < 100:   return "Low"
    elif user_ratings_total < 500:   return "Moderate"
    elif user_ratings_total < 2000:  return "High"
    else:                            return "Very High"

def get_price_tier(loc):
    if loc.get("price_level") is not None:
        return int(loc["price_level"])
    return 0  # default free for outdoor locations

def assign_activity(location_id, activity_name):
    """Helper to create a HAS_ACTIVITY edge from a Location to an Activity node."""
    run_query("""
        MATCH (l:Location {location_id: $location_id})
        MATCH (a:Activity {name: $activity})
        MERGE (l)-[:HAS_ACTIVITY]->(a)
    """, {"location_id": location_id, "activity": activity_name})

def load_locations():
    print("Loading Location nodes...")
    count = 0
    for fname in ["merged_locations.json", "google_only_locations.json", "yelp_only_locations.json"]:
        locations = load_json(fname)
        for loc in locations:
            location_id = loc.get("google_id") or loc.get("yelp_id")
            crowd_label = get_crowd_level(loc.get("user_ratings_total"))
            price_tier  = get_price_tier(loc)

            # create Location node
            run_query("""
                MERGE (l:Location {location_id: $location_id})
                  SET l.name               = $name,
                      l.address            = $address,
                      l.lat                = $lat,
                      l.lng                = $lng,
                      l.city               = $city,
                      l.source             = $source,
                      l.google_rating      = $google_rating,
                      l.yelp_stars         = $yelp_stars,
                      l.review_count       = $review_count,
                      l.opening_hours      = $opening_hours,
                      l.distanceFromOrigin = $distance
            """, {
                "location_id":   location_id,
                "name":          loc["name"],
                "address":       loc.get("formatted_address"),
                "lat":           loc["lat"],
                "lng":           loc["lng"],
                "city":          loc.get("city"),
                "source":        loc["source"],
                "google_rating": loc.get("google_rating"),
                "yelp_stars":    loc.get("yelp_stars"),
                "review_count":  loc.get("user_ratings_total") or loc.get("yelp_review_count"),
                "opening_hours": str(loc.get("opening_hours")) if loc.get("opening_hours") else None,
                "distance":      round(haversine_miles(loc["lat"], loc["lng"]), 1)
            })

            # ── Activity edges via Google type map ────────────────────────────
            for t in loc.get("types", []):
                if t in ACTIVITY_TYPE_MAP:
                    assign_activity(location_id, ACTIVITY_TYPE_MAP[t])

            # ── Extended name-based activity enrichment ───────────────────────
            name = loc["name"].lower()

            if any(w in name for w in ["beach", "shore", "coast", "surf"]):
                assign_activity(location_id, "Beach")

            if any(w in name for w in ["trail", "trailhead", "hike", "hiking",
                                        "canyon", "mountain", "forest",
                                        "wilderness", "peak", "summit"]):
                assign_activity(location_id, "Hiking")

            if any(w in name for w in ["park", "preserve", "reserve", "nature"]):
                assign_activity(location_id, "Nature")

            if any(w in name for w in ["adventure", "kayak", "paddle", "dive",
                                        "snorkel", "boat", "jet ski", "surf school"]):
                assign_activity(location_id, "Recreation")

            if any(w in name for w in ["museum", "courthouse", "carousel",
                                        "castle", "historic"]):
                assign_activity(location_id, "Cultural")

            # ── Cost edge ─────────────────────────────────────────────────────
            run_query("""
                MATCH (l:Location {location_id: $location_id})
                MATCH (c:Cost {tier: $tier})
                MERGE (l)-[:HAS_COST_TIER]->(c)
            """, {"location_id": location_id, "tier": price_tier})

            # ── CrowdLevel node + edge (Google ratings proxy) ─────────────────
            crowd_id = f"{location_id}_crowd"
            run_query("""
                MERGE (cl:CrowdLevel {crowd_id: $crowd_id})
                  SET cl.level              = $level,
                      cl.user_ratings_total = $total,
                      cl.source             = 'google_ratings'
                WITH cl
                MATCH (l:Location {location_id: $location_id})
                MERGE (l)-[:HAS_CROWD_LEVEL]->(cl)
            """, {
                "crowd_id":    crowd_id,
                "level":       crowd_label,
                "total":       loc.get("user_ratings_total"),
                "location_id": location_id
            })

            count += 1
            if count % 100 == 0:
                print(f"  {count}/1408 locations loaded...")

    print(f"  Done. {count} locations loaded.")

# ── ReviewEvidence nodes ──────────────────────────────────────────────────────

def load_reviews():
    print("Loading ReviewEvidence nodes...")
    count = 0
    for fname in ["merged_locations.json", "google_only_locations.json", "yelp_only_locations.json"]:
        for loc in load_json(fname):
            location_id = loc.get("google_id") or loc.get("yelp_id")

            # google reviews
            for i, r in enumerate(loc.get("google_reviews", [])):
                if not r.get("text"):
                    continue
                review_id = f"{location_id}_g_{i}"
                run_query("""
                    MERGE (r:ReviewEvidence {review_id: $review_id})
                      SET r.text        = $text,
                          r.rating      = $rating,
                          r.source_type = 'UserReview',
                          r.platform    = 'google'
                    WITH r
                    MATCH (l:Location {location_id: $location_id})
                    MERGE (l)-[:HAS_REVIEW_EVIDENCE]->(r)
                """, {
                    "review_id":   review_id,
                    "text":        r["text"],
                    "rating":      r.get("rating"),
                    "location_id": location_id
                })
                count += 1

            # yelp reviews
            for i, r in enumerate(loc.get("yelp_reviews", [])):
                if not r.get("text"):
                    continue
                review_id = f"{location_id}_y_{i}"
                run_query("""
                    MERGE (r:ReviewEvidence {review_id: $review_id})
                      SET r.text        = $text,
                          r.rating      = $rating,
                          r.source_type = 'UserReview',
                          r.platform    = 'yelp'
                    WITH r
                    MATCH (l:Location {location_id: $location_id})
                    MERGE (l)-[:HAS_REVIEW_EVIDENCE]->(r)
                """, {
                    "review_id":   review_id,
                    "text":        r["text"],
                    "rating":      r.get("stars"),
                    "location_id": location_id
                })
                count += 1

    print(f"  Done. {count} reviews loaded.")

# ── WeatherCondition nodes ────────────────────────────────────────────────────

def load_weather():
    print("Loading WeatherCondition nodes...")
    weather_data = load_json("weather_by_location.json")
    count = 0
    for w in weather_data:
        weather_id = f"{w['location_id']}_{w['month_num']}"
        run_query("""
            MERGE (wc:WeatherCondition {weather_id: $weather_id})
              SET wc.temp_max_c        = $temp_max,
                  wc.temp_min_c        = $temp_min,
                  wc.temp_mean_c       = $temp_mean,
                  wc.precipitation_mm  = $precip,
                  wc.windspeed_max_kmh = $wind
            WITH wc
            MATCH (l:Location {location_id: $location_id})
            MERGE (l)-[:EXPERIENCES_WEATHER]->(wc)
            WITH wc
            MATCH (m:Month {month_num: $month_num})
            MERGE (wc)-[:OCCURS_IN_MONTH]->(m)
        """, {
            "weather_id":  weather_id,
            "temp_max":    w.get("temp_max_c"),
            "temp_min":    w.get("temp_min_c"),
            "temp_mean":   w.get("temp_mean_c"),
            "precip":      w.get("precipitation_mm"),
            "wind":        w.get("windspeed_max_kmh"),
            "location_id": w["location_id"],
            "month_num":   w["month_num"],
        })
        count += 1
        if count % 1000 == 0:
            print(f"  {count}/{len(weather_data)} weather records loaded...")
    print(f"  Done. {count} weather records loaded.")

# ── NPS CrowdLevel nodes ──────────────────────────────────────────────────────

NPS_TO_LOCATION = {
    "JOTR": "Joshua Tree National Park",
    "CHIS": "Channel Islands National Park",
    "SAMO": "Santa Monica Mountains NRA",
    "CABR": "Cabrillo National Monument",
}

def load_nps():
    print("Loading NPS CrowdLevel nodes...")
    nps_data = load_json("nps_visitation.json")
    count = 0
    for record in nps_data:
        crowd_id = f"nps_{record['park_code']}_{record['year']}_{record['month_num']}"
        run_query("""
            MERGE (cl:CrowdLevel {crowd_id: $crowd_id})
              SET cl.recreation_visitors = $visitors,
                  cl.year               = $year,
                  cl.source             = 'nps_official',
                  cl.park_code          = $park_code,
                  cl.level              = CASE
                    WHEN $visitors < 10000  THEN 'Low'
                    WHEN $visitors < 50000  THEN 'Moderate'
                    WHEN $visitors < 150000 THEN 'High'
                    ELSE 'Very High'
                  END
            WITH cl
            MATCH (m:Month {month_num: $month_num})
            MERGE (cl)-[:RECORDED_IN_MONTH]->(m)
        """, {
            "crowd_id":  crowd_id,
            "visitors":  record["recreation_visitors"],
            "year":      record["year"],
            "park_code": record["park_code"],
            "month_num": record["month_num"],
        })

        # link to Location by name match
        run_query("""
            MATCH (l:Location)
            WHERE toLower(l.name) CONTAINS toLower($park_name)
            MATCH (cl:CrowdLevel {crowd_id: $crowd_id})
            MERGE (l)-[:HAS_HISTORICAL_CROWDS]->(cl)
        """, {
            "park_name": NPS_TO_LOCATION[record["park_code"]],
            "crowd_id":  crowd_id
        })
        count += 1
    print(f"  Done. {count} NPS records loaded.")

# ── main ──────────────────────────────────────────────────────────────────────

def run():
    print("=== Loading SoCal KG into Neo4j ===\n")
    create_constraints()
    load_months_seasons()
    load_cost_nodes()
    load_activities()
    load_locations()
    load_reviews()
    load_weather()
    load_nps()
    driver.close()
    print("\n=== Done! KG loaded successfully ===")

if __name__ == "__main__":
    run()