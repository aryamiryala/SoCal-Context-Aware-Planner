import json
import csv
import os
from pathlib import Path
from dotenv import load_dotenv
from neo4j import GraphDatabase
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError

ROOT = Path(__file__).resolve().parents[2]
load_dotenv()

DB_NAME = "socal"
QUERIES_PATH = ROOT / "src" / "evaluation" / "constraint_queries.json"
RESULTS_CSV = ROOT / "src" / "evaluation" / "constraint_eval_results.csv"

# same SoCal bounds as app.py
LAT_MIN, LAT_MAX = 32.5, 35.0
LON_MIN, LON_MAX = -120.5, -114.0

driver = GraphDatabase.driver(
    os.getenv("NEO4J_URI"),
    auth=(os.getenv("NEO4J_USER"), os.getenv("NEO4J_PASSWORD")),
)

geolocator = Nominatim(user_agent="socal_constraint_eval")


def run_query(query: str, params=None):
    with driver.session(database=DB_NAME) as session:
        result = session.run(query, params or {})
        return [dict(r) for r in result]


def geocode_address(address: str):
    """
    Returns (lat, lng, resolved_address) or raises ValueError.
    """
    try:
        location = geolocator.geocode(address, timeout=10)
        if location is None:
            location = geolocator.geocode(f"{address}, CA", timeout=10)
    except GeocoderTimedOut:
        raise ValueError(f"Geocoder timed out for address: {address}")
    except GeocoderServiceError as e:
        raise ValueError(f"Geocoder service error for '{address}': {e}")

    if location is None:
        raise ValueError(f"Could not geocode address: {address}")

    lat, lng = location.latitude, location.longitude

    if not (LAT_MIN <= lat <= LAT_MAX and LON_MIN <= lng <= LON_MAX):
        raise ValueError(
            f"Address '{address}' resolved outside SoCal bounds: ({lat:.4f}, {lng:.4f})"
        )

    return lat, lng, location.address


def get_recommendations(test_case, origin_lat, origin_lng):
    min_temp_c = (test_case["min_temp_f"] - 32) * 5 / 9
    max_distance_m = test_case["max_distance_miles"] * 1609.34

    query = """
    MATCH (l:Location)-[:HAS_ACTIVITY]->(a:Activity),
          (l)-[:EXPERIENCES_WEATHER]->(w:WeatherCondition)-[:OCCURS_IN_MONTH]->(m:Month {name: $month})
    WHERE a.name IN $activities
      AND w.temp_mean_c >= $min_temp_c
      AND l.lat IS NOT NULL AND l.lng IS NOT NULL
      AND point.distance(
            point({latitude: l.lat, longitude: l.lng}),
            point({latitude: $origin_lat, longitude: $origin_lng})
          ) <= $max_distance_m
      AND (l.google_rating IS NULL OR l.google_rating >= $min_rating)

    OPTIONAL MATCH (l)-[:HAS_HISTORICAL_CROWDS]->(nps_c:CrowdLevel)-[:RECORDED_IN_MONTH]->(m)
    OPTIONAL MATCH (l)-[:HAS_REVIEW_EVIDENCE]->(:ReviewEvidence)-[:INDICATES_CROWDING]->(nlp_c:CrowdLevel)
    WHERE nlp_c.source = 'review_nlp'
    OPTIONAL MATCH (l)-[:HAS_CROWD_LEVEL]->(proxy_c:CrowdLevel)

    WITH l, a, w, nps_c, proxy_c,
         collect(nlp_c.level) AS nlp_levels,
         point.distance(
             point({latitude: l.lat, longitude: l.lng}),
             point({latitude: $origin_lat, longitude: $origin_lng})
         ) / 1609.34 AS dist_miles

    WITH l, a, w, nps_c, proxy_c, dist_miles,
         size([x IN nlp_levels WHERE x = 'Low']) AS nlp_low,
         size([x IN nlp_levels WHERE x = 'Moderate']) AS nlp_mod,
         size([x IN nlp_levels WHERE x = 'High']) AS nlp_high,
         size([x IN nlp_levels WHERE x = 'Very High']) AS nlp_vhigh

    WITH l, a, w, nps_c, proxy_c, dist_miles,
         CASE
           WHEN (nlp_vhigh >= nlp_high AND nlp_vhigh >= nlp_mod AND nlp_vhigh >= nlp_low AND nlp_vhigh > 0) THEN 'Very High'
           WHEN (nlp_high >= nlp_mod AND nlp_high >= nlp_low AND nlp_high > 0) THEN 'High'
           WHEN (nlp_mod >= nlp_low AND nlp_mod > 0) THEN 'Moderate'
           WHEN (nlp_low > 0) THEN 'Low'
           ELSE NULL
         END AS nlp_label,
         (nlp_low + nlp_mod + nlp_high + nlp_vhigh) AS nlp_review_count

    WITH l, a, w, dist_miles,
         CASE
           WHEN nps_c.level IS NOT NULL THEN nps_c.level
           WHEN nlp_label IS NOT NULL THEN nlp_label
           ELSE proxy_c.level
         END AS crowd_label,
         CASE
           WHEN nps_c.level IS NOT NULL THEN nps_c.source
           WHEN nlp_label IS NOT NULL THEN 'review_nlp'
           ELSE proxy_c.source
         END AS crowd_source,
         CASE
           WHEN nps_c.level IS NOT NULL THEN nps_c.recreation_visitors
           WHEN nlp_label IS NOT NULL THEN nlp_review_count
           ELSE proxy_c.user_ratings_total
         END AS crowd_signal

    WHERE crowd_label IN $crowd_levels

    WITH l,
         collect(DISTINCT a.name) AS activities,
         round((avg(w.temp_mean_c) * 9/5 + 32) * 10) / 10 AS avg_temp_f,
         crowd_label,
         crowd_source,
         avg(crowd_signal) AS crowd_signal,
         min(dist_miles) AS miles_from_origin

    RETURN l.name AS name,
           l.city AS city,
           activities,
           avg_temp_f,
           crowd_label,
           crowd_source,
           toInteger(crowd_signal) AS crowd_signal,
           round(miles_from_origin * 10) / 10 AS miles
    ORDER BY
        CASE crowd_label
            WHEN 'Low' THEN 1
            WHEN 'Moderate' THEN 2
            WHEN 'High' THEN 3
            WHEN 'Very High' THEN 4
            ELSE 5
        END ASC,
        avg_temp_f DESC
    LIMIT 10
    """

    return run_query(query, {
        "month": test_case["month"],
        "activities": test_case["activities"],
        "min_temp_c": min_temp_c,
        "origin_lat": origin_lat,
        "origin_lng": origin_lng,
        "max_distance_m": max_distance_m,
        "crowd_levels": test_case["crowd_levels"],
        "min_rating": test_case["min_rating"],
    })


def evaluate_top_result(test_case, rec):
    if rec is None:
        return {
            "has_result": False,
            "activity_ok": False,
            "temp_ok": False,
            "crowd_ok": False,
            "distance_ok": False,
            "all_constraints_satisfied": False
        }

    activity_ok = any(a in test_case["activities"] for a in rec["activities"])
    temp_ok = rec["avg_temp_f"] >= test_case["min_temp_f"]
    crowd_ok = rec["crowd_label"] in test_case["crowd_levels"]
    distance_ok = rec["miles"] <= test_case["max_distance_miles"]

    return {
        "has_result": True,
        "activity_ok": activity_ok,
        "temp_ok": temp_ok,
        "crowd_ok": crowd_ok,
        "distance_ok": distance_ok,
        "all_constraints_satisfied": activity_ok and temp_ok and crowd_ok and distance_ok
    }

def build_description(tc):
    activity = " / ".join(tc["activities"])
    crowd = " or ".join(tc["crowd_levels"])

    # optional map temp to label like UI
    temp = tc["min_temp_f"]
    if temp >= 75:
        temp_desc = "hot (75°F+)"
    elif temp >= 65:
        temp_desc = "warm (65°F+)"
    elif temp >= 55:
        temp_desc = "mild (55°F+)"
    else:
        temp_desc = f"{temp}°F+"

    return (
        f"{activity} destination in {tc['month']} within "
        f"{tc['max_distance_miles']} miles of {tc['origin']} "
        f"with {temp_desc}, {crowd} crowd levels, "
        f"and at least {tc['min_rating']}⭐ rating"
    )


def main():
    if not QUERIES_PATH.exists():
        print(f"Query file not found: {QUERIES_PATH}")
        return

    with open(QUERIES_PATH, "r", encoding="utf-8") as f:
        test_cases = json.load(f)

    results = []
    satisfied_count = 0

    for tc in test_cases:
        query_id = tc["query_id"]
        origin = tc["origin"]

        try:
            origin_lat, origin_lng, resolved_origin = geocode_address(origin)
        except ValueError as e:
            row = {
                "query_id": query_id,
                #"description": tc["description"], removed description field from JSON
                "description": build_description(tc),
                "origin_input": origin,
                "origin_resolved": "",
                "month": tc["month"],
                "requested_activities": ", ".join(tc["activities"]),
                "requested_crowd_levels": ", ".join(tc["crowd_levels"]),
                "requested_min_temp_f": tc["min_temp_f"],
                "requested_max_distance_miles": tc["max_distance_miles"],
                "top_result_name": "",
                "top_result_city": "",
                "top_result_activities": "",
                "top_result_temp_f": "",
                "top_result_crowd": "",
                "top_result_crowd_source": "",
                "top_result_miles": "",
                "has_result": False,
                "activity_ok": False,
                "temp_ok": False,
                "crowd_ok": False,
                "distance_ok": False,
                "all_constraints_satisfied": False,
                "error": str(e)
            }
            results.append(row)
            continue

        recs = get_recommendations(tc, origin_lat, origin_lng)
        top_rec = recs[0] if recs else None
        eval_result = evaluate_top_result(tc, top_rec)

        row = {
            "query_id": query_id,
            #"description": tc["description"],
            "description": build_description(tc),
            "origin_input": origin,
            "origin_resolved": resolved_origin,
            "month": tc["month"],
            "requested_activities": ", ".join(tc["activities"]),
            "requested_crowd_levels": ", ".join(tc["crowd_levels"]),
            "requested_min_temp_f": tc["min_temp_f"],
            "requested_max_distance_miles": tc["max_distance_miles"],
            "top_result_name": top_rec["name"] if top_rec else "",
            "top_result_city": top_rec["city"] if top_rec else "",
            "top_result_activities": ", ".join(top_rec["activities"]) if top_rec else "",
            "top_result_temp_f": top_rec["avg_temp_f"] if top_rec else "",
            "top_result_crowd": top_rec["crowd_label"] if top_rec else "",
            "top_result_crowd_source": top_rec["crowd_source"] if top_rec else "",
            "top_result_miles": top_rec["miles"] if top_rec else "",
            "has_result": eval_result["has_result"],
            "activity_ok": eval_result["activity_ok"],
            "temp_ok": eval_result["temp_ok"],
            "crowd_ok": eval_result["crowd_ok"],
            "distance_ok": eval_result["distance_ok"],
            "all_constraints_satisfied": eval_result["all_constraints_satisfied"],
            "error": ""
        }

        if eval_result["all_constraints_satisfied"]:
            satisfied_count += 1

        results.append(row)

    with open(RESULTS_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(results[0].keys()))
        writer.writeheader()
        writer.writerows(results)

    total = len(results)
    rate = satisfied_count / total if total else 0

    print("\n=== Constraint Satisfaction Evaluation ===")
    print(f"Total queries: {total}")
    print(f"Satisfied queries: {satisfied_count}")
    print(f"Constraint Satisfaction Rate: {rate:.2%}")
    print(f"Saved detailed results to: {RESULTS_CSV}")

    print("\nFailures:")
    for r in results:
        if not r["all_constraints_satisfied"]:
            print(f"- Query {r['query_id']}: {r['description']}")
            if r["error"]:
                print(f"  Error: {r['error']}")
            else:
                print(
                    f"  Returned: {r['top_result_name']} | "
                    f"activity_ok={r['activity_ok']}, "
                    f"temp_ok={r['temp_ok']}, "
                    f"crowd_ok={r['crowd_ok']}, "
                    f"distance_ok={r['distance_ok']}"
                )


if __name__ == "__main__":
    try:
        main()
    finally:
        driver.close()