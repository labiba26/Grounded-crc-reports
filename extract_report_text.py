"""
extract_report_text.py

Fills in the actual TEXT of your 594 GDC pathology report PDFs, using the
published TCGA-Reports corpus (Kefeli et al., Patterns 2024 - 9,523 TCGA
pathology reports OCR'd via AWS Textract) wherever it has an exact match,
and clearly flags whatever it doesn't cover so you know exactly which PDFs
still need OCR yourself.

WHY: your dataset_index.json / metadata.csv only ever stored *paths* to the
report PDFs, never their text. This is the step that actually gets you
report TEXT to pair with UNI2-h features for the reasoning schema.

INPUT (paths in CONFIG below):
    pathology_report_metadata.json  - your 594 GDC report records
                                       (file_name, file_id, ...)
    TCGA_Reports.csv                - the published corpus. Download it:
        curl -L -o TCGA_Reports.csv.zip \
          https://raw.githubusercontent.com/jkefeli/tcga-path-reports/main/TCGA_Reports.csv.zip
        unzip TCGA_Reports.csv.zip
      Cite: Kefeli J, et al. "TCGA-Reports: A machine-readable pathology
      report resource for benchmarking text-based AI models." Patterns 2024.

OUTPUT (written to --out_dir):
    report_text_by_file.json   -> {report_file_name: {"case_id", "text",
                                    "source": "tcga_reports_corpus"}}
                                   for every report matched by exact UUID
    reports_needing_ocr.json   -> the report records NOT found in the
                                   corpus - these still need OCR from your
                                   own PDFs (pdf_path is under your
                                   reports/ dir, named the same as file_name)
    summary.txt                -> coverage stats

USAGE:
    python extract_report_text.py \
        --report_metadata pathology_report_metadata.json \
        --tcga_reports_csv TCGA_Reports.csv \
        --out_dir ./report_text
"""

import argparse
import csv
import json
import re
import sys
from pathlib import Path

# patient_filename in TCGA_Reports.csv looks like:
#   TCGA-AA-A01V.c5348097-4824-490a-b2ff-f257bdc9c633
CORPUS_ROW_RE = re.compile(
    r"^(TCGA-[0-9A-Za-z]{2}-[0-9A-Za-z]{4})\.([0-9a-fA-F-]{36})$"
)

# your GDC file_name looks like:
#   TCGA-AA-A01V.C5348097-4824-490A-B2FF-F257BDC9C633.PDF
OUR_FILENAME_RE = re.compile(
    r"^(TCGA-[0-9A-Za-z]{2}-[0-9A-Za-z]{4})\.([0-9A-Fa-f-]{36})\.PDF$"
)


def load_corpus(csv_path: Path) -> dict:
    """Returns {lowercase uuid: report text} from TCGA_Reports.csv."""
    csv.field_size_limit(10**7)  # report text can exceed the default limit
    by_uuid = {}
    unparsed = 0
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            m = CORPUS_ROW_RE.match(row["patient_filename"])
            if m:
                by_uuid[m.group(2).lower()] = row["text"]
            else:
                unparsed += 1
    if unparsed:
        print(f"  (note: {unparsed} corpus rows had an unexpected filename format, skipped)")
    return by_uuid


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--report_metadata", required=True, type=Path)
    p.add_argument("--tcga_reports_csv", required=True, type=Path)
    p.add_argument("--out_dir", default=Path("./report_text"), type=Path)
    args = p.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)

    our_reports = json.loads(args.report_metadata.read_text())
    print(f"Your reports to resolve: {len(our_reports)}")

    print(f"Loading corpus from {args.tcga_reports_csv} ...")
    corpus_by_uuid = load_corpus(args.tcga_reports_csv)
    print(f"Corpus rows parsed: {len(corpus_by_uuid)}")

    matched = {}
    needs_ocr = []
    unparsed_filename = []

    for r in our_reports:
        file_name = r["file_name"]
        m = OUR_FILENAME_RE.match(file_name)
        if not m:
            unparsed_filename.append(r)
            continue

        case_id, uuid = m.group(1).upper(), m.group(2).lower()
        text = corpus_by_uuid.get(uuid)

        if text is not None:
            matched[file_name] = {
                "case_id": case_id,
                "text": text,
                "source": "tcga_reports_corpus",
            }
        else:
            needs_ocr.append(r)

    (args.out_dir / "report_text_by_file.json").write_text(
        json.dumps(matched, indent=2)
    )
    (args.out_dir / "reports_needing_ocr.json").write_text(
        json.dumps(needs_ocr, indent=2)
    )

    summary = [
        "=== Report text resolution summary ===",
        f"Total reports:                {len(our_reports)}",
        f"Matched from TCGA-Reports corpus: {len(matched)}",
        f"Still need OCR (not in corpus):   {len(needs_ocr)}",
        f"Unparseable file_name (check manually): {len(unparsed_filename)}",
        "",
        "Coverage: {:.1f}%".format(100 * len(matched) / len(our_reports)) if our_reports else "n/a",
        "",
        "Cite the corpus if you use it:",
        "  Kefeli J, et al. TCGA-Reports: A machine-readable pathology report",
        "  resource for benchmarking text-based AI models. Patterns, 2024.",
    ]
    if needs_ocr:
        summary += ["", "Cases still needing OCR (first 15):"]
        summary += [f"  {r['file_name']}" for r in needs_ocr[:15]]

    text = "\n".join(summary)
    (args.out_dir / "summary.txt").write_text(text)
    print("\n" + text + "\n")

    if unparsed_filename:
        print(
            f"WARNING: {len(unparsed_filename)} of your report records had a "
            "file_name that didn't match the expected TCGA barcode.UUID.PDF "
            "pattern - check these manually.",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
