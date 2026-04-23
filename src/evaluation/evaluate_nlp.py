import csv
import os
import random
import sys
from pathlib import Path

from dotenv import load_dotenv
from neo4j import GraphDatabase
from sklearn.metrics import classification_report, confusion_matrix

# ---------------------------- Paths / imports ------------------------------------------

ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(ROOT))

from src.processing.crowd_nlp import classify_crowding  # uses your real model

load_dotenv()

DB_NAME = "socal"
SAMPLE_SIZE = 100
OUTPUT_CSV = ROOT / "src" / "evaluation" / "nlp_gold_labels.csv"

ALLOWED_LABELS = ["Low", "Moderate", "High", "Very High", "None"]


# ---------------------------- Neo4j connection -----------------------------------------


def get_driver():
    return GraphDatabase.driver(
        os.getenv("NEO4J_URI"),
        auth=(os.getenv("NEO4J_USER"), os.getenv("NEO4J_PASSWORD")),
    )


def fetch_random_reviews(sample_size=SAMPLE_SIZE):
    """
    Pull a random sample of ReviewEvidence nodes from Neo4j.
    """
    query = """
    MATCH (r:ReviewEvidence)
    WHERE r.text IS NOT NULL AND size(trim(r.text)) > 20
    RETURN r.review_id AS review_id,
           r.text AS text,
           r.platform AS platform,
           r.rating AS rating
    ORDER BY rand()
    LIMIT $limit
    """

    driver = get_driver()
    with driver.session(database=DB_NAME) as session:
        rows = [dict(r) for r in session.run(query, {"limit": sample_size})]
    driver.close()
    return rows


# -------------------------- Step 1: create annotation CSV -------------------------------------------

def create_annotation_file():
    if OUTPUT_CSV.exists():
        print(f"{OUTPUT_CSV} already exists.")
        print("To avoid overwriting your manual labels, delete or rename it first if you want a new sample.")
        return

    rows = fetch_random_reviews(SAMPLE_SIZE)
    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["review_id", "platform", "rating", "text", "true_label"]
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({
                "review_id": row.get("review_id", ""),
                "platform": row.get("platform", ""),
                "rating": row.get("rating", ""),
                "text": row.get("text", ""),
                "true_label": "",   
            })

    print(f"Created annotation file: {OUTPUT_CSV}")
    print("\nNext step:")
    print("Open the CSV and fill in true_label for each row using one of:")
    print(ALLOWED_LABELS)


# ----------------------- Step 2: evaluate labeled CSV ----------------------------------------------

def normalize_true_label(label: str) -> str:
    if label is None:
        return "None"

    label = label.strip()
    if label == "":
        return ""

    # allow light variations
    lowered = label.lower()
    mapping = {
        "low": "Low",
        "moderate": "Moderate",
        "high": "High",
        "very high": "Very High",
        "very_high": "Very High",
        "none": "None",
        "no signal": "None",
        "no crowd signal": "None",
        "null": "None",
    }
    return mapping.get(lowered, label)


def evaluate_annotations():
    if not OUTPUT_CSV.exists():
        print(f"File not found: {OUTPUT_CSV}")
        print("Run sampling mode first to create the annotation CSV.")
        return

    y_true = []
    y_pred = []
    skipped = 0

    with open(OUTPUT_CSV, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    for row in rows:
        true_label = normalize_true_label(row.get("true_label", ""))
        text = row.get("text", "")

        if true_label == "":
            skipped += 1
            continue

        if true_label not in ALLOWED_LABELS:
            print(f"Invalid true_label '{true_label}' for review_id={row.get('review_id')}. Skipping.")
            skipped += 1
            continue

        pred_label, _ = classify_crowding(text)
        pred_label = pred_label if pred_label is not None else "None"

        y_true.append(true_label)
        y_pred.append(pred_label)

    if not y_true:
        print("No labeled rows found.")
        print("Fill in the true_label column first.")
        return

    print("\n=== NLP Evaluation ===")
    print(f"Total labeled rows used: {len(y_true)}")
    print(f"Skipped unlabeled/invalid rows: {skipped}\n")

    print("Allowed labels:")
    print(ALLOWED_LABELS)
    print()

    report = classification_report(
        y_true,
        y_pred,
        labels=ALLOWED_LABELS,
        zero_division=0,
        digits=3
    )
    print(report)

    cm = confusion_matrix(y_true, y_pred, labels=ALLOWED_LABELS)
    print("Confusion Matrix (rows=true, cols=pred):")
    print("Labels:", ALLOWED_LABELS)
    print(cm)


# ---------------------------- Main menu -----------------------------------------

if __name__ == "__main__":
    print("Choose mode:")
    print("1 → Create random 100-review annotation CSV")
    print("2 → Evaluate labeled CSV (precision / recall / F1)")
    choice = input("Enter 1 or 2: ").strip()

    if choice == "1":
        create_annotation_file()
    elif choice == "2":
        evaluate_annotations()
    else:
        print("Invalid choice.")