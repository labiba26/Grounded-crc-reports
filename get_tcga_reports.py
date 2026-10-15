import re
import json
import requests
from pathlib import Path

# --------------------------------------------------
# Paths
# --------------------------------------------------

BASE = Path.home() / "TCGA_thesis"
COAD_LIST = BASE / "COAD_H5_list.txt"
READ_LIST = BASE / "READ_H5_list.txt"

OUT_DIR = BASE / "reports"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# --------------------------------------------------
# Extract TCGA case IDs from H5 filenames
# Example:
# TCGA-DM-A28M-01Z-00-DX1.xxxxx.h5
# -> TCGA-DM-A28M
# --------------------------------------------------

def extract_cases(path):
    cases = set()

    with open(path, "r") as f:
        for line in f:
            line = line.strip()

            if not line:
                continue

            match = re.match(r"(TCGA-[A-Z0-9]+-[A-Z0-9]+)", line)

            if match:
                cases.add(match.group(1))

    return sorted(cases)


coad_cases = extract_cases(COAD_LIST)
read_cases = extract_cases(READ_LIST)

all_cases = sorted(set(coad_cases + read_cases))

print("COAD cases:", len(coad_cases))
print("READ cases:", len(read_cases))
print("Total unique cases:", len(all_cases))

# --------------------------------------------------
# Query GDC
# --------------------------------------------------

url = "https://api.gdc.cancer.gov/files"

payload = {
    "filters": {
        "op": "and",
        "content": [
            {
                "op": "in",
                "content": {
                    "field": "cases.submitter_id",
                    "value": all_cases
                }
            },
            {
                "op": "in",
                "content": {
                    "field": "data_type",
                    "value": ["Pathology Report"]
                }
            },
            {
                "op": "in",
                "content": {
                    "field": "data_format",
                    "value": ["PDF"]
                }
            }
        ]
    },
    "fields": ",".join([
        "file_id",
        "file_name",
        "cases.submitter_id",
        "data_type",
        "data_format",
        "access",
        "file_size"
    ]),
    "format": "JSON",
    "size": 10000
}

print("\nQuerying GDC...")

response = requests.post(
    url,
    json=payload,
    timeout=120
)

response.raise_for_status()

data = response.json()

hits = data["data"]["hits"]

print("Pathology reports found:", len(hits))

# --------------------------------------------------
# Save metadata
# --------------------------------------------------

metadata_file = BASE / "pathology_report_metadata.json"

with open(metadata_file, "w") as f:
    json.dump(hits, f, indent=2)

print("Saved metadata to:")
print(metadata_file)

# --------------------------------------------------
# Print matches
# --------------------------------------------------

for hit in hits:
    print(
        hit.get("cases", [{}])[0].get("submitter_id"),
        hit.get("file_name"),
        hit.get("file_id")
    )

