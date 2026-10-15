"""compare_gdc.py - agreement between the report-extracted weak labels and GDC's
curator-abstracted clinical fields (THESIS_LOG.md, Phase 12).

GDC's `ajcc_pathologic_t`, `ajcc_pathologic_n` and `morphology` were abstracted
from the same pathology reports by trained curators, independently of
extract_fields.py. Agreement with them is a second, independent check on the weak
labels, over far more cases than a hand-labelled gold set. GDC carries no
histologic grade for TCGA COAD/READ (tumor_grade is empty for all 633 cases), so
grade cannot be checked this way.

Input: ../gdc_clinical_coad_read.tsv, downloaded from the GDC API (fields and
query in THESIS_LOG.md, Phase 12). A case can carry several diagnoses in GDC -
including unrelated earlier cancers (prostate, breast, ...) - so the colorectal
one is chosen by its site of origin, never by position.

    python3 compare_gdc.py            # prints the tables, writes gdc_agreement.json
"""
import csv
import json
import re
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
GDC = HERE.parent / "gdc_clinical_coad_read.tsv"
LABELS = HERE / "structured_labels.json"
SPLITS = HERE.parent / "dataset_manifests_final"

CRC_SITE = re.compile(r"colon|rectum|rectosigmoid|cecum|flexure|appendix", re.I)
MISSING = {"", "Not Reported", "Unknown", "NX", "TX"}


def colorectal_diagnosis(row):
    """The diagnosis entry that belongs to the colorectal tumour, or None."""
    k = 0
    cands = []
    while f"diagnoses.{k}.primary_diagnosis" in row or f"diagnoses.{k}.ajcc_pathologic_t" in row:
        d = {f: row.get(f"diagnoses.{k}.{f}", "") for f in
             ("ajcc_pathologic_t", "ajcc_pathologic_n", "morphology",
              "primary_diagnosis", "tissue_or_organ_of_origin")}
        if CRC_SITE.search(d["tissue_or_organ_of_origin"]):
            cands.append(d)
        k += 1
    if not cands:
        return None
    # prefer the entry that actually carries staging
    cands.sort(key=lambda d: (d["ajcc_pathologic_t"] in MISSING, d["ajcc_pathologic_n"] in MISSING))
    return cands[0]


def gdc_t(d):
    m = re.match(r"T([1-4])", d["ajcc_pathologic_t"])
    return int(m.group(1)) if m else None


def gdc_node_pos(d):
    n = d["ajcc_pathologic_n"]
    if n in MISSING or not n.startswith("N"):
        return None
    return not n.startswith("N0")


def gdc_mucinous(d):
    m = d["morphology"]
    if m in MISSING:
        return None
    # 8480 mucinous adenocarcinoma, 8481 mucin-producing, 8490 signet-ring cell
    return m.split("/")[0] in {"8480", "8481", "8490"}


def kappa(pairs):
    n = len(pairs)
    if not n:
        return None
    po = sum(a == b for a, b in pairs) / n
    ca, cb = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    pe = sum(ca[c] * cb[c] for c in set(ca) | set(cb)) / n / n
    return (po - pe) / (1 - pe) if pe < 1 else None


def split_of():
    out = {}
    for name in ("train_coad", "test_coad", "holdout_read"):
        f = SPLITS / f"{name}.json"
        if f.exists():
            txt = f.read_text()
            for cid in set(re.findall(r"TCGA-[A-Z0-9]{2}-[A-Z0-9]{4}", txt)):
                out[cid] = name
    return out


def main():
    gdc = {r["submitter_id"]: r for r in csv.DictReader(open(GDC), delimiter="\t")}
    labels = json.load(open(LABELS))
    splits = split_of()

    comps = {
        "pt_stage": (lambda L: L.get("pt_stage"), gdc_t),
        "node_positive": (lambda L: L.get("lymph_node_positive"), gdc_node_pos),
        "mucinous": (lambda L: None if L.get("histologic_type") is None
                     else L["histologic_type"] in ("mucinous", "signet_ring", "signet-ring"),
                     gdc_mucinous),
    }
    no_gdc, no_crc = [], []
    pairs = {t: [] for t in comps}
    for cid, entry in labels.items():
        row = gdc.get(cid)
        if row is None:
            no_gdc.append(cid); continue
        d = colorectal_diagnosis(row)
        if d is None:
            no_crc.append(cid); continue
        for t, (ours, theirs) in comps.items():
            a, b = ours(entry["labels"]), theirs(d)
            if a is not None and b is not None:
                pairs[t].append((cid, splits.get(cid, "?"), a, b))

    print(f"cases with labels: {len(labels)} · not in GDC file: {len(no_gdc)} · "
          f"no colorectal diagnosis in GDC: {len(no_crc)}")
    result = {"n_cases": len(labels), "not_in_gdc": no_gdc, "no_colorectal_dx": no_crc,
              "fields": {}}
    for t, ps in pairs.items():
        ab = [(a, b) for _, _, a, b in ps]
        agree = sum(a == b for a, b in ab)
        conf = Counter((a, b) for a, b in ab)
        by_split = {}
        for s in ("train_coad", "test_coad", "holdout_read"):
            sub = [(a, b) for _, sp, a, b in ps if sp == s]
            if sub:
                by_split[s] = {"n": len(sub), "agreement": sum(a == b for a, b in sub) / len(sub)}
        k = kappa(ab)
        print(f"\n{t}: n={len(ab)}  agreement {agree/len(ab):.3f}  kappa {k:.3f}")
        print("   ours -> GDC counts:", dict(sorted(conf.items(), key=str)))
        for s, v in by_split.items():
            print(f"   {s:13s} n={v['n']:3d}  agreement {v['agreement']:.3f}")
        result["fields"][t] = {
            "n": len(ab), "agreement": agree / len(ab), "kappa": k,
            "confusion_ours_vs_gdc": {f"{a}->{b}": c for (a, b), c in conf.items()},
            "by_split": by_split,
            "disagreements": [cid for cid, _, a, b in ps if a != b],
        }
    (HERE / "gdc_agreement.json").write_text(json.dumps(result, indent=1, default=str))
    print("\nwrote gdc_agreement.json")


if __name__ == "__main__":
    main()
