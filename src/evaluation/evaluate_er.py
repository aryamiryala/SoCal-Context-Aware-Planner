import json
import random
import os

INPUT_PATH = "data/processed/entity_resolution/merged_locations.json"
OUTPUT_PATH = "src/evaluation/er_sample.json"
SAMPLE_SIZE = 50


def sample_locations():
    if not os.path.exists(INPUT_PATH):
        print(f"File not found: {INPUT_PATH}")
        return

    with open(INPUT_PATH, "r") as f:
        data = json.load(f)

    if len(data) < SAMPLE_SIZE:
        print(f"Warning: dataset has only {len(data)} locations")

    sample = random.sample(data, min(SAMPLE_SIZE, len(data)))

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)

    with open(OUTPUT_PATH, "w") as f:
        json.dump(sample, f, indent=2)

    print(f"Sampled {len(sample)} locations → saved to {OUTPUT_PATH}")


def compute_accuracy():
    """
    After manual labeling, add a field:
    "is_correct": true/false
    to each object in er_sample.json
    """

    if not os.path.exists(OUTPUT_PATH):
        print(f"File not found: {OUTPUT_PATH}")
        return

    with open(OUTPUT_PATH, "r") as f:
        data = json.load(f)

    total = len(data)
    correct = sum(1 for item in data if item.get("is_correct") == True)

    if total == 0:
        print("No data found")
        return

    accuracy = correct / total

    print("\n=== Entity Resolution Evaluation ===")
    print(f"Total samples: {total}")
    print(f"Correct matches: {correct}")
    print(f"Accuracy: {accuracy:.2%}")


if __name__ == "__main__":
    print("Choose mode:")
    print("1 → Sample locations")
    print("2 → Compute accuracy")

    choice = input("Enter 1 or 2: ")

    if choice == "1":
        sample_locations()
    elif choice == "2":
        compute_accuracy()
    else:
        print("Invalid choice")