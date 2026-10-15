"""heldout_check.py - a FROZEN held-out test of the consistency checker.

Twelve reports in free, LLM-like phrasing, written 24 Sep 2026 AFTER the checker was
tuned on planted_errors.py, with the verdict a careful human reader would give.
Run once and recorded as-is (THESIS_LOG.md, Phase 12). DO NOT edit the checker to make
these pass and then quote the result - that would turn a held-out test into a
training set. New failure modes go into a NEW held-out set.

All twelve are checked against the same input: adenocarcinoma, G2, pT3, node-negative
(predicted). "expect" gives the verdict for each field, the unsupported claims, and
whether node status is overclaimed.

    python3 heldout_check.py        # writes heldout_results.json
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent / "stage2"))
import consistency as C      # noqa: E402

FS = {"source": "predicted", "findings": {
    "histologic_type": {"value": "adenocarcinoma", "prob": 0.9},
    "grade": {"value": 2, "prob": 0.6}, "pt_stage": {"value": 3, "prob": 0.6},
    "node_status": {"value": False, "prob": 0.6}}}
OK = {"histologic_type": "correct", "grade": "correct", "pt_stage": "correct", "node_status": "correct"}


def E(fields=None, unsupported=(), overclaim=False):
    return {"fields": {**OK, **(fields or {})}, "unsupported": sorted(unsupported), "overclaim": overclaim}


CASES = [
    ("Sections show a moderately differentiated adenocarcinoma infiltrating through the muscularis "
     "propria into the subserosal fat (pT3). Based on the model, regional lymph node involvement is "
     "considered unlikely.", E()),
    ("Final diagnosis: Colon, resection - invasive adenocarcinoma, intermediate grade (G2), pT3. "
     "Nodes: negative (0/12). Margins: negative.", E(unsupported=["node_count", "margins"], overclaim=True)),
    ("The tumour is a well-to-moderately differentiated adenocarcinoma, pT3, with no lymph node "
     "metastases identified.", E(overclaim=True)),
    ("Moderately differentiated adenocarcinoma of the rectum invading perirectal fat (pT3), with "
     "lymphovascular invasion and 2 of 18 lymph nodes positive (pN1a). Circumferential margin clear. "
     "MMR proficient.",
     E({"node_status": "contradicted"}, ["lymphovascular_invasion", "node_count", "pn_category",
                                         "margins", "msi_mmr", "tumour_site"], overclaim=True)),
    ("Adenocarcinoma, G2, pT3. Lymph nodes were not submitted; nodal status cannot be assessed.",
     E({"node_status": "omitted"})),
    ("Low-grade adenocarcinoma, pT3, estimated node-negative.", E({"grade": "omitted"})),
    ("Invasive carcinoma with mucinous features (approximately 30%), moderately differentiated, pT3; "
     "the predicted nodal status is negative.", E()),
    ("Moderately differentiated adenocarcinoma, pT3 N0 (predicted).", E()),
    ("Adenocarcinoma, grade 2 of 3, pT3. Model estimate: node negative.", E()),
    ("Adenocarcinoma (moderately differentiated). Tumour invades through the muscularis propria into "
     "pericolorectal tissues. Nodal status: likely negative.", E()),
    ("Adenocarcinoma, G2, pT3. The model predicts node-negative status; however, extramural venous "
     "invasion is present.", E(unsupported=["lymphovascular_invasion"])),
    ("Adenocarcinoma, G2, pT3, estimated N-negative. Tumour deposits are absent.",
     E(unsupported=["tumour_deposits"])),
]


def main():
    out, n_items, n_ok = [], 0, 0
    for i, (text, exp) in enumerate(CASES, 1):
        r = C.check(text, FS)
        got = {"fields": {k: v["status"] for k, v in r["fields"].items()},
               "unsupported": sorted(r["unsupported_claims"]),
               "overclaim": r["fields"]["node_status"]["overclaim"]}
        items = ([(f"field {k}", got["fields"][k], exp["fields"][k]) for k in exp["fields"]] +
                 [("unsupported", got["unsupported"], exp["unsupported"]),
                  ("overclaim", got["overclaim"], exp["overclaim"])])
        wrong = [(k, g, e) for k, g, e in items if g != e]
        n_items += len(items); n_ok += len(items) - len(wrong)
        print(f"H{i:02d} {'OK ' if not wrong else 'ERR'} {text[:70]}...")
        for k, g, e in wrong:
            print(f"      {k}: checker {g!r}, human {e!r}")
        out.append({"id": f"H{i:02d}", "text": text, "expected": exp, "got": got,
                    "disagreements": [{"item": k, "checker": g, "human": e} for k, g, e in wrong]})
    n_full = sum(not o["disagreements"] for o in out)
    print(f"\n{n_full}/{len(CASES)} reports fully right; {n_ok}/{n_items} individual verdicts right "
          f"({n_ok / n_items:.1%})")
    (HERE / "heldout_results.json").write_text(json.dumps(
        {"reports_fully_right": n_full, "n_reports": len(CASES), "verdicts_right": n_ok,
         "n_verdicts": n_items, "cases": out}, indent=1))


if __name__ == "__main__":
    main()
