# src/app.py
import os
import html
from urllib.parse import quote
import streamlit as st
from neo4j import GraphDatabase
from dotenv import load_dotenv
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError

load_dotenv()

# ── SoCal bounding box ────────────────────────────────────────────────────────
LAT_MIN, LAT_MAX = 32.5, 35.0
LON_MIN, LON_MAX = -120.5, -114.0

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="SoCal Trip Planner",
    page_icon="🌴",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Session state init ────────────────────────────────────────────────────────
if "results" not in st.session_state:
    st.session_state["results"] = None
if "selected" not in st.session_state:
    st.session_state["selected"] = None

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=DM+Sans:wght@300;400;500;600&display=swap');

html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }

.stApp {
    background: linear-gradient(135deg, #0a1628 0%, #0d2137 50%, #0a1e30 100%);
    min-height: 100vh;
}

[data-testid="stSidebar"] {
    background: rgba(255,255,255,0.04) !important;
    border-right: 1px solid rgba(255,255,255,0.08);
}
[data-testid="stSidebar"] .stMarkdown p,
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] .stSelectbox label,
[data-testid="stSidebar"] .stMultiSelect label,
[data-testid="stSidebar"] .stSlider label,
[data-testid="stSidebar"] .stTextInput label {
    color: #a8c4d4 !important;
    font-size: 0.8rem !important;
    font-weight: 500 !important;
    letter-spacing: 0.08em !important;
    text-transform: uppercase !important;
}

.hero-title {
    font-family: 'DM Serif Display', serif;
    font-size: 3.2rem;
    color: #ffffff;
    line-height: 1.1;
    margin-bottom: 0.2rem;
}
.hero-title span { color: #4fc3f7; font-style: italic; }
.hero-subtitle {
    color: #7fa8bf;
    font-size: 1rem;
    font-weight: 300;
    letter-spacing: 0.02em;
    margin-bottom: 2rem;
}

.result-card {
    background: rgba(255,255,255,0.05);
    border: 1px solid rgba(79,195,247,0.15);
    border-radius: 12px;
    padding: 1.2rem 1.4rem;
    margin-bottom: 0.6rem;
    position: relative;
    overflow: hidden;
    transition: all 0.2s ease;
}
.result-card::before {
    content: '';
    position: absolute;
    top: 0; left: 0;
    width: 3px; height: 100%;
    background: linear-gradient(180deg, #4fc3f7, #0288d1);
    border-radius: 3px 0 0 3px;
}
.result-card:hover {
    background: rgba(255,255,255,0.08);
    border-color: rgba(79,195,247,0.35);
}
.card-name {
    font-family: 'DM Serif Display', serif;
    font-size: 1.15rem;
    color: #e8f4f8;
    margin-bottom: 0.4rem;
}
.card-meta { display: flex; flex-wrap: wrap; gap: 0.5rem; margin-top: 0.5rem; }
.badge {
    font-size: 0.7rem; font-weight: 600;
    letter-spacing: 0.06em; text-transform: uppercase;
    padding: 0.2rem 0.6rem; border-radius: 20px;
    background: rgba(79,195,247,0.12); color: #4fc3f7;
    border: 1px solid rgba(79,195,247,0.25);
}
.badge-crowd-low   { background:rgba(76,175,80,0.12);  color:#81c784; border-color:rgba(76,175,80,0.25); }
.badge-crowd-mod   { background:rgba(255,193,7,0.12);  color:#ffd54f; border-color:rgba(255,193,7,0.25); }
.badge-crowd-high  { background:rgba(255,152,0,0.12);  color:#ffb74d; border-color:rgba(255,152,0,0.25); }
.badge-crowd-vhigh { background:rgba(244,67,54,0.12);  color:#e57373; border-color:rgba(244,67,54,0.25); }

.card-stat { color: #7fa8bf; font-size: 0.82rem; margin-top: 0.3rem; }
.card-stat strong { color: #c8e6f5; }

.review-box {
    background: rgba(255,255,255,0.03);
    border-left: 2px solid rgba(79,195,247,0.3);
    padding: 0.6rem 0.9rem;
    border-radius: 0 8px 8px 0;
    margin-top: 0.6rem;
    color: #7fa8bf;
    font-size: 0.82rem;
    font-style: italic;
    line-height: 1.5;
}

.metric-row { display: flex; gap: 1rem; margin-bottom: 1.5rem; }
.metric-box {
    flex: 1;
    background: rgba(79,195,247,0.07);
    border: 1px solid rgba(79,195,247,0.15);
    border-radius: 10px;
    padding: 0.9rem 1rem;
    text-align: center;
}
.metric-value {
    font-family: 'DM Serif Display', serif;
    font-size: 1.8rem; color: #4fc3f7; line-height: 1;
}
.metric-label {
    color: #7fa8bf; font-size: 0.72rem;
    text-transform: uppercase; letter-spacing: 0.08em; margin-top: 0.25rem;
}

.section-label {
    color: #4fc3f7; font-size: 0.72rem; font-weight: 600;
    text-transform: uppercase; letter-spacing: 0.1em;
    margin-bottom: 0.75rem; padding-bottom: 0.4rem;
    border-bottom: 1px solid rgba(79,195,247,0.15);
}

/* Address validation feedback boxes */
.addr-ok {
    background: rgba(76,175,80,0.1); border: 1px solid rgba(76,175,80,0.3);
    border-radius: 8px; padding: 0.5rem 0.8rem;
    color: #81c784; font-size: 0.8rem; margin-top: 0.4rem;
}
.addr-err {
    background: rgba(244,67,54,0.1); border: 1px solid rgba(244,67,54,0.3);
    border-radius: 8px; padding: 0.5rem 0.8rem;
    color: #e57373; font-size: 0.8rem; margin-top: 0.4rem;
}

.empty-state { text-align: center; padding: 3rem 1rem; color: #4a7a94; }
.empty-state .icon { font-size: 3rem; margin-bottom: 0.75rem; }

/* ── All buttons: bright blue gradient ── */
.stButton > button {
    background: linear-gradient(135deg, #0288d1, #4fc3f7) !important;
    color: #ffffff !important;
    border: none !important;
    border-radius: 24px !important;
    font-family: 'DM Sans', sans-serif !important;
    font-weight: 500 !important;
    font-size: 0.88rem !important;
    letter-spacing: 0 !important;
    padding: 0.45rem 1.3rem !important;
    margin-bottom: 2rem !important;
    transition: opacity 0.2s ease !important;
    box-shadow: 0 2px 10px rgba(2,136,209,0.25) !important;
}
.stButton > button:hover {
    opacity: 0.88 !important;
    color: #ffffff !important;
}
/* Find Destinations button: full width */
.search-btn .stButton > button {
    width: 100% !important;
    border-radius: 8px !important;
    font-weight: 600 !important;
    margin-bottom: 0 !important;
}

div[data-baseweb="select"] > div,
div[data-baseweb="input"] > div {
    background: rgba(255,255,255,0.05) !important;
    border-color: rgba(79,195,247,0.2) !important;
    color: #e8f4f8 !important; border-radius: 8px !important;
}
</style>
""", unsafe_allow_html=True)

# ── Neo4j connection ──────────────────────────────────────────────────────────
@st.cache_resource
def get_driver():
    return GraphDatabase.driver(
        os.getenv("NEO4J_URI"),
        auth=(os.getenv("NEO4J_USER"), os.getenv("NEO4J_PASSWORD"))
    )

def run_query(query, params=None):
    driver = get_driver()
    with driver.session(database="socal") as session:
        result = session.run(query, params or {})
        return [dict(r) for r in result]

# ── Geocoding ─────────────────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def geocode_address(address: str):
    """
    Returns (lat, lng, display_name) or raises ValueError with a user-friendly message.
    Validates the result falls within the SoCal bounding box.
    """
    geolocator = Nominatim(user_agent="socal_trip_planner_kg")
    try:
        # Try the address as-is first, then with ", CA" appended as fallback
        location = geolocator.geocode(address, timeout=10)
        if location is None:
            location = geolocator.geocode(f"{address}, CA", timeout=10)
    except GeocoderTimedOut:
        raise ValueError("Geocoder timed out. Please try again.")
    except GeocoderServiceError as e:
        raise ValueError(f"Geocoder error: {e}")

    if location is None:
        raise ValueError("Address not found. Try adding a city or state, e.g. 'Palm Springs, CA'.")

    lat, lng = location.latitude, location.longitude

    if not (LAT_MIN <= lat <= LAT_MAX and LON_MIN <= lng <= LON_MAX):
        raise ValueError(
            f"'{address}' resolved outside Southern California "
            f"({lat:.2f}, {lng:.2f}). Please enter a SoCal address."
        )

    return lat, lng, location.address

# ── Core recommendation query ─────────────────────────────────────────────────
def get_recommendations(month, activities, origin_lat, origin_lng,
                         max_distance_miles, min_temp_f, crowd_levels, min_rating):
    min_temp_c = (min_temp_f - 32) * 5 / 9
    # Convert miles to meters for Neo4j point.distance()
    max_distance_m = max_distance_miles * 1609.34

    activity_list = activities if activities else [
        "Beach", "Hiking", "Park", "Nature", "Camping",
        "Attraction", "Cultural", "Recreation"
    ]

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
    OPTIONAL MATCH (l)-[:HAS_CROWD_LEVEL]->(proxy_c:CrowdLevel)

    WITH l, a, w,
         coalesce(nps_c.level, proxy_c.level)                             AS crowd_label,
         coalesce(nps_c.source, proxy_c.source)                           AS crowd_source,
         coalesce(nps_c.recreation_visitors, proxy_c.user_ratings_total)  AS crowd_signal,
         point.distance(
             point({latitude: l.lat, longitude: l.lng}),
             point({latitude: $origin_lat, longitude: $origin_lng})
         ) / 1609.34                                                       AS dist_miles

    WHERE crowd_label IN $crowd_levels

    WITH l,
         collect(DISTINCT a.name)                           AS activities,
         round((avg(w.temp_mean_c) * 9/5 + 32) * 10) / 10 AS avg_temp_f,
         crowd_label,
         crowd_source,
         avg(crowd_signal)                                  AS crowd_signal,
         min(dist_miles)                                    AS miles_from_origin

    RETURN l.name               AS name,
           l.address            AS address,
           l.city               AS city,
           l.lat                AS lat,
           l.lng                AS lng,
           l.google_rating      AS rating,
           l.yelp_stars         AS yelp_stars,
           activities,
           avg_temp_f,
           crowd_label,
           crowd_source,
           toInteger(crowd_signal) AS crowd_signal,
           round(miles_from_origin * 10) / 10 AS miles

    ORDER BY crowd_signal ASC, avg_temp_f DESC
    LIMIT 30
    """

    return run_query(query, {
        "month":          month,
        "activities":     activity_list,
        "min_temp_c":     min_temp_c,
        "origin_lat":     origin_lat,
        "origin_lng":     origin_lng,
        "max_distance_m": max_distance_m,
        "crowd_levels":   crowd_levels,
        "min_rating":     min_rating,
    })

def get_reviews(location_name, limit=1):
    query = """
    MATCH (l:Location {name: $name})-[:HAS_REVIEW_EVIDENCE]->(r:ReviewEvidence)
    WHERE r.text IS NOT NULL AND size(r.text) > 40
    RETURN r.text AS text, r.rating AS rating, r.platform AS platform
    ORDER BY r.rating DESC
    LIMIT $limit
    """
    return run_query(query, {"name": location_name, "limit": limit})

def get_all_reviews(location_name, limit=20):
    query = """
    MATCH (l:Location {name: $name})-[:HAS_REVIEW_EVIDENCE]->(r:ReviewEvidence)
    WHERE r.text IS NOT NULL AND size(r.text) > 20
    RETURN r.text AS text, r.rating AS rating, r.platform AS platform
    ORDER BY r.rating DESC
    LIMIT $limit
    """
    return run_query(query, {"name": location_name, "limit": limit})

def get_location_detail(location_name):
    query = """
    MATCH (l:Location {name: $name})
    OPTIONAL MATCH (l)-[:HAS_ACTIVITY]->(a:Activity)
    OPTIONAL MATCH (l)-[:HAS_COST_TIER]->(c:Cost)
    RETURN l.name AS name, l.address AS address, l.city AS city,
           l.google_rating AS rating, l.yelp_stars AS yelp_stars,
           l.distanceFromOrigin AS distance,
           collect(DISTINCT a.name) AS activities,
           c.label AS cost_label
    LIMIT 1
    """
    rows = run_query(query, {"name": location_name})
    return rows[0] if rows else None

def get_graph_stats():
    stats = {}
    stats["locations"] = run_query("MATCH (l:Location) RETURN count(l) AS n")[0]["n"]
    stats["reviews"]   = run_query("MATCH (r:ReviewEvidence) RETURN count(r) AS n")[0]["n"]
    stats["weather"]   = run_query("MATCH (w:WeatherCondition) RETURN count(w) AS n")[0]["n"]
    return stats

# ── Helpers ───────────────────────────────────────────────────────────────────
CROWD_BADGE = {
    "Low": "badge-crowd-low", "Moderate": "badge-crowd-mod",
    "High": "badge-crowd-high", "Very High": "badge-crowd-vhigh", "Unknown": "badge",
}
CROWD_EMOJI = {
    "Low": "🟢", "Moderate": "🟡", "High": "🟠", "Very High": "🔴", "Unknown": "⚪"
}
SOURCE_LABEL = {
    "nps_official":   "NPS Official Data",
    "google_ratings": "Review Volume Proxy",
}
MONTHS = [
    "January","February","March","April","May","June",
    "July","August","September","October","November","December"
]
ACTIVITY_OPTIONS = [
    "Beach","Hiking","Park","Nature","Camping","Attraction","Cultural","Recreation"
]

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 🌴 Trip Filters")
    st.markdown("---")

    month = st.selectbox("Month", MONTHS, index=2)

    activities = st.multiselect(
        "Activity Type",
        ACTIVITY_OPTIONS,
        default=["Hiking", "Beach", "Park"],
        help="Leave empty to include all activity types"
    )

    st.markdown("**Origin Address**")
    address_input = st.text_input(
        "Origin Address",
        value="Los Angeles, CA",
        label_visibility="collapsed",
        placeholder="e.g. 123 Main St, San Diego, CA",
        help="Enter any SoCal address as your trip starting point"
    )

    # Geocode and validate on input change
    origin_lat, origin_lng, origin_display = 34.0522, -118.2437, "Los Angeles, CA"
    geo_error = None

    if address_input.strip():
        try:
            origin_lat, origin_lng, origin_display = geocode_address(address_input.strip())
            st.markdown(
                f"<div class='addr-ok'>📍 {origin_display[:60]}{'…' if len(origin_display)>60 else ''}"
                f"<br><span style='opacity:0.7'>({origin_lat:.4f}, {origin_lng:.4f})</span></div>",
                unsafe_allow_html=True
            )
        except ValueError as e:
            geo_error = str(e)
            st.markdown(f"<div class='addr-err'>⚠️ {geo_error}</div>", unsafe_allow_html=True)

    max_distance = st.slider(
        "Max Distance from Origin (miles)",
        min_value=10, max_value=200, value=100, step=5
    )

    temp_preference = st.radio(
        "Weather Preference",
        ["Any", "Mild (55°F+)", "Warm (65°F+)", "Hot (75°F+)"],
        index=1,
        horizontal=True,
        help="Filters destinations by historical average temperature for your selected month"
    )
    temp_map = {"Any": 0, "Mild (55°F+)": 55, "Warm (65°F+)": 65, "Hot (75°F+)": 75}
    min_temp_f = temp_map[temp_preference]

    crowd_levels = st.multiselect(
        "Acceptable Crowd Level",
        ["Low", "Moderate", "High", "Very High"],
        default=["Low", "Moderate", "High"],
        help="Low = quiet/obscure  ·  Very High = major NPS parks at peak"
    )

    min_rating = st.slider(
        "Min Google Rating",
        min_value=1.0, max_value=5.0, value=4.0, step=0.1
    )

    st.markdown("---")
    st.markdown('<div class="search-btn">', unsafe_allow_html=True)
    search = st.button("🔍 Find Destinations", use_container_width=True, disabled=bool(geo_error))
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown("""
    <div style='margin-top:1.5rem; color:#4a7a94; font-size:0.72rem; line-height:1.7;'>
        <strong style='color:#7fa8bf;'>Data Sources</strong><br>
        📍 Google Places + Yelp<br>
        🌤 Open-Meteo Historical API<br>
        🏕 NPS Visitor Statistics<br><br>
        <em>Crowd data reflects historical monthly averages, not real-time conditions.</em>
    </div>
    """, unsafe_allow_html=True)

# ── Main content ──────────────────────────────────────────────────────────────
st.markdown("""
<div style='padding: 2rem 0 1rem 0;'>
    <div class='hero-title'>SoCal <span>Trip Planner</span></div>
    <div class='hero-subtitle'>
        Constraint-aware destination search powered by a knowledge graph —
        weather, crowds, distance, and activity all reasoned together.
    </div>
</div>
""", unsafe_allow_html=True)

try:
    stats = get_graph_stats()
    st.markdown(f"""
    <div class='metric-row'>
        <div class='metric-box'>
            <div class='metric-value'>{stats['locations']:,}</div>
            <div class='metric-label'>Locations</div>
        </div>
        <div class='metric-box'>
            <div class='metric-value'>{stats['reviews']:,}</div>
            <div class='metric-label'>Reviews</div>
        </div>
        <div class='metric-box'>
            <div class='metric-value'>{stats['weather']:,}</div>
            <div class='metric-label'>Weather Records</div>
        </div>
        <div class='metric-box'>
            <div class='metric-value'>4</div>
            <div class='metric-label'>NPS Parks</div>
        </div>
    </div>
    """, unsafe_allow_html=True)
except Exception:
    pass

# ── Results ───────────────────────────────────────────────────────────────────
if search:
    if not crowd_levels:
        st.warning("Please select at least one crowd level.")
    else:
        with st.spinner("Querying knowledge graph..."):
            results = get_recommendations(
                month=month,
                activities=activities,
                origin_lat=origin_lat,
                origin_lng=origin_lng,
                max_distance_miles=max_distance,
                min_temp_f=min_temp_f,
                crowd_levels=crowd_levels,
                min_rating=min_rating,
            )
        st.session_state["results"] = results
        st.session_state["selected"] = None

# ── Detail view ───────────────────────────────────────────────────────────────
if st.session_state.get("selected"):
    selected_name = st.session_state["selected"]

    if st.button("← Back to results"):
        st.session_state["selected"] = None
        st.rerun()

    detail = get_location_detail(selected_name)
    all_reviews = get_all_reviews(selected_name, limit=20)

    st.markdown(f"""
    <div style='margin: 1rem 0 0.5rem 0;'>
        <div class='hero-title' style='font-size:2rem;'>{html.escape(selected_name)}</div>
        <div style='color:#7fa8bf; font-size:0.9rem; margin-top:0.3rem;'>
            {html.escape(detail.get("address") or detail.get("city") or "")}
        </div>
    </div>
    """, unsafe_allow_html=True)

    # stat row
    acts_str = " &nbsp;·&nbsp; ".join(detail.get("activities") or [])
    rating   = detail.get("rating") or detail.get("yelp_stars")
    cost     = detail.get("cost_label") or "Free"
    st.markdown(f"""
    <div style='background:rgba(79,195,247,0.07); border:1px solid rgba(79,195,247,0.15);
                border-radius:10px; padding:0.9rem 1.2rem; margin-bottom:1.5rem;
                color:#7fa8bf; font-size:0.88rem; line-height:2;'>
        &#127919; <strong style='color:#c8e6f5;'>{acts_str or "—"}</strong> &nbsp;&nbsp;
        &#11088; <strong style='color:#c8e6f5;'>{rating or "—"}</strong> &nbsp;&nbsp;
        &#128181; <strong style='color:#c8e6f5;'>{cost}</strong>
    </div>
    """, unsafe_allow_html=True)

    if not all_reviews:
        st.markdown("<div class='empty-state'><div class='icon'>📭</div><p>No reviews available for this location.</p></div>",
                    unsafe_allow_html=True)
    else:
        st.markdown(f"<div class='section-label'>— {len(all_reviews)} Reviews —</div>",
                    unsafe_allow_html=True)
        for rev in all_reviews:
            text     = html.escape(rev["text"] or "")
            rating_r = rev.get("rating")
            platform = html.escape(rev.get("platform") or "")
            stars    = "⭐" * int(rating_r) if rating_r else ""
            st.markdown(f"""
            <div style='background:rgba(255,255,255,0.04); border:1px solid rgba(79,195,247,0.1);
                        border-radius:10px; padding:1rem 1.2rem; margin-bottom:0.75rem;'>
                <div style='display:flex; justify-content:space-between;
                            margin-bottom:0.5rem; align-items:center;'>
                    <span style='color:#4fc3f7; font-size:0.75rem; font-weight:600;
                                 text-transform:uppercase; letter-spacing:0.06em;'>
                        {platform}
                    </span>
                    <span style='font-size:0.8rem;'>{stars}</span>
                </div>
                <div style='color:#c8e6f5; font-size:0.88rem; line-height:1.65;
                            font-style:italic;'>&ldquo;{text}&rdquo;</div>
            </div>
            """, unsafe_allow_html=True)

# ── Results list view ─────────────────────────────────────────────────────────
elif "results" in st.session_state:
    results = st.session_state["results"]

    if not results:
        st.markdown("""
        <div class='empty-state'>
            <div class='icon'>🏜️</div>
            <p>No destinations matched your constraints.<br>
            Try relaxing the temperature, distance, or crowd filters.</p>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown(
            f"<div class='section-label'>— {len(results)} destinations found for {month} "
            f"within {max_distance} miles of {html.escape(address_input)} —</div>",
            unsafe_allow_html=True
        )

        col1, col2 = st.columns([3, 2])

        with col1:
            for i, r in enumerate(results):
                name         = r["name"]
                name_escaped = html.escape(name)
                miles        = r["miles"]
                temp_f       = r["avg_temp_f"]
                crowd        = r["crowd_label"] or "Unknown"
                crowd_src    = html.escape(SOURCE_LABEL.get(r.get("crowd_source", ""), ""))
                rating       = r["rating"] or r.get("yelp_stars")
                acts         = r["activities"]
                crowd_signal = r["crowd_signal"]

                act_badges  = "".join(f"<span class='badge'>{html.escape(a)}</span>" for a in acts)
                crowd_badge = (f"<span class='badge {CROWD_BADGE.get(crowd, 'badge')}'>"
                               f"{CROWD_EMOJI.get(crowd, '')} {html.escape(crowd)}</span>")
                rating_str  = f"&#11088; {rating}" if rating else ""
                crowd_detail = (f"{crowd_signal:,} visitors/mo"
                                if r.get("crowd_source") == "nps_official" and crowd_signal
                                else "")
                crowd_detail_html = (
                    f"&nbsp;&middot;&nbsp;<em style='color:#4a7a94;font-size:0.75rem;'>"
                    f"{crowd_detail}</em>" if crowd_detail else ""
                )

                reviews = get_reviews(name, limit=1)
                review_html = ""
                if reviews:
                    snippet = html.escape(reviews[0]["text"][:160].rstrip()) + "&hellip;"
                    review_html = f"<div class='review-box'>&ldquo;{snippet}&rdquo;</div>"

                reviews = get_reviews(name, limit=1)
                review_html = ""
                if reviews:
                    snippet = html.escape(reviews[0]["text"][:160].rstrip()) + "&hellip;"
                    review_html = f"<div class='review-box'>&ldquo;{snippet}&rdquo;</div>"

                st.markdown(f"""
                <div class='result-card'>
                    <div class='card-name'>{name_escaped}</div>
                    <div class='card-meta'>{act_badges} {crowd_badge}</div>
                    <div class='card-stat'>
                        <strong>{temp_f}&deg;F</strong> avg &nbsp;&middot;&nbsp;
                        <strong>{miles} mi</strong> from origin &nbsp;&middot;&nbsp;
                        {rating_str}{crowd_detail_html}
                    </div>
                    <div style='color:#4a7a94;font-size:0.7rem;margin-top:0.25rem;'>
                        Crowd source: {crowd_src}
                    </div>
                    {review_html}
                </div>
                """, unsafe_allow_html=True)

                if st.button("Read all reviews →", key=f"btn_{i}"):
                    st.session_state["selected"] = name
                    st.rerun()

        with col2:
            st.markdown("<div class='section-label'>— Query Summary —</div>",
                        unsafe_allow_html=True)
            st.markdown(f"""
            <div style='background:rgba(255,255,255,0.04); border-radius:10px;
                        padding:1rem 1.2rem; border:1px solid rgba(79,195,247,0.1);
                        color:#7fa8bf; font-size:0.85rem; line-height:2;'>
                &#128197; <strong style='color:#c8e6f5;'>{month}</strong><br>
                &#127919; <strong style='color:#c8e6f5;'>{", ".join(activities) if activities else "All types"}</strong><br>
                &#128205; Within <strong style='color:#c8e6f5;'>{max_distance} mi</strong>
                          of <strong style='color:#c8e6f5;'>{html.escape(address_input)}</strong><br>
                &#127777; <strong style='color:#c8e6f5;'>{temp_preference}</strong><br>
                &#128101; <strong style='color:#c8e6f5;'>{", ".join(crowd_levels)}</strong> crowds<br>
                &#11088; Rated <strong style='color:#c8e6f5;'>{min_rating}+</strong>
            </div>
            """, unsafe_allow_html=True)

            st.markdown("<div class='section-label' style='margin-top:1.2rem;'>— Crowd Breakdown —</div>",
                        unsafe_allow_html=True)
            crowd_counts = {}
            for r in results:
                cl = r["crowd_label"] or "Unknown"
                crowd_counts[cl] = crowd_counts.get(cl, 0) + 1

            for level, count in sorted(crowd_counts.items()):
                pct = int(count / len(results) * 100)
                st.markdown(f"""
                <div style='margin-bottom:0.5rem;'>
                    <div style='display:flex; justify-content:space-between;
                                color:#7fa8bf; font-size:0.78rem; margin-bottom:0.2rem;'>
                        <span>{CROWD_EMOJI.get(level,'')} {level}</span>
                        <span>{count}</span>
                    </div>
                    <div style='background:rgba(255,255,255,0.06); border-radius:4px; height:6px;'>
                        <div style='background:#4fc3f7; width:{pct}%; height:6px; border-radius:4px;'></div>
                    </div>
                </div>
                """, unsafe_allow_html=True)

            st.markdown("<div class='section-label' style='margin-top:1.2rem;'>— Activity Mix —</div>",
                        unsafe_allow_html=True)
            act_counts = {}
            for r in results:
                for a in r["activities"]:
                    act_counts[a] = act_counts.get(a, 0) + 1

            for act, count in sorted(act_counts.items(), key=lambda x: -x[1]):
                st.markdown(
                    f"<span class='badge' style='margin-right:0.3rem;margin-bottom:0.3rem;"
                    f"display:inline-block;'>{act} ({count})</span>",
                    unsafe_allow_html=True
                )

else:
    st.markdown("""
    <div class='empty-state'>
        <div class='icon'>🌴</div>
        <p>Set your filters in the sidebar and hit <strong>Find Destinations</strong>.</p>
    </div>
    """, unsafe_allow_html=True)