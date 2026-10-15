import json
import re
import csv
from pathlib import Path
from collections import defaultdict

BASE = Path.home() / "TCGA_thesis"

COAD_LIST = BASE / "COAD_H5_list.txt"
READ_LIST = BASE / "READ_H5_list.txt"

CASE_MAPPING = BASE / "tcga_case_mapping.json"
REPORT_METADATA = BASE / "pathology_report_metadata.json"

OUTPUT = BASE / "metadata.csv"


# ==================================================
# 1. Read H5 filenames
# ==================================================

def read_h5_files(path):

    files = []

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
                files.append({
                    "case_id": match.group(1),
                    "filename": filename
                })

    return files


coad_h5 = read_h5_files(COAD_LIST)
read_h5 = read_h5_files(READ_LIST)

all_h5 = coad_h5 + read_h5

print("H5 files:", len(all_h5))


# ==================================================
# 2. Index H5 files by case
# ==================================================

h5_by_case = defaultdict(list)

for item in all_h5:
    h5_by_case[item["case_id"]].append(item["filename"])


# ==================================================
# 3. Load GDC case metadata
# ==================================================

with open(CASE_MAPPING) as f:
    cases = json.load(f)


# ==================================================
# 4. Load GDC pathology-report file metadata
# ==================================================

with open(REPORT_METADATA) as f:
    reports = json.load(f)


# ==================================================
# 5. Index pathology REPORT FILES by CASE ID
# ==================================================

reports_by_case = defaultdict(list)

for report in reports:

    for case in report.get("cases", []):

        case_id = case.get("submitter_id")

        if case_id:

            reports_by_case[case_id].append({
                "file_id": report.get("file_id"),
                "file_name": report.get("file_name"),
                "access": report.get("access"),
                "file_size": report.get("file_size")
            })


# ==================================================
# 6. Build dataset
# ==================================================

rows = []

for case in cases:

    case_id = case.get("submitter_id")

    project = (
        case.get("project", {})
        .get("project_id", "")
    )

    h5_files = h5_by_case.get(case_id, [])

    if not h5_files:
        continue


    # ----------------------------------------------
    # GDC slides
    # ----------------------------------------------

    slide_ids = case.get(
        "submitter_slide_ids",
        []
    )


    # ----------------------------------------------
    # GDC samples
    # ----------------------------------------------

    samples = case.get(
        "samples",
        []
    )


    # ----------------------------------------------
    # Pathology reports for this CASE
    # ----------------------------------------------

    case_reports = reports_by_case.get(
        case_id,
        []
    )


    # ----------------------------------------------
    # Create rows
    # ----------------------------------------------

    # ----------------------------------------------
    # Samples associated with pathology reports
    # (case-level info: GDC's /files response for a
    # report does not tell us which specific sample/
    # portion it belongs to, so this cannot be tied to
    # one particular report when a case has more than
    # one. Reported honestly as a joined list instead
    # of picking report_samples[0] and pretending it
    # corresponds to whichever report is being written.)
    # ----------------------------------------------

    report_samples = []

    for sample in samples:

        pathology_uuid = sample.get(
            "pathology_report_uuid"
        )

        if pathology_uuid:

            report_samples.append({
                "sample_id": sample.get(
                    "submitter_id"
                ),
                "pathology_report_uuid":
                    pathology_uuid
            })

    sample_ids_joined = "|".join(
        s["sample_id"] for s in report_samples if s["sample_id"]
    )
    pathology_uuids_joined = "|".join(
        s["pathology_report_uuid"] for s in report_samples
    )

    report_files_joined = "|".join(
        r["file_name"] for r in case_reports
    )
    report_file_ids_joined = "|".join(
        r["file_id"] for r in case_reports
    )
    report_access_joined = "|".join(
        str(r["access"]) for r in case_reports
    )

    for h5_file in h5_files:

        # Extract slide ID from H5 filename.
        # H5 filenames look like:
        #   TCGA-XX-XXXX-01Z-00-DX1.<uuid>.h5
        # i.e. sample+vial (01Z) - portion (00, digits
        # only, NO trailing letter) - analyte+slide (DX1).
        # The previous pattern required a trailing letter
        # on the portion segment too, which real barcodes
        # never have, so it matched 0/600 real filenames.
        match = re.match(
            r"(TCGA-[A-Z0-9]+-[A-Z0-9]+-\d+[A-Z]-\d+-[A-Z0-9]+)",
            h5_file
        )

        if match:
            slide_id = match.group(1)
        else:
            slide_id = ""

        # Check whether this slide exists in GDC
        slide_in_gdc = slide_id in slide_ids

        # ------------------------------------------
        # One row per H5 slide. When a case has more
        # than one report, list them all on that same
        # row (pipe-joined) instead of exploding into
        # one row per (slide, report) combination -
        # the old code fabricated slide<->report pairs
        # that were never verified to correspond (e.g.
        # 2 slides x 2 reports produced 4 "pairs" for
        # what is really just 2 slides and 2 reports).
        # ------------------------------------------

        rows.append({

            "case_id":
                case_id,

            "project":
                project,

            "slide_id":
                slide_id,

            "slide_in_gdc":
                slide_in_gdc,

            "h5_file":
                h5_file,

            "report_file":
                report_files_joined,

            "report_file_id":
                report_file_ids_joined,

            "report_access":
                report_access_joined,

            "sample_id":
                sample_ids_joined,

            "pathology_report_uuid":
                pathology_uuids_joined,

            "num_case_reports":
                len(case_reports),

            "num_h5_slides":
                len(h5_files)
        })


# ==================================================
# 7. Save CSV
# ==================================================

columns = [
    "case_id",
    "project",
    "slide_id",
    "slide_in_gdc",
    "h5_file",
    "report_file",
    "report_file_id",
    "report_access",
    "sample_id",
    "pathology_report_uuid",
    "num_case_reports",
    "num_h5_slides"
]


with open(
    OUTPUT,
    "w",
    newline=""
) as f:

    writer = csv.DictWriter(
        f,
        fieldnames=columns
    )

    writer.writeheader()
    writer.writerows(rows)


# ==================================================
# 8. Summary
# ==================================================

unique_cases = len(
    set(r["case_id"] for r in rows)
)

unique_h5 = len(
    set(r["h5_file"] for r in rows)
)

unique_reports = len({
    name
    for r in rows
    for name in r["report_file"].split("|")
    if name
})

missing_reports = sum(
    not r["report_file"]
    for r in rows
)

gdc_slide_matches = sum(
    r["slide_in_gdc"]
    for r in rows
)


print()
print("=" * 50)
print("FINAL DATASET SUMMARY")
print("=" * 50)

print("Rows:", len(rows))
print("Unique cases:", unique_cases)
print("Unique H5 files:", unique_h5)
print("Unique reports:", unique_reports)
print("Missing reports:", missing_reports)
print("H5 slides found in GDC:", gdc_slide_matches)

print()
print("Saved:")
print(OUTPUT)
