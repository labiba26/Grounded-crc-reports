"""score_fluency.py - do standard text-overlap metrics tell faithful reports from invented ones?

THESIS_LOG.md, 29 Sep improvement plan, item 1. For every generated TCGA report, BLEU-4 and
ROUGE-1/2/L are computed against the patient's REAL report (the usual protocol in report-generation
papers), then compared with what the Stage 3 checker says about the same reports.

Question asked: if a paper reported only BLEU/ROUGE, would it prefer the grounded report (states
what it was given, invents nothing) over the invented one? And does a metric rise with the number
of fields a report gets right?

Metrics (own implementation, no external library; tokens = lowercase alphanumeric words):
  BLEU-4        sentence BLEU, add-one smoothing on n-gram precisions, standard brevity penalty
  BLEU-4 P      the same WITHOUT the brevity penalty (generated reports are ~20x shorter than real ones)
  ROUGE-1/2/L   F1; ROUGE-L also reported as precision and recall
Reference = the real report text, unedited (OCR noise included); TCGA cases only (CPTAC has no reports).

95% CIs: bootstrap over cases, 2,000 resamples, seed 2026. Paired differences use the same cases.
Writes stage3/fluency_scores.json. Run:  python3 stage3/score_fluency.py
"""
from __future__ import annotations

import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
sys.path.insert(0, str(HERE))
import consistency as C   # noqa: E402

N_BOOT, SEED = 2000, 2026
TOK = re.compile(r"[a-z0-9]+")
INDEX = {c["case_id"]: c for c in json.loads((BASE / "dataset_manifests_final" / "dataset_index.json").read_text())}
_REF = {}


def toks(s):
    return TOK.findall(s.lower())


def ref_tokens(cid):
    if cid not in _REF:
        text = "\n".join((BASE / p).read_text(errors="ignore") for p in INDEX[cid]["reports"])
        _REF[cid] = toks(text)
    return _REF[cid]


def ngrams(t, n):
    return Counter(tuple(t[i:i + n]) for i in range(len(t) - n + 1))


def bleu4(hyp, ref):
    """Returns (BLEU-4 with brevity penalty, BLEU-4 without it)."""
    if not hyp:
        return 0.0, 0.0
    logs = 0.0
    for n in range(1, 5):
        h, r = ngrams(hyp, n), ngrams(ref, n)
        tot = max(sum(h.values()), 0)
        match = sum(min(c, r[g]) for g, c in h.items())
        logs += math.log((match + 1) / (tot + 1))       # add-one smoothing (Lin & Och)
    p = math.exp(logs / 4)
    bp = 1.0 if len(hyp) >= len(ref) else math.exp(1 - len(ref) / len(hyp))
    return p * bp, p


def lcs(a, b):
    if not a or not b:
        return 0
    prev = [0] * (len(b) + 1)
    for x in a:
        cur = [0]
        for j, y in enumerate(b, 1):
            cur.append(prev[j - 1] + 1 if x == y else max(prev[j], cur[j - 1]))
        prev = cur
    return prev[-1]


def f1(p, r):
    return 0.0 if p + r == 0 else 2 * p * r / (p + r)


def rouge_n(hyp, ref, n):
    h, r = ngrams(hyp, n), ngrams(ref, n)
    m = sum(min(c, r[g]) for g, c in h.items())
    p = m / max(sum(h.values()), 1)
    rc = m / max(sum(r.values()), 1)
    return f1(p, rc)


def score_pair(hyp_text, cid):
    hyp, ref = toks(hyp_text), ref_tokens(cid)
    b, bnp = bleu4(hyp, ref)
    l = lcs(hyp, ref)
    lp, lr = l / max(len(hyp), 1), l / max(len(ref), 1)
    return {"bleu4": b, "bleu4_p": bnp, "rouge1": rouge_n(hyp, ref, 1), "rouge2": rouge_n(hyp, ref, 2),
            "rougeL": f1(lp, lr), "rougeL_p": lp, "rougeL_r": lr, "len": len(hyp)}


METRICS = ["bleu4", "bleu4_p", "rouge1", "rouge2", "rougeL", "rougeL_p", "rougeL_r"]


def rank(v):
    order = np.argsort(v, kind="stable")
    r = np.empty(len(v)); r[order] = np.arange(len(v))
    for val in np.unique(v):                    # average ranks for ties
        m = v == val
        r[m] = r[m].mean()
    return r


def spearman(x, y):
    x, y = np.asarray(x, float), np.asarray(y, float)
    if x.std() == 0 or y.std() == 0:
        return None
    return float(np.corrcoef(rank(x), rank(y))[0, 1])


def main():
    root = BASE / "stage2" / "outputs"
    runs = [p for p in sorted(root.iterdir()) if p.is_dir() and "tcga" in p.name and not p.name.endswith("_smoke")]
    rows = defaultdict(list)          # (run, arm) -> per-report dicts
    for run in runs:
        for f in sorted(run.glob("*.jsonl")):
            for line in f.read_text().splitlines():
                r = json.loads(line)
                if r["split"] not in ("test_coad", "holdout_read"):
                    continue
                chk = C.check(r["output"], r["input_findings"])
                ref = C.against_reference(r["output"], r["reference_findings"])
                n_ok = sum(v == "correct" for k, v in ref["fields"].items() if k != "node_status")
                m = score_pair(r["output"], r["case_id"])
                m.update({"case": r["case_id"], "split": r["split"], "n_extra": len(chk["unsupported_claims"]),
                          "n_correct_fields": n_ok, "invented": int(len(chk["unsupported_claims"]) > 0)})
                rows[(run.name, f.stem)].append(m)
        print("scored", run.name, flush=True)

    rng = np.random.default_rng(SEED)
    summary, boots = {}, {}
    for key, reps in rows.items():
        s = {"n": len(reps), "invented_share": float(np.mean([r["invented"] for r in reps])),
             "mean_correct_fields": float(np.mean([r["n_correct_fields"] for r in reps])),
             "mean_words": float(np.mean([r["len"] for r in reps]))}
        arr = {m: np.array([r[m] for r in reps]) for m in METRICS}
        idx = rng.integers(0, len(reps), (N_BOOT, len(reps)))
        for m in METRICS:
            s[m] = float(arr[m].mean())
            b = arr[m][idx].mean(1)
            s[m + "_ci95"] = [float(np.percentile(b, 2.5)), float(np.percentile(b, 97.5))]
        summary["/".join(key)] = s

    # paired contrasts inside each LLM run: predicted vs each other arm, same cases
    contrasts = {}
    for (run, arm), reps in rows.items():
        if arm not in ("predicted", "extracted"):
            continue
        A = {r["case"]: r for r in reps}
        others = [(run, o) for o in ("none", "none_free", "retrieval", "predicted", "extracted") if o != arm]
        others.append(("copy_tcga", "retrieval"))          # the neighbour's real report, copied verbatim
        for orun, other in others:
            if (orun, other) not in rows or (arm == "extracted" and other == "predicted"):
                continue
            B = {r["case"]: r for r in rows[(orun, other)]}
            cases = sorted(set(A) & set(B))
            out = {}
            for m in METRICS:
                d = np.array([A[c][m] - B[c][m] for c in cases])
                idx = rng.integers(0, len(cases), (N_BOOT, len(cases)))
                bs = d[idx].mean(1)
                out[m] = {"diff": float(d.mean()), "ci95": [float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))]}
            contrasts[f"{run}: {arm} - " + (other if orun == run else "COPIED neighbour report")] = out

    # does each metric rise with correctness? pooled over every report of a model run
    corr = {}
    for run in {k[0] for k in rows}:
        pool = [r for (rn, arm), reps in rows.items() if rn == run for r in reps]
        if len(pool) < 100:
            continue
        corr[run] = {m: {"spearman_with_correct_fields": spearman([r[m] for r in pool], [r["n_correct_fields"] for r in pool]),
                         "spearman_with_invented": spearman([r[m] for r in pool], [r["invented"] for r in pool])}
                     for m in ["bleu4_p", "rouge1", "rougeL", "rougeL_p"]}

    (HERE / "fluency_scores.json").write_text(json.dumps(
        {"protocol": __doc__.strip().split("\n\n")[1:3], "bootstrap": N_BOOT, "seed": SEED,
         "summary": summary, "paired_contrasts": contrasts, "spearman": corr}, indent=1))

    f = lambda v: f"{v:.3f}"
    print(f"\n{'run/arm':52s} {'n':>4s} {'words':>6s} {'BLEU4':>6s} {'BLEU4-P':>7s} {'R-1':>6s} {'R-2':>6s} {'R-L':>6s} {'R-L P':>6s} {'R-L R':>6s} | {'invented':>8s} {'correct fields':>14s}")
    for k, s in summary.items():
        print(f"{k:52s} {s['n']:4d} {s['mean_words']:6.0f} {f(s['bleu4']):>6s} {f(s['bleu4_p']):>7s} {f(s['rouge1']):>6s} {f(s['rouge2']):>6s} {f(s['rougeL']):>6s} {f(s['rougeL_p']):>6s} {f(s['rougeL_r']):>6s} | {s['invented_share']:8.2f} {s['mean_correct_fields']:14.2f}")
    print("\nSpearman: metric vs number of correct fields / vs 'contains invented claims' (pooled per model)")
    for run, d in corr.items():
        print(run, {m: (None if v['spearman_with_correct_fields'] is None else round(v['spearman_with_correct_fields'], 2),
                        None if v['spearman_with_invented'] is None else round(v['spearman_with_invented'], 2)) for m, v in d.items()})
    print("\nwrote stage3/fluency_scores.json")


if __name__ == "__main__":
    main()
