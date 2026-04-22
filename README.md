# SoCal Context-Aware Trip Planner

>Built by Arya Miryala & Saavani Vaidya

A constraint-aware destination recommender for Southern California, powered by a Neo4j knowledge graph. Unlike generic AI itinerary generators, this system reasons across weather, crowd levels, activity type, distance, and ratings simultaneously to surface realistic, explainable recommendations.

---

## Project Overview

Most travel planners produce generic results that ignore real-world constraints — a chatbot might suggest hiking in the rain or visiting a beach in winter. This system addresses that gap by encoding contextual relationships in a knowledge graph, enabling multi-hop queries like:

> *"Find hiking destinations within 50 miles of San Diego in April that are historically not crowded and have an average temperature above 60°F."*

The answer is not stored explicitly — it is **derived through multi-step reasoning** across linked semantic types.

---

## Architecture

### Ontology — 11 Semantic Types, 17 Edge Types

| Subject | Predicate | Object | Source |
|---|---|---|---|
| Location | HAS_ACTIVITY | Activity | Google Places / Yelp |
| Location | HAS_COST_TIER | Cost | Google Places |
| Location | EXPERIENCES_WEATHER | WeatherCondition | Open-Meteo API |
| Location | HAS_HISTORICAL_CROWDS | CrowdLevel | NPS Visitor Stats |
| Location | HAS_CROWD_LEVEL | CrowdLevel | Google Ratings Proxy |
| Location | HAS_REVIEW_EVIDENCE | ReviewEvidence | Google / Yelp Reviews |
| WeatherCondition | OCCURS_IN_MONTH | Month | Open-Meteo API |
| WeatherCondition | TYPICAL_IN_SEASON | Season | Derived |
| CrowdLevel | RECORDED_IN_MONTH | Month | NPS Stats |
| Month | BELONGS_TO_SEASON | Season | System Logic |
| Activity | FEASIBLE_IN_SEASON | Season | System Logic |
| ReviewEvidence | INDICATES_CROWDING | CrowdLevel | NLP Pipeline |
| TravelPreference | MATCHES_ACTIVITY | Activity | User Input |
| UserQuery | HAS_PREFERENCE | TravelPreference | Streamlit GUI |
| UserQuery | MAX_DISTANCE_LIMIT | Literal | Streamlit GUI |
| UserQuery | HAS_TARGET_MONTH | Month | Streamlit GUI |

### Tech Stack

| Layer | Technology |
|---|---|
| Graph Database | Neo4j (Aura or local) |
| Graph Query | Cypher |
| Ontology Serialization | rdflib (Python) |
| Data Ingestion | Python + pandas |
| Geocoding | geopy + Nominatim (OpenStreetMap) |
| GUI | Streamlit |
| Distance Computation | Haversine formula + Neo4j `point.distance()` |

---

## Data Sources

| Source | What It Provides | Coverage |
|---|---|---|
| **Google Places API** | Location names, types, ratings, reviews, coordinates | ~1,400 SoCal locations |
| **Yelp Open Dataset** | Historical reviews and check-ins | Santa Barbara area |
| **Open-Meteo Historical API** | Monthly avg temp, precipitation, wind speed | All locations (by lat/lng) |
| **NPS Visitor Use Statistics** | Official monthly visitor headcounts | Joshua Tree, Channel Islands, Santa Monica Mtns, Cabrillo |

### SoCal Bounding Box

```python
LAT_MIN, LAT_MAX = 32.5, 35.0
LON_MIN, LON_MAX = -120.5, -114.0
```

### Entity Resolution Data

The processed and entity-resolved location data (`merged_locations.json`, `google_only_locations.json`, `yelp_only_locations.json`, `weather_by_location.json`, `nps_visitation.json`) is stored in the GitHub repository under:

```
data/processed/entity_resolution/
```

Clone the repo to access this data — it is not regenerated at runtime.

---

## Project Structure

```
SoCal-Context-Aware-Planner/
├── src/
│   ├── app.py                          # Streamlit GUI
│   ├── graph/
│   │   └── load_graph.py               # Loads data into Neo4j KG
│   ├── ingestion/
│   │   ├── google_places.py            # Google Places ingestion
│   │   ├── yelp_ingest.py              # Yelp business ingestion
│   │   ├── yelp_reviews_ingest.py      # Yelp review ingestion
│   │   ├── yelp_checkin_ingest.py      # Yelp check-in data
│   │   ├── open_meteo.py               # Weather data ingestion
│   │   └── nps_stats.py                # NPS crowd data ingestion
│   ├── processing/
│   │   ├── entity_resolution.py        # Merge Google + Yelp locations
│   │   ├── clean_google_places.py      # Data cleaning
│   │   └── crowd_nlp.py                # NLP crowd detection from reviews
│
├── data/
│   ├── raw/                            # Raw API responses (gitignored)
│   └── processed/
│       └── entity_resolution/          # Resolved & merged location data
│           ├── merged_locations.json
│           ├── google_only_locations.json
│           ├── yelp_only_locations.json
│           ├── weather_by_location.json
│           └── nps_visitation.json
│
├── requirements.txt
├── .env                                # Neo4j credentials
└── README.md
```

---

## Local Setup

### 1. Clone the Repository

```bash
git clone https://github.com/<your-repo>/SoCal-Context-Aware-Planner.git
cd SoCal-Context-Aware-Planner
```

### 2. Create and Activate a Virtual Environment

```bash
python -m venv venv
source venv/bin/activate        # Mac/Linux
venv\Scripts\activate           # Windows
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Set Up Neo4j

You can use either **Neo4j Aura** (free cloud instance) or a **local Neo4j Desktop** installation.

- Create a database named `socal`
- Note your connection URI, username, and password

### 5. Configure Environment Variables

Create a `.env` file in the project root:

```
NEO4J_URI=neo4j+s://your-instance.databases.neo4j.io
NEO4J_USER=neo4j
NEO4J_PASSWORD=your-password
```

For a local Neo4j instance:

```
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your-password
```

### 6. Load the Knowledge Graph

Run from the **project root** (not from inside `src/`):

```bash
python src/graph/load_graph.py
```

This will:
- Create constraints and indexes
- Load Month and Season nodes (12 months → 4 seasons)
- Load Cost tier nodes
- Load all Activity nodes with season feasibility edges
- Load ~1,408 Location nodes with `distanceFromOrigin` from LA
- Load ReviewEvidence nodes from Google and Yelp reviews
- Load WeatherCondition nodes from Open-Meteo data
- Load NPS CrowdLevel nodes for national parks

Expected output:
```
=== Loading SoCal KG into Neo4j ===
Creating constraints... Done.
Loading Month and Season nodes... Done.
Loading Cost nodes... Done.
Loading Activity nodes... Loaded 8 activity types.
Loading Location nodes... Done. 1408 locations loaded.
Loading ReviewEvidence nodes... Done. 11245 reviews loaded.
Loading WeatherCondition nodes... Done. 16884 weather records loaded.
Loading NPS CrowdLevel nodes... Done. X NPS records loaded.
=== Done! KG loaded successfully ===
```

### 7. Run the Crowd NLP Pipeline

```bash
python src/processing/crowd_nlp.py
```

This step enriches the knowledge graph by extracting crowd signals directly from review text.

It will:
- Process ReviewEvidence nodes stored in Neo4j
- Apply a keyword-based NLP classifier to detect crowd-related language
- Assign crowd levels: Low, Moderate, High, Very High
- Create new graph relationships:
- (ReviewEvidence)-[:INDICATES_CROWDING]->(CrowdLevel)

Expected output:
```
=== Running crowd NLP pipeline ===
Fetched XXXXX reviews
Processed XXXXX/XXXXX reviews...
=== Crowd NLP complete ===
Labeled reviews: XXXX
Low: XXXX
Moderate: XXXX
High: XXXX
Very High: XXXX
```
Note: This step must be run after loading the knowledge graph, since it operates on ReviewEvidence nodes already stored in Neo4j.

### 8. Run the Streamlit App

```bash
streamlit run src/app.py
```

Open your browser to `http://localhost:8501`.

---

## Using the App

1. **Select a Month** — filters destinations by historical weather for that month
2. **Choose Activity Types** — Beach, Hiking, Park, Nature, Camping, Attraction, Cultural, Recreation
3. **Enter an Origin Address** — any SoCal address; geocoded via OpenStreetMap. Must fall within the SoCal bounding box
4. **Set Max Distance** — radius in miles from your origin
5. **Weather Preference** — Any / Mild (55°F+) / Warm (65°F+) / Hot (75°F+)
6. **Crowd Tolerance** — Low, Moderate, High, Very High
7. **Min Rating** — filters by Google star rating
8. **Click Find Destinations** — runs the multi-hop Cypher query
9. **Click "Read all reviews →"** on any card to see all available reviews for that location
10. **Click "← Back to results"** to return to the results list

---

## Graph Stats (as loaded)

| Metric | Count |
|---|---|
| Location nodes | 1,408 |
| ReviewEvidence nodes | ~11,245 |
| WeatherCondition nodes | ~16,884 |
| NPS parks with official crowd data | 4 |
| Activity types | 8 |
| Months | 12 |
| Seasons | 4 |

---

## Activity Classification

Activities are assigned via two mechanisms:

**Google Places type taxonomy:**

| Google Type | Activity Node |
|---|---|
| `park` | Park |
| `campground`, `rv_park` | Camping |
| `natural_feature` | Nature |
| `tourist_attraction`, `travel_agency` | Attraction |
| `hiking_area` | Hiking |
| `beach` | Beach |
| `museum`, `aquarium`, `zoo` | Cultural |
| `stadium`, `amusement_park` | Recreation |

**Name-based keyword enrichment** (catches Yelp locations without Google types):

| Keywords in Name | Activity |
|---|---|
| beach, shore, coast, surf | Beach |
| trail, trailhead, hike, canyon, mountain, forest, peak, summit | Hiking |
| park, preserve, reserve, nature | Nature |
| adventure, kayak, paddle, dive, boat | Recreation |
| museum, courthouse, carousel, castle, historic | Cultural |

---

## Crowd Data — Important Caveat

The app uses **three crowd signals** with different reliability:

| Signal | Edge | Source | What It Means |
|---|---|---|---|
| **NPS Official** | `HAS_HISTORICAL_CROWDS` | NPS Visitor Use Statistics | Actual monthly headcount — trustworthy |
| **Review NLP Signal** | `INDICATES_CROWDING `| Yelp Reviews | Direct textual evidence of crowd perception from user reviews (keyword matching) |
| **Review Volume Proxy** | `HAS_CROWD_LEVEL` | Google `user_ratings_total` | Number of reviews, not visitors — a popularity proxy |

Review volume is a weak proxy: a location with few reviews is labeled "Low" crowd, but that means it's obscure, not necessarily quiet. To address this limitation, we incorporate an NLP-based crowd signal extracted directly from review text. This provides more granular and interpretable evidence of crowd conditions (e.g., "packed", "quiet", "manageable"). The GUI labels the source on every result card so users understand which signal is being shown.

**No real-time crowd data is used.** All crowd information reflects historical monthly averages.

---

## Known Limitations

- **Duplicate location nodes** — some locations (e.g. Santa Monica State Beach) appear multiple times across Google and Yelp source files with different IDs. MERGE-based deduplication by name+coordinates is a planned improvement.
- **Cost data sparse** — Google Places `price_level` is rarely returned for outdoor locations; nearly all locations default to "Free." Cost filtering is not exposed in the GUI.
- **Beach and Hiking coverage** — Google Places does not reliably tag locations with `beach` or `hiking_area` types. These activity edges are primarily assigned via name-based keyword matching.
- **NPS coverage limited to 4 parks** — Joshua Tree, Channel Islands, Santa Monica Mountains NRA, and Cabrillo National Monument.
- **37 unclassifiable locations** — Yelp-sourced locations whose names contain no recognizable activity keywords and have no Google type tags.

---

## Requirements


Can be found in `requirements.txt`.

---

## Evaluation Plan

Per the project proposal, system correctness is measured across three areas:

1. **Entity Resolution Accuracy** — random sample of 50 Location nodes manually verified for correct cross-source mapping (Yelp ↔ Google ↔ NPS)
2. **NLP Pipeline Precision/Recall** — 100 manually annotated reviews tested for constraint extraction (e.g. "overcrowded", "closed", "seasonal")
3. **Constraint Satisfaction Rate** — 20 randomly generated multi-hop queries verified that all returned destinations satisfy the temporal, weather, and activity constraints simultaneously
