import json
import re
import requests
from pathlib import Path

BASE = Path.home() / "TCGA_thesis"

# H5 filename lists
COAD_LIST = BASE / "COAD_H5_list.txt"
READ_LIST = BASE / "READ_H5_list.txt"

# Output
OUTPUT = BASE / "tcga_case_mapping.json"

# --------------------------------------------------
# Extract unique case IDs from H5 filenames
# --------------------------------------------------

def extract_cases(path):
    cases = set()

    with open(path) as f:
        for line in f:
            filename = line.strip()

            if not filename:
                continue

            match = re.match(
                r"(TCGA-[A-Z0-9]+-[A-Z0-9]+)",
                filename
            )

            if match:
                cases.add(match.group(1))

    return sorted(cases)


coad_cases = extract_cases(COAD_LIST)
read_cases = extract_cases(READ_LIST)

all_cases = sorted(set(coad_cases + read_cases))

print("COAD cases:", len(coad_cases))
print("READ cases:", len(read_cases))
print("Total cases:", len(all_cases))

# --------------------------------------------------
# Query GDC cases endpoint
# --------------------------------------------------

url = "https://api.gdc.cancer.gov/cases"

payload = {
    "filters": {
        "op": "in",
        "content": {
            "field": "submitter_id",
            "value": all_cases
        }
    },

    "fields": ",".join([
        "submitter_id",
        "case_id",
        "project.project_id",
        "primary_site",
        "disease_type",
        "slide_ids",
        "submitter_slide_ids",

        "samples.sample_id",
        "samples.submitter_id",
        "samples.sample_type",
        "samples.tissue_type",
        "samples.tumor_descriptor",
        "samples.pathology_report_uuid"
    ]),

    "format": "JSON",
    "size": 1000
}

print("\nQuerying GDC cases...")

response = requests.post(
    url,
    json=payload,
    timeout=120
)

response.raise_for_status()

data = response.json()
hits = data["data"]["hits"]

print("Cases returned:", len(hits))

# --------------------------------------------------
# Save mapping
# --------------------------------------------------

with open(OUTPUT, "w") as f:
    json.dump(hits, f, indent=2)

print("\nSaved:")
print(OUTPUT)

# --------------------------------------------------
# Summary
# --------------------------------------------------

cases_with_reports = 0
cases_with_slides = 0

for case in hits:

    samples = case.get("samples", [])

    report_uuids = set()
    sample_ids = set()

    for sample in samples:

        sample_ids.add(
            sample.get("sample_id")
        )

        uuid = sample.get(
            "pathology_report_uuid"
        )

        if uuid:
            report_uuids.add(uuid)

    if report_uuids:
        cases_with_reports += 1

    if case.get("submitter_slide_ids"):
        cases_with_slides += 1


print("\nCases with pathology report UUID:",
      cases_with_reports)

print("Cases with slide IDs:",
      cases_with_slides)
