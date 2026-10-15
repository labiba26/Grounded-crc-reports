"""cptac_labels.py - labels and slide lists for the CPTAC-COAD external test (THESIS_LOG.md).
stdlib only. Writes external/cptac_labels.json.

Sources (all public; downloaded 25-26 Sep 2026):
  cbio_cptac_coad_patient.json / _sample.json   cBioPortal study coad_cptac_2019
                                                 (Vasaikar et al., Cell 2019): HISTOLOGY,
                                                 PATHOLOGY_T_STAGE, PATHOLOGY_N_STAGE. No grade.
  cptac_coad_slides_idc.csv                      IDC slide index: one row per slide, with the
                                                 tissue modifier ("Neoplasm, Primary" / "Normal" /
                                                 blank) and pixel spacing (all 0.25 um/px, 40x).
  UNI2_h_features/CPTAC/CPTAC-COAD/*.h5          MahmoodLab UNI2-h features, one file per slide,
                                                 named <PatientID>-<ContainerIdentifier>.h5

Label mapping to the Stage 1 targets (decided BEFORE any model is run on CPTAC):
  mucinous       HISTOLOGY "Mucinous" -> True, "Not Mucinous" -> False, missing -> None
  pt_stage       T2 -> 2, T3 -> 3, T4a/T4b -> 4 (CPTAC has no T1)
  node_positive  N0 -> False; N1, N1a, N1b, N2a, N2b -> True
  grade          not available in CPTAC -> None (grade is NOT externally tested)

Slide selections (also fixed before running):
  tumour_slides  PRIMARY. Patients with >= 1 slide the IDC index calls "Neoplasm, Primary";
                 the bag is those slides only.
  all_slides     SENSITIVITY. Every cBioPortal patient; the bag is every slide of the patient,
                 as in TCGA where the bag is the case. Includes "Normal" and unlabelled slides.
Each patient also gets a `slide_group` so all_slides results can be broken down.
"""
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
FEAT = BASE / "UNI2_h_features" / "CPTAC" / "CPTAC-COAD"

T_MAP = {"T1": 1, "T2": 2, "T3": 3, "T4": 4, "T4a": 4, "T4b": 4}
N_POS = {"N1", "N1a", "N1b", "N1c", "N2", "N2a", "N2b"}


def main():
    clin = defaultdict(dict)
    for f in ("cbio_cptac_coad_patient.json", "cbio_cptac_coad_sample.json"):
        for x in json.loads((HERE / f).read_text()):
            clin[x["patientId"]][x["clinicalAttributeId"]] = x["value"]

    slides = defaultdict(list)
    for r in csv.DictReader(open(HERE / "cptac_coad_slides_idc.csv")):
        name = f"{r['PatientID']}-{r['ContainerIdentifier']}"
        path = FEAT / f"{name}.h5"
        slides[r["PatientID"]].append({
            "slide": name, "path": str(path.relative_to(BASE)), "exists": path.exists(),
            "tissue": {"Neoplasm, Primary": "tumour", "Normal": "normal"}.get(r["modifier"], "unlabelled"),
            "um_per_px": float(r["min_PixelSpacing_2sf"]) * 1000, "objective": r["ObjectiveLensPower"]})

    cases, problems = {}, []
    for pid in sorted(clin):
        c = clin[pid]
        h, t, n = c.get("HISTOLOGY"), c.get("PATHOLOGY_T_STAGE"), c.get("PATHOLOGY_N_STAGE")
        labels = {
            "mucinous": {"Mucinous": True, "Not Mucinous": False}.get(h),
            "pt_stage": T_MAP.get(t),
            "node_positive": None if n is None else (False if n == "N0" else (True if n in N_POS else None)),
            "grade": None,
        }
        for k, raw in (("mucinous", h), ("pt_stage", t), ("node_positive", n)):
            if raw is not None and labels[k] is None:
                problems.append(f"{pid}: unmapped {k} value {raw!r}")
        sl = slides.get(pid, [])
        missing = [s["slide"] for s in sl if not s["exists"]]
        if missing:
            problems.append(f"{pid}: feature file missing for {missing}")
        kinds = {s["tissue"] for s in sl}
        group = ("has_tumour_slide" if "tumour" in kinds else
                 "normal_and_unlabelled_only" if "normal" in kinds else "unlabelled_only")
        cases[pid] = {
            "labels": labels,
            "raw": {"HISTOLOGY": h, "PATHOLOGY_T_STAGE": t, "PATHOLOGY_N_STAGE": n,
                    "STAGE": c.get("STAGE"), "TUMOR_SITE": c.get("TUMOR_SITE"),
                    "MSI_STATUS": c.get("MSI_STATUS"), "SPECIMEN_PRESERVATION": c.get("SPECIMEN_PRESERVATION")},
            "slide_group": group,
            "slides": sl,
        }

    sel = {
        "tumour_slides": {pid: [s["path"] for s in c["slides"] if s["tissue"] == "tumour" and s["exists"]]
                          for pid, c in cases.items() if c["slide_group"] == "has_tumour_slide"},
        "all_slides": {pid: [s["path"] for s in c["slides"] if s["exists"]]
                       for pid, c in cases.items() if any(s["exists"] for s in c["slides"])},
    }
    summary = {}
    for name, bags in sel.items():
        summary[name] = {"patients": len(bags), "slides": sum(len(v) for v in bags.values())}
        for k in ("mucinous", "pt_stage", "node_positive"):
            summary[name][k] = dict(Counter(str(cases[p]["labels"][k]) for p in bags))
    summary["slide_groups"] = dict(Counter(c["slide_group"] for c in cases.values()))
    summary["idc_patients_without_cbioportal_labels"] = len(set(slides) - set(clin))

    (HERE / "cptac_labels.json").write_text(json.dumps(
        {"note": __doc__.strip().split("\n\n")[-2:], "summary": summary, "problems": problems,
         "selections": sel, "cases": cases}, indent=1))
    print(json.dumps(summary, indent=1))
    print("problems:", problems or "none")


if __name__ == "__main__":
    main()
