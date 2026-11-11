import json
import requests
from pathlib import Path
import time

BASE = Path.home() / "TCGA_thesis"
REPORT_DIR = BASE / "reports"

REPORT_DIR.mkdir(parents=True, exist_ok=True)

with open(BASE / "pathology_report_metadata.json") as f:
    reports = json.load(f)

print("Reports to download:", len(reports))
print("Saving to:", REPORT_DIR)
print()

for i, report in enumerate(reports, 1):

    file_id = report["file_id"]
    file_name = report["file_name"]

    output = REPORT_DIR / file_name

    if output.exists() and output.stat().st_size > 0:
        print(f"[{i}/{len(reports)}] Already exists: {file_name}")
        continue

    url = f"https://api.gdc.cancer.gov/data/{file_id}"

    print(f"[{i}/{len(reports)}] Downloading {file_name}")

    try:
        response = requests.get(url, timeout=120)
        response.raise_for_status()

        with open(output, "wb") as f:
            f.write(response.content)

        print("    ✓ downloaded")

    except Exception as e:
        print("    ✗ ERROR:", e)

    time.sleep(0.1)

print("\nFinished.")

