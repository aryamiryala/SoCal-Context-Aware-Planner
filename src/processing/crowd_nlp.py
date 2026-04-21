# src/processing/crowd_nlp.py
import os
import re
from typing import Optional, Tuple, List

from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv()

DB_NAME = "socal"

driver = GraphDatabase.driver(
    os.getenv("NEO4J_URI"),
    auth=(os.getenv("NEO4J_USER"), os.getenv("NEO4J_PASSWORD")),
)

# ------------------------------- Keyword rules ----------------------------------------------

VERY_HIGH_PATTERNS = [
    r"\bovercrowded\b",
    r"\bextremely crowded\b",
    r"\bsuper crowded\b",
    r"\binsanely busy\b",
    r"\bpacked\b",
    r"\bmobbed\b",
    r"\bshoulder to shoulder\b",
    r"\bwall to wall people\b",
    r"\bno room\b",
    r"\bimpossible to park\b",
    r"\bparking was impossible\b",
    r"\bhuge lines\b",
    r"\breally long lines\b",
    r"\bvery long lines\b",
]

HIGH_PATTERNS = [
    r"\bcrowded\b",
    r"\bvery busy\b",
    r"\breally busy\b",
    r"\bbusy\b",
    r"\blots of people\b",
    r"\bso many people\b",
    r"\btons of people\b",
    r"\blong line\b",
    r"\blong lines\b",
    r"\blong wait\b",
    r"\bhard to park\b",
    r"\bhard to find parking\b",
    r"\bparking was hard\b",
    r"\bfull parking lot\b",
]

MODERATE_PATTERNS = [
    r"\bsomewhat busy\b",
    r"\ba bit busy\b",
    r"\bmoderately busy\b",
    r"\ba little crowded\b",
    r"\ba bit crowded\b",
    r"\bmoderately crowded\b",
    r"\bnot too crowded\b",
    r"\bnot overly crowded\b",
    r"\bmanageable crowd\b",
    r"\bdecent crowd\b",
    r"\bkind of busy\b"
    r"\bkind of crowded\b"
    r"\bslightly crowded\b"
    r"\bnot that crowded\b"
    r"\bmanageable\b"
]

LOW_PATTERNS = [
    r"\bnot crowded\b",
    r"\bwasn't crowded\b",
    r"\bwas not crowded\b",
    r"\bnot busy\b",
    r"\bwasn't busy\b",
    r"\bwas not busy\b",
    r"\buncrowded\b",
    r"\bempty\b",
    r"\bquiet\b",
    r"\bpeaceful\b",
    r"\bplenty of space\b",
    r"\beasy parking\b",
    r"\bno line\b",
    r"\bno lines\b",
    r"\bno wait\b",
]

# Extra negation-safe phrases to check before generic "busy"/"crowded"
NEGATED_LOW_PRIORITY = [
    r"\bnot crowded\b",
    r"\bnot busy\b",
    r"\bwasn't crowded\b",
    r"\bwasn't busy\b",
    r"\bwas not crowded\b",
    r"\bwas not busy\b",
    r"\bnot too crowded\b",
    r"\bnot overly crowded\b",
]

# -------------------------------- Text classification ---------------------------------------------


def normalize_text(text: str) -> str:
    text = text.lower()
    text = text.replace("’", "'")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def first_match(text: str, patterns: List[str]) -> Optional[str]:
    for pattern in patterns:
        if re.search(pattern, text):
            return pattern
    return None


def classify_crowding(text: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Returns:
        (crowd_level, matched_pattern)
    crowd_level is one of:
        "Low", "Moderate", "High", "Very High", or None
    """
    if not text or not text.strip():
        return None, None

    t = normalize_text(text)

    # 1) Negated low phrases first so "not crowded" doesn't get caught as "crowded"
    pat = first_match(t, NEGATED_LOW_PRIORITY)
    if pat:
        return "Low", pat

    # 2) Strongest evidence next
    pat = first_match(t, VERY_HIGH_PATTERNS)
    if pat:
        return "Very High", pat

    # MODERATE FIRST (more specific phrases)
    pat = first_match(t, MODERATE_PATTERNS)
    if pat:
        return "Moderate", pat

    # HIGH AFTER (more generic phrases)
    pat = first_match(t, HIGH_PATTERNS)
    if pat:
        return "High", pat

    pat = first_match(t, LOW_PATTERNS)
    if pat:
        return "Low", pat

    return None, None

# --------------------------------- Neo4j helpers --------------------------------------------


def run_read_query(query: str, params: Optional[dict] = None):
    with driver.session(database=DB_NAME) as session:
        result = session.run(query, params or {})
        return [dict(r) for r in result]


def run_write_query(query: str, params: Optional[dict] = None):
    with driver.session(database=DB_NAME) as session:
        session.run(query, params or {})


def ensure_nlp_crowdlevel_nodes():
    """
    Create one canonical CrowdLevel node per NLP crowd label.
    This fits your existing schema where CrowdLevel has unique crowd_id. :contentReference[oaicite:3]{index=3}
    """
    levels = ["Low", "Moderate", "High", "Very High"]
    for level in levels:
        crowd_id = f"nlp_{level.lower().replace(' ', '_')}"
        run_write_query(
            """
            MERGE (cl:CrowdLevel {crowd_id: $crowd_id})
              SET cl.level = $level,
                  cl.source = 'review_nlp'
            """,
            {"crowd_id": crowd_id, "level": level},
        )


def fetch_reviews():
    return run_read_query(
        """
        MATCH (r:ReviewEvidence)
        WHERE r.text IS NOT NULL AND size(trim(r.text)) > 0
        RETURN r.review_id AS review_id,
               r.text AS text,
               r.platform AS platform,
               r.rating AS rating
        """
    )


def clear_existing_nlp_edges():
    run_write_query(
        """
        MATCH (:ReviewEvidence)-[rel:INDICATES_CROWDING]->(cl:CrowdLevel)
        WHERE cl.source = 'review_nlp'
        DELETE rel
        """
    )


def write_nlp_edge(review_id: str, level: str, matched_pattern: str):
    crowd_id = f"nlp_{level.lower().replace(' ', '_')}"
    run_write_query(
        """
        MATCH (r:ReviewEvidence {review_id: $review_id})
        MATCH (cl:CrowdLevel {crowd_id: $crowd_id})
        MERGE (r)-[rel:INDICATES_CROWDING]->(cl)
          SET rel.method = 'keyword_rules',
              rel.matched_pattern = $matched_pattern
        """,
        {
            "review_id": review_id,
            "crowd_id": crowd_id,
            "matched_pattern": matched_pattern,
        },
    )

# ---------------------------------- Main -------------------------------------------

def run():
    print("=== Running crowd NLP pipeline ===")

    ensure_nlp_crowdlevel_nodes()
    clear_existing_nlp_edges()

    reviews = fetch_reviews()
    print(f"Fetched {len(reviews)} reviews")

    labeled = 0
    counts = {"Low": 0, "Moderate": 0, "High": 0, "Very High": 0}

    for i, review in enumerate(reviews, start=1):
        level, matched_pattern = classify_crowding(review["text"])
        if level is None:
            continue

        write_nlp_edge(
            review_id=review["review_id"],
            level=level,
            matched_pattern=matched_pattern or "",
        )
        labeled += 1
        counts[level] += 1

        if i % 1000 == 0:
            print(f"Processed {i}/{len(reviews)} reviews...")

    print("\n=== Crowd NLP complete ===")
    print(f"Labeled reviews: {labeled}")
    for level in ["Low", "Moderate", "High", "Very High"]:
        print(f"  {level}: {counts[level]}")

    driver.close()


if __name__ == "__main__":
    run()