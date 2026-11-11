"""
build_multimodal_dataset.py

Builds a case-level multimodal dataset index that pairs UNI2-h whole-slide
features (H5 files) with GDC pathology reports for the COAD+READ colorectal
cohort, validates the pairing, and produces case-level train/test splits with
READ held out entirely for cross-cohort generalization testing.

WHY CASE-LEVEL (not slide-level or file-level):
A single TCGA case can have more than one slide (and occasionally more than
one report). If splitting is done at the slide/file level instead of the case
level, slides from the same patient can leak across train and test, inflating
performance. This script always groups by case_id before splitting.

EXPECTED INPUT LAYOUT (edit paths in CONFIG below, or pass --h5_dir etc.):

    h5_dir/
        COAD/  *.h5      <- UNI2-h feature files, one per slide
        READ/  *.h5

    reports_dir/
        *.txt  (or .json / .pdf)   <- GDC pathology reports

If your H5 files are NOT already split into COAD/READ subfolders, pass a
--cohort_manifest CSV with two columns: case_id,cohort   (cohort in {COAD,READ})
and point --h5_dir at a single flat folder instead.

Report files just need the TCGA case id somewhere in the filename, e.g.
    TCGA-AA-3506.report.txt
    TCGA-AA-3506_gdc_report.pdf

OUTPUT (written to --out_dir):
    dataset_index.json   -> every case found, with its slides/reports/cohort
    train_coad.json      -> COAD cases for training (case-level split)
    test_coad.json        -> COAD cases held out for testing
    holdout_read.json    -> ALL READ cases, held out for generalization testing
    summary.txt          -> human-readable stats + any warnings

USAGE:
    python build_multimodal_dataset.py \
        --h5_dir /path/to/h5_root \
        --reports_dir /path/to/reports \
        --out_dir ./dataset_manifests \
        --test_size 0.2 --seed 42

Requires: h5py, scikit-learn  (pip install h5py scikit-learn)
"""

from __future__ import annotations  # keeps `str | None` / `dict[str, str]` hints
                                     # working on Python < 3.10, common on shared
                                     # HPC servers with an older module-loaded python

import argparse
import csv
import json
import logging
import re
import sys
from collections import defaultdict
from pathlib import Path

import h5py
from sklearn.model_selection import train_test_split

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)

# TCGA case-id barcode pattern, e.g. TCGA-AA-3506
CASE_ID_RE = re.compile(r"TCGA-[0-9A-Za-z]{2}-[0-9A-Za-z]{4}")

H5_EXTS = {".h5", ".hdf5"}
REPORT_EXTS = {".txt", ".json", ".pdf"}


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def extract_case_id(filename: str) -> str | None:
    """Pull a TCGA case id (e.g. TCGA-AA-3506) out of a filename."""
    m = CASE_ID_RE.search(filename)
    return m.group(0).upper() if m else None


def load_cohort_manifest(path: str | None) -> dict[str, str]:
    """Optional CSV with columns case_id,cohort. Returns {} if not given."""
    if not path:
        return {}
    mapping = {}
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            case_id = row["case_id"].strip().upper()
            cohort = row["cohort"].strip().upper()
            mapping[case_id] = cohort
    log.info(f"Loaded cohort manifest for {len(mapping)} cases from {path}")
    return mapping


# Keys that are known NOT to be the patch-feature array, so the fallback
# search below never mistakes them for one (this was silently happening:
# a (num_patches, 2) coords array matches the same "2D dataset" heuristic
# as a real (num_patches, 1536) feature array).
NON_FEATURE_KEYS = {"coords", "coordinates", "coords_patching", "coord", "patch_coords"}
# Try these names first, in order, before falling back to shape-guessing.
KNOWN_FEATURE_KEYS = ("features", "feats", "feature", "patch_features", "embeddings")
# A real patch embedding is expected to have a "wide" last dimension (UNI2-h
# is 1536-d). Coords/indices arrays have a last dim of 2-4. Used only to warn,
# never to silently drop data.
MIN_PLAUSIBLE_FEATURE_DIM = 16


def inspect_h5(path: Path) -> dict:
    """Return basic shape info for a UNI2-h feature file. Never raises.

    Handles both layouts seen in the wild:
      - 2D: (num_patches, feature_dim)
      - 3D: (1, num_patches, feature_dim)  <- leading slide/batch dim of 1
    """
    info = {"num_patches": None, "feature_dim": None, "has_coords": False, "error": None}
    try:
        with h5py.File(path, "r") as f:
            feat_key = next((k for k in KNOWN_FEATURE_KEYS if k in f), None)
            if feat_key is None:
                # Fallback: first dataset (NOT group) with ndim 2/3 that isn't
                # a known non-feature key. isinstance check avoids crashing
                # (and silently swallowing the error) when a Group sorts
                # before the real dataset alphabetically.
                feat_key = next(
                    (
                        k for k in f.keys()
                        if k not in NON_FEATURE_KEYS
                        and isinstance(f[k], h5py.Dataset)
                        and f[k].ndim in (2, 3)
                    ),
                    None,
                )
            if feat_key is not None:
                shape = f[feat_key].shape
                if len(shape) == 3:
                    info["num_patches"], info["feature_dim"] = shape[1], shape[2]
                elif len(shape) == 2:
                    info["num_patches"], info["feature_dim"] = shape[0], shape[1]
                if info["feature_dim"] is not None and info["feature_dim"] < MIN_PLAUSIBLE_FEATURE_DIM:
                    info["error"] = (
                        f"picked key '{feat_key}' with feature_dim={info['feature_dim']}, "
                        f"which looks like a coords/index array, not a real embedding "
                        f"(keys in file: {list(f.keys())})"
                    )
            else:
                info["error"] = f"no feature-shaped dataset found (keys in file: {list(f.keys())})"
            info["has_coords"] = any(
                k in f for k in ("coords", "coordinates", "coords_patching")
            )
    except Exception as e:  # noqa: BLE001 - we want to log and continue, not crash the pipeline
        info["error"] = str(e)
    return info


def scan_h5_files(h5_dir: Path, cohort_manifest: dict[str, str]) -> tuple[dict[str, list[Path]], dict]:
    """
    Walk h5_dir recursively. Cohort is taken from (in priority order):
      1. an immediate 'COAD'/'READ' parent subfolder name
      2. the cohort_manifest lookup by case_id
    Returns ({case_id: [h5 paths]}, diagnostics).
    """
    case_to_files: dict[str, list[Path]] = defaultdict(list)
    diag = {"h5_files_found": 0, "h5_case_id_failures": [], "sample_filenames": []}

    for path in h5_dir.rglob("*"):
        if path.suffix.lower() not in H5_EXTS:
            continue
        diag["h5_files_found"] += 1
        if len(diag["sample_filenames"]) < 5:
            diag["sample_filenames"].append(str(path))
        case_id = extract_case_id(path.name) or extract_case_id(str(path.parent))
        if not case_id:
            diag["h5_case_id_failures"].append(str(path))
            continue
        case_to_files[case_id].append(path)

    return dict(case_to_files), diag


def resolve_cohort(path: Path, case_id: str, cohort_manifest: dict[str, str]) -> str:
    # Substring match, not exact match: folders are often named "TCGA-COAD" /
    # "TCGA-READ" rather than bare "COAD" / "READ".
    parts_upper = [p.upper() for p in path.parts]
    if any("COAD" in p for p in parts_upper):
        return "COAD"
    if any("READ" in p for p in parts_upper):
        return "READ"
    return cohort_manifest.get(case_id, "UNKNOWN")


def scan_reports(reports_dir: Path) -> tuple[dict[str, list[Path]], dict]:
    """Returns ({case_id: [report paths]}, diagnostics)."""
    case_to_reports: dict[str, list[Path]] = defaultdict(list)
    diag = {"report_files_found": 0, "report_case_id_failures": [], "sample_filenames": []}
    for path in reports_dir.rglob("*"):
        if path.suffix.lower() not in REPORT_EXTS:
            continue
        diag["report_files_found"] += 1
        if len(diag["sample_filenames"]) < 5:
            diag["sample_filenames"].append(str(path))
        case_id = extract_case_id(path.name)
        if not case_id:
            diag["report_case_id_failures"].append(str(path))
            continue
        case_to_reports[case_id].append(path)
    return dict(case_to_reports), diag


# --------------------------------------------------------------------------- #
# Core pipeline
# --------------------------------------------------------------------------- #

def build_case_records(
    h5_dir: Path, reports_dir: Path, cohort_manifest: dict[str, str]
) -> tuple[dict, dict]:
    slide_index, h5_diag = scan_h5_files(h5_dir, cohort_manifest)
    report_index, report_diag = scan_reports(reports_dir)

    all_case_ids = sorted(set(slide_index) | set(report_index))
    records = {}
    stats = {
        "total_cases_seen": len(all_case_ids),
        "cases_missing_h5": [],
        "cases_missing_report": [],
        "cases_unknown_cohort": [],
        "h5_read_errors": [],
        "h5_diag": h5_diag,
        "report_diag": report_diag,
    }

    for case_id in all_case_ids:
        h5_paths = slide_index.get(case_id, [])
        report_paths = report_index.get(case_id, [])

        if not h5_paths:
            stats["cases_missing_h5"].append(case_id)
            continue  # can't use this case without visual features
        if not report_paths:
            stats["cases_missing_report"].append(case_id)
            continue  # can't use this case without a report

        cohort = resolve_cohort(h5_paths[0], case_id, cohort_manifest)
        if cohort == "UNKNOWN":
            stats["cases_unknown_cohort"].append(case_id)
            continue

        slide_info = []
        for p in h5_paths:
            info = inspect_h5(p)
            if info["error"]:
                stats["h5_read_errors"].append((str(p), info["error"]))
            slide_info.append({"path": str(p), **info})

        records[case_id] = {
            "case_id": case_id,
            "cohort": cohort,
            "num_slides": len(h5_paths),
            "num_reports": len(report_paths),
            "slides": slide_info,
            "reports": [str(p) for p in report_paths],
        }

    return records, stats


def split_dataset(records: dict, test_size: float, seed: int) -> dict:
    coad_ids = sorted(cid for cid, r in records.items() if r["cohort"] == "COAD")
    read_ids = sorted(cid for cid, r in records.items() if r["cohort"] == "READ")

    if len(coad_ids) < 2:
        raise ValueError("Not enough COAD cases to split.")

    train_ids, test_ids = train_test_split(
        coad_ids, test_size=test_size, random_state=seed, shuffle=True
    )

    return {
        "train_coad": sorted(train_ids),
        "test_coad": sorted(test_ids),
        "holdout_read": read_ids,
    }


def write_manifest(records: dict, ids: list[str], out_path: Path) -> None:
    payload = [records[cid] for cid in ids]
    out_path.write_text(json.dumps(payload, indent=2))
    log.info(f"Wrote {len(payload)} cases -> {out_path}")


def write_summary(records: dict, stats: dict, splits: dict, out_path: Path) -> None:
    total_patches = [
        s["num_patches"]
        for r in records.values()
        for s in r["slides"]
        if s["num_patches"] is not None
    ]
    lines = [
        "=== Dataset build summary ===",
        f"Usable cases (H5 + report + known cohort): {len(records)}",
        f"  COAD: {sum(1 for r in records.values() if r['cohort'] == 'COAD')}",
        f"  READ: {sum(1 for r in records.values() if r['cohort'] == 'READ')}",
        "",
        "=== Split sizes ===",
        f"  train_coad:   {len(splits['train_coad'])}",
        f"  test_coad:    {len(splits['test_coad'])}",
        f"  holdout_read: {len(splits['holdout_read'])}",
        "",
        "=== Patch count stats (per slide) ===",
    ]
    if total_patches:
        lines += [
            f"  n_slides_with_features: {len(total_patches)}",
            f"  min: {min(total_patches)}  max: {max(total_patches)}  "
            f"mean: {sum(total_patches)/len(total_patches):.1f}",
        ]
    else:
        lines.append("  (no readable feature shapes found)")

    lines += [
        "",
        "=== Warnings ===",
        f"  Cases with H5 but no report (dropped): {len(stats['cases_missing_report'])}",
        f"  Cases with report but no H5 (dropped): {len(stats['cases_missing_h5'])}",
        f"  Cases with unresolved cohort (dropped): {len(stats['cases_unknown_cohort'])}",
        f"  H5 files that failed to read: {len(stats['h5_read_errors'])}",
    ]
    if stats["cases_missing_report"]:
        lines.append(f"    missing_report ids (first 10): {stats['cases_missing_report'][:10]}")
    if stats["cases_missing_h5"]:
        lines.append(f"    missing_h5 ids (first 10): {stats['cases_missing_h5'][:10]}")
    if stats["cases_unknown_cohort"]:
        lines.append(f"    unknown_cohort ids (first 10): {stats['cases_unknown_cohort'][:10]}")
    if stats["h5_read_errors"]:
        lines.append(f"    read errors (first 5): {stats['h5_read_errors'][:5]}")

    text = "\n".join(lines)
    out_path.write_text(text)
    print("\n" + text + "\n")


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def parse_args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--h5_dir", required=True, type=Path, help="Root folder containing UNI2-h .h5 files")
    p.add_argument("--reports_dir", required=True, type=Path, help="Folder containing GDC pathology reports")
    p.add_argument("--out_dir", default=Path("./dataset_manifests"), type=Path)
    p.add_argument("--cohort_manifest", default=None, help="Optional CSV: case_id,cohort")
    p.add_argument("--test_size", default=0.2, type=float, help="COAD test fraction (case-level)")
    p.add_argument("--seed", default=42, type=int)
    return p.parse_args()


def main():
    args = parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    cohort_manifest = load_cohort_manifest(args.cohort_manifest)
    records, stats = build_case_records(args.h5_dir, args.reports_dir, cohort_manifest)

    h5_diag, report_diag = stats["h5_diag"], stats["report_diag"]
    print("\n=== Scan diagnostics (always shown) ===")
    print(f"H5 files found under --h5_dir:      {h5_diag['h5_files_found']}")
    print(f"  -> case id NOT extractable from:  {len(h5_diag['h5_case_id_failures'])} filenames")
    print(f"  -> sample H5 filenames seen:      {h5_diag['sample_filenames']}")
    print(f"Report files found under --reports_dir: {report_diag['report_files_found']}")
    print(f"  -> case id NOT extractable from:      {len(report_diag['report_case_id_failures'])} filenames")
    print(f"  -> sample report filenames seen:      {report_diag['sample_filenames']}")
    print("=" * 45 + "\n")

    if not records:
        log.error(
            "No usable cases found. Look at the diagnostics above:\n"
            "  - If 'H5 files found' is 0: --h5_dir path is wrong, or your files "
            "don't have a .h5/.hdf5 extension.\n"
            "  - If 'H5 files found' > 0 but most filenames failed case-id extraction: "
            "your H5 files are likely named by UUID, not by TCGA barcode — the case id "
            "has to come from a mapping file instead. Tell me and I'll adapt the script.\n"
            "  - Same two checks apply to the report side."
        )
        sys.exit(1)

    (args.out_dir / "dataset_index.json").write_text(
        json.dumps(list(records.values()), indent=2)
    )

    splits = split_dataset(records, args.test_size, args.seed)
    write_manifest(records, splits["train_coad"], args.out_dir / "train_coad.json")
    write_manifest(records, splits["test_coad"], args.out_dir / "test_coad.json")
    write_manifest(records, splits["holdout_read"], args.out_dir / "holdout_read.json")

    write_summary(records, stats, splits, args.out_dir / "summary.txt")


if __name__ == "__main__":
    main()
