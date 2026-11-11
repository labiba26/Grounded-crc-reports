"""template_report.py - the deterministic Stage 2 baseline: findings -> report text.

Fully interpretable and the floor every other condition must beat. It states exactly
the fields it is given, words them by visibility, and says nothing else - so under
the consistency checker it should score perfectly, which also makes it the
checker's first sanity test.

Three STYLES exist so the Stage 3 planted-error suite does not tune the checker to
one fixed phrasing.
"""
from __future__ import annotations

GRADE_WORDS = {1: "well differentiated", 2: "moderately differentiated",
               3: "poorly differentiated", 4: "undifferentiated"}
T_WORDS = {1: "invading the submucosa", 2: "invading the muscularis propria",
           3: "invading through the muscularis propria into pericolorectal tissue",
           4: "penetrating the visceral peritoneum or adjacent organs"}
TYPE_WORDS = {"adenocarcinoma": "adenocarcinoma", "mucinous": "mucinous adenocarcinoma",
              "signet_ring": "signet-ring cell carcinoma"}


def _conf(f):
    p = f.get("prob")
    return "" if p is None else f" (model confidence {p:.0%})"


def render(fs: dict, style: int = 0) -> str:
    f = fs["findings"]
    t, g, pt, n = (f.get(k) for k in ("histologic_type", "grade", "pt_stage", "node_status"))
    inferred = fs.get("source") == "predicted"
    out = []

    if style == 0:            # synoptic
        if t: out.append(f"Histologic type: {TYPE_WORDS[t['value']]}{_conf(t)}.")
        if g: out.append(f"Histologic grade: G{g['value']}, {GRADE_WORDS[g['value']]}{_conf(g)}.")
        if pt: out.append(f"Depth of invasion: pT{pt['value']}, {T_WORDS[pt['value']]}{_conf(pt)}. "
                          f"The deepest point of invasion may not be represented on the examined slide.")
        if n: out.append(f"Lymph nodes: no lymph node tissue was examined. Nodal status is estimated "
                         f"from the primary tumour as {'positive' if n['value'] else 'negative'}{_conf(n)}.")
    elif style == 1:          # prose
        s = []
        if t or g:
            desc = " ".join(x for x in [GRADE_WORDS[g["value"]] if g else "",
                                        TYPE_WORDS[t["value"]] if t else "carcinoma"] if x)
            s.append(f"The slide shows a {desc}" + (f" (G{g['value']})" if g else "") + ".")
        if pt: s.append(f"The tumour is staged pT{pt['value']}, {T_WORDS[pt['value']]}, although the "
                        f"deepest invasion may lie outside the examined section.")
        if n: s.append(f"No lymph nodes are present on the slide; the model's estimate of nodal status is "
                       f"{'node-positive' if n['value'] else 'node-negative'}{_conf(n)}.")
        out = s
    else:                     # terse, coded
        parts = []
        if t: parts.append(TYPE_WORDS[t["value"]].capitalize())
        if g: parts.append(f"G{g['value']}")
        if pt: parts.append(f"pT{pt['value']} (estimated)")
        out.append(", ".join(parts) + "." if parts else "")
        if n: out.append(f"Nodal status (inferred, not observed): {'positive' if n['value'] else 'negative'}.")

    if fs.get("node_policy") == "abstain":
        from findings import NODE_ABSTAIN_TEXT
        out.append(NODE_ABSTAIN_TEXT)
    header = ("Model-generated report from predicted findings." if inferred
              else "Report generated from supplied findings.")
    body = " ".join(x for x in out if x)
    return f"{header} {body}".strip() if body else header


if __name__ == "__main__":
    import json, sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import findings as F
    L = json.loads((Path(__file__).resolve().parent.parent / "stage1" / "structured_labels.json").read_text())
    fs = F.from_labels(L["TCGA-AA-3949"]["labels"])
    for st in range(3):
        print(f"--- style {st}\n{render(fs, st)}\n")
    pred = {"mucinous": {"value": False, "prob": 0.91}, "grade": {"value": 3, "prob": 0.55},
            "pt_stage": {"value": 3, "prob": 0.62}, "node_positive": {"value": True, "prob": 0.58}}
    print("--- predicted, style 0\n" + render(F.from_predictions(pred), 0))
