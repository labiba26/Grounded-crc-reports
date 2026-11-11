"""findings.py - the input contract shared by every Stage 2 generator and the Stage 3 checker.

A generator receives a FindingSet: the four Stage 1 fields, each with a value and
(for predictions) a probability. Every condition uses the same structure, so the only
thing that changes between conditions is what is inside it:

  source="predicted"  Stage 1's predictions                     (the method)
  source="extracted"  the weak labels from the real report       (upper bound)
  source="none"       no findings at all                         (ungrounded baseline)

VISIBILITY (THESIS_LOG.md, Phase 12): 599 of 600 slides are primary tumour, so each
field is tagged by whether the slide can show it. A generator must word a
not-visible field as an inference, and the checker flags it when stated as observed.
"""
from __future__ import annotations

FIELDS = ("histologic_type", "grade", "pt_stage", "node_status")

VISIBILITY = {
    "histologic_type": "visible",          # tumour morphology is on the slide
    "grade": "visible",
    "pt_stage": "partly visible",          # the deepest point may not be on the slide
    "node_status": "not visible",          # lymph nodes are on other slides
}

# canonical values - the checker compares against these
VALUES = {
    "histologic_type": ("adenocarcinoma", "mucinous", "signet_ring"),
    "grade": (1, 2, 3, 4),
    "pt_stage": (1, 2, 3, 4),
    "node_status": (True, False),
}


def from_labels(labels: dict) -> dict:
    """FindingSet from structured_labels.json-style labels (the 'extracted' arm)."""
    return {"source": "extracted", "findings": {
        "histologic_type": _f(labels.get("histologic_type")),
        "grade": _f(labels.get("histologic_grade")),
        "pt_stage": _f(labels.get("pt_stage")),
        "node_status": _f(labels.get("lymph_node_positive")),
    }}


def from_predictions(pred: dict) -> dict:
    """FindingSet from a Stage 1 prediction record:
    {"mucinous": {"value": bool, "prob": p}, "grade": {...}, "pt_stage": {...},
     "node_positive": {...}}"""
    m = pred["mucinous"]
    return {"source": "predicted", "findings": {
        "histologic_type": {"value": "mucinous" if m["value"] else "adenocarcinoma",
                            "prob": m["prob"]},
        "grade": dict(pred["grade"]),
        "pt_stage": dict(pred["pt_stage"]),
        "node_status": dict(pred["node_positive"]),
    }}


def empty() -> dict:
    return {"source": "none", "findings": {k: None for k in FIELDS}}


def _f(v):
    return None if v is None else {"value": v, "prob": None}

# Node status policy (decided 26 Sep, THESIS_LOG.md CPTAC results): Stage 1's node prediction
# is at chance externally (AUROC 0.45) and the slides hold no lymph nodes, so reports built
# from PREDICTED findings abstain on node status. The extracted arm keeps it (it comes from
# the real report). Applied in Stage 2 only - the Stage 3 validation suites are unchanged.
NODE_ABSTAIN_TEXT = ("Lymph node status cannot be assessed from the submitted tissue, "
                     "which contains the primary tumour only.")


def abstain_node(fs: dict) -> dict:
    """Copy of a FindingSet with node status removed and the abstention policy set."""
    import copy
    out = copy.deepcopy(fs)
    out["findings"]["node_status"] = None
    out["node_policy"] = "abstain"
    return out
