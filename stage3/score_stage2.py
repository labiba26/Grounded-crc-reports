"""score_stage2.py - the Stage 2 result tables, recomputed from the saved generations.

Reads stage2/outputs/<run>/<arm>.jsonl (written by stage2/generate.py; *_smoke runs are
skipped unless --smoke) and re-runs the Stage 3 checker on every report, so the scores
always come from the current checker and never from numbers cached at generation time.

Two questions, kept apart (THESIS_LOG.md, Phase 11):

  FAITHFULNESS  does the report say what the generator was GIVEN, and nothing else?
                per field: correct / contradicted / omitted vs the input; fields stated
                without being given; extra claims (margins, LVI, size, node counts...);
                node overclaims (only when node status was NOT given); node abstention.
  CORRECTNESS   is the report right about the patient (vs the labels from the real report)?
                BALANCED per field: the mean over reference classes of the share of
                reports that state the right class ("not stated" counts as wrong). A
                report that always says the common class scores 1/K, not the class
                share - the Stage 1 lesson (accuracy vs balanced accuracy) applied to text.
                Type is scored as mucinous (incl. signet-ring) vs not, as in Stage 1.
                Node is reported separately: arms that abstain on it score 0 by design.

95% CIs: bootstrap over cases (2,000 resamples, seed 2026). Paired differences between
arms use the same resampled cases for both arms.

    python3 stage3/score_stage2.py                 # all non-smoke runs
    python3 stage3/score_stage2.py --smoke         # include smoke runs
Writes stage3/stage2_scores.json.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
sys.path.insert(0, str(HERE))
import consistency as C   # noqa: E402

N_BOOT, SEED = 2000, 2026
VISIBLE = ("histologic_type", "grade", "pt_stage")
FIELDS = VISIBLE + ("node_status",)


def norm(field, v):
    if v is None:
        return None
    if field == "histologic_type":
        return "mucinous" if v in ("mucinous", "signet_ring") else "not mucinous"
    return v


def per_report(row):
    """Everything scored for one report, as plain numbers/labels."""
    text = row["output"] or ""
    chk = C.check(text, row["input_findings"])
    claims = C.extract_claims(text)[0]
    ref = row["reference_findings"]["findings"]
    out = {"case": row["case_id"], "split": row["split"]}
    for f in FIELDS:
        st = chk["fields"][f]["status"]
        out[f"faith_{f}"] = st
        truth = norm(f, None if ref.get(f) is None else ref[f]["value"])
        said = norm(f, claims.get(f))
        out[f"truth_{f}"] = truth
        out[f"said_{f}"] = said
    node_given = row["input_findings"]["findings"].get("node_status") is not None
    out["n_extra"] = len(chk["unsupported_claims"])
    out["extra_kinds"] = sorted(chk["unsupported_claims"])
    out["overclaim"] = int(chk["summary"]["overclaims"] > 0 and not node_given)
    out["node_abstained"] = int(any("lymph node status cannot be assessed" in s.lower()
                                    for s in chk["abstentions"]))
    out["truncated"] = int(row.get("finish_reason") == "length")
    return out


def balanced(reps, f):
    """Balanced correctness for one field over a list of per-report dicts, or None."""
    by = defaultdict(list)
    for r in reps:
        t = r[f"truth_{f}"]
        if t is not None:
            by[t].append(r[f"said_{f}"] == t)
    if not by:
        return None
    return float(np.mean([np.mean(v) for v in by.values()]))


def summarise(reps):
    n = len(reps)
    s = {"n": n}
    for f in FIELDS:
        st = [r[f"faith_{f}"] for r in reps]
        given = [x for x in st if x in ("correct", "contradicted", "omitted")]
        s[f"{f}_given"] = len(given)
        s[f"{f}_faithful"] = (sum(x == "correct" for x in given) / len(given)) if given else None
        s[f"{f}_contradicted"] = sum(x == "contradicted" for x in given)
        s[f"{f}_omitted"] = sum(x == "omitted" for x in given)
        s[f"{f}_stated_not_given"] = sum(x == "unsupported" for x in st)
        s[f"{f}_balanced_correct"] = balanced(reps, f)
        s[f"{f}_n_classes"] = len({r[f"truth_{f}"] for r in reps if r[f"truth_{f}"] is not None})
    vis = [s[f"{f}_balanced_correct"] for f in VISIBLE if s[f"{f}_balanced_correct"] is not None]
    s["visible_balanced_correct"] = float(np.mean(vis)) if vis else None
    s["reports_with_extra_claim"] = sum(r["n_extra"] > 0 for r in reps) / n if n else None
    s["extra_claims_per_report"] = sum(r["n_extra"] for r in reps) / n if n else None
    s["node_overclaim_rate"] = sum(r["overclaim"] for r in reps) / n if n else None
    s["node_abstention_rate"] = sum(r["node_abstained"] for r in reps) / n if n else None
    s["truncated"] = sum(r["truncated"] for r in reps)
    kinds = defaultdict(int)
    for r in reps:
        for k in r["extra_kinds"]:
            kinds[k] += 1
    s["extra_claim_kinds"] = dict(sorted(kinds.items(), key=lambda kv: -kv[1]))
    return s


KEYS_CI = ("visible_balanced_correct", "reports_with_extra_claim")


def boot_ci(reps, key, rng):
    idx = np.arange(len(reps))
    vals = []
    for _ in range(N_BOOT):
        smp = [reps[i] for i in rng.choice(idx, len(idx))]
        v = summarise(smp)[key]
        if v is not None:
            vals.append(v)
    return [float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))] if vals else None


def paired_diff(a, b, key, rng):
    """a, b: per-report lists for two arms on the SAME cases (matched by case id)."""
    A = {r["case"]: r for r in a}
    B = {r["case"]: r for r in b}
    cases = sorted(set(A) & set(B))
    if len(cases) < 5:
        return None
    diffs = []
    for _ in range(N_BOOT):
        smp = rng.choice(cases, len(cases))
        va, vb = summarise([A[c] for c in smp])[key], summarise([B[c] for c in smp])[key]
        if va is not None and vb is not None:
            diffs.append(va - vb)
    point = summarise([A[c] for c in cases])[key] - summarise([B[c] for c in cases])[key]
    return {"n_cases": len(cases), "diff": point,
            "ci95": [float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5))]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--runs", nargs="*", help="run folder names (default: all)")
    a = ap.parse_args()
    root = BASE / "stage2" / "outputs"
    runs = sorted(p for p in root.iterdir() if p.is_dir()) if root.exists() else []
    runs = [p for p in runs if (a.smoke or not p.name.endswith("_smoke"))
            and "_injection" not in p.name          # item 4 runs: scored by score_injection.py
            and "_cot" not in p.name                # chain-of-thought runs: scored by score_cot.py
            and (not a.runs or p.name in a.runs)]
    if not runs:
        sys.exit(f"no runs in {root}")
    rng = np.random.default_rng(SEED)
    result, per = {}, {}
    for run in runs:
        meta = json.loads((run / "meta.json").read_text()) if (run / "meta.json").exists() else {}
        for f in sorted(run.glob("*.jsonl")):
            rows = [json.loads(l) for l in f.read_text().splitlines() if l.strip()]
            reps = [per_report(r) for r in rows]
            for split in sorted({r["split"] for r in reps}):
                sub = [r for r in reps if r["split"] == split]
                key = f"{run.name}/{f.stem}/{split}"
                s = summarise(sub)
                for k in KEYS_CI:
                    s[k + "_ci95"] = boot_ci(sub, k, rng)
                s["model"] = meta.get("model", meta.get("generator"))
                s["git_commit"] = meta.get("git_commit")
                result[key] = s
                per[key] = sub

    # paired contrasts inside each LLM run: the method vs each ungrounded arm
    contrasts = {}
    for key in per:
        run, arm, split = key.split("/")
        if arm != "predicted":
            continue
        for other in ("none", "none_free", "retrieval"):
            k2 = f"{run}/{other}/{split}"
            if k2 in per:
                contrasts[f"{run}/{split}: predicted - {other}"] = {
                    m: paired_diff(per[key], per[k2], m, rng) for m in KEYS_CI}

    (HERE / "stage2_scores.json").write_text(json.dumps(
        {"note": __doc__.split("\n\n")[1:4], "bootstrap": N_BOOT, "seed": SEED,
         "scores": result, "paired_contrasts": contrasts}, indent=1))

    fmt = lambda v: "-" if v is None else f"{v:.2f}"
    print(f"{'run/arm/split':58s} {'n':>4s} {'faith T/G/pT':>14s} {'bal.correct T/G/pT':>19s} "
          f"{'vis.bal [95% CI]':>21s} {'extra-claim rpts':>17s} {'node abst':>9s} {'trunc':>5s}")
    for k, s in result.items():
        ci = s["visible_balanced_correct_ci95"]
        print(f"{k:58s} {s['n']:4d} "
              f"{'/'.join(fmt(s[f + '_faithful']) for f in VISIBLE):>14s} "
              f"{'/'.join(fmt(s[f + '_balanced_correct']) for f in VISIBLE):>19s} "
              f"{fmt(s['visible_balanced_correct']):>6s} [{fmt(ci[0]) if ci else '-'}-{fmt(ci[1]) if ci else '-'}]"
              f"{fmt(s['reports_with_extra_claim']):>12s} {fmt(s['node_abstention_rate']):>9s} {s['truncated']:5d}")
    if contrasts:
        print("\npaired differences (same cases), 95% CI:")
        for k, v in contrasts.items():
            parts = [f"{m}: {d['diff']:+.2f} [{d['ci95'][0]:+.2f}, {d['ci95'][1]:+.2f}]"
                     for m, d in v.items() if d]
            print(f"  {k}\n     " + "   ".join(parts))
    print("\nchance for balanced correctness = 1 / number of classes; faithfulness = share of GIVEN fields stated correctly.")
    print(f"wrote {(HERE / 'stage2_scores.json').relative_to(BASE)}")


if __name__ == "__main__":
    main()
