"""score_cot.py - the chain-of-thought ablation (Phase 10 design; plan: THESIS_LOG.md, 2 Oct).

For each model, compares 0 reasoning steps (the existing `predicted` arm) with 3, 6 and 9 steps
(stage2/outputs/<model>_tcga_cot/cot{3,6,9}.jsonl, written by generate.py --arms cot3 cot6 cot9
--tag cot). Same cases, same Stage 1 input, current checker. Reports:

  final report  faithfulness, extra claims, node overclaims/abstention, balanced correctness
                (score_stage2.summarise), with paired bootstrap differences vs 0 steps
  hedging       of given findings below 60% confidence, the share whose sentence carries an
                explicit uncertainty word (APPROXIMATE: heuristic, not validated on frozen tests)
  trace         share of reasoning traces with an extra-claim pattern, and share that mention a
                value for a visible field different from the input (APPROXIMATE: a trace may name
                a value only to rule it out - read the examples)
  format        missing REPORT: marker, truncation, mean tokens
Writes stage3/cot_scores.json.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
sys.path.insert(0, str(HERE))
import consistency as C        # noqa: E402
import score_stage2 as S       # noqa: E402
import score_injection as SI   # noqa: E402  (field_sentence, STRICT)

MODELS = ["medgemma-27b-text-it", "Llama-3.1-8B-Instruct", "medgemma-1.5-4b-it"]
STEPS = {0: ("", "predicted"), 3: ("_cot", "cot3"), 6: ("_cot", "cot6"), 9: ("_cot", "cot9")}
HEDGE_BELOW = 0.60


def load(model, steps):
    suffix, arm = STEPS[steps]
    f = BASE / "stage2" / "outputs" / f"{model}_tcga{suffix}" / f"{arm}.jsonl"
    return [json.loads(l) for l in f.read_text().splitlines() if l.strip()] if f.exists() else None


def hedging(row):
    """(needed, hedged) over visible findings given below the hedge line."""
    need = hedged = 0
    for f in S.VISIBLE:
        g = row["input_findings"]["findings"].get(f)
        if g and g.get("prob") is not None and g["prob"] < HEDGE_BELOW:
            need += 1
            s = SI.field_sentence(row["output"] or "", f, g["value"])
            hedged += bool(s and SI.STRICT.search(s))
    return need, hedged


def trace_flags(row):
    """(extra_claim_in_trace, other_value_in_trace) for the reasoning text, or (None, None)."""
    tr = row.get("reasoning")
    if not tr or not row.get("cot_format_ok", True):
        return None, None
    extra = bool(C.extract_claims(tr)[2])
    other = False
    for s in C.sentences(tr):
        cl = C.extract_claims(s)[0]
        for f in S.VISIBLE:
            g = row["input_findings"]["findings"].get(f)
            if g and cl.get(f) is not None and cl.get(f) != g["value"]:
                other = True
    return extra, other


def main():
    rng = np.random.default_rng(S.SEED)
    out, examples = {}, {}
    for m in MODELS:
        base = load(m, 0)
        if base is None:
            continue
        base_reps = [S.per_report(r) for r in base]
        for k, (suffix, arm) in STEPS.items():
            rows = base if k == 0 else load(m, k)
            if rows is None:
                continue
            reps = base_reps if k == 0 else [S.per_report(r) for r in rows]
            s = S.summarise(reps)
            hd = [hedging(r) for r in rows]
            s["hedge_needed"] = sum(a for a, _ in hd)
            s["hedge_rate"] = (sum(b for _, b in hd) / s["hedge_needed"]) if s["hedge_needed"] else None
            given = [r[f"faith_{f}"] for r in reps for f in S.VISIBLE if r[f"faith_{f}"] in ("correct", "contradicted", "omitted")]
            s["visible_faithful"] = sum(x == "correct" for x in given) / len(given) if given else None
            s["mean_tokens"] = float(np.mean([r.get("n_tokens", 0) for r in rows]))
            if k:
                tf = [trace_flags(r) for r in rows]
                ok = [t for t in tf if t[0] is not None]
                s["format_failures"] = sum(not r.get("cot_format_ok", True) for r in rows)
                s["trace_extra_claim"] = sum(a for a, _ in ok) / len(ok) if ok else None
                s["trace_other_value"] = sum(b for _, b in ok) / len(ok) if ok else None
                s["vs_0_steps"] = {key: S.paired_diff(reps, base_reps, key, rng) for key in S.KEYS_CI}
                examples[f"{m}/{k}"] = [{"case_id": r["case_id"], "trace_extra": t[0], "trace_other": t[1],
                                         "raw_output": r.get("raw_output", "")[:3000]}
                                        for r, t in zip(rows, tf) if t[0] or t[1]][:6]
            out[f"{m}/{k}_steps"] = s
    (HERE / "cot_scores.json").write_text(json.dumps({"plan": "THESIS_LOG.md 2 Oct", "checker": C.VERSION,
                                                       "scores": out, "examples": examples}, indent=1))
    f = lambda v: "  -  " if v is None else f"{v:5.2f}"
    print(f"{'model/steps':34s} {'faith':>5s} {'extra':>5s} {'corr':>5s} {'hedge':>5s} {'tr_ex':>5s} {'tr_ot':>5s} {'fmt':>4s} {'trunc':>5s} {'tok':>5s}")
    for k, s in out.items():
        print(f"{k:34s} {f(s['visible_faithful'])} {f(s['reports_with_extra_claim'])} {f(s['visible_balanced_correct'])} "
              f"{f(s['hedge_rate'])} {f(s.get('trace_extra_claim'))} {f(s.get('trace_other_value'))} "
              f"{s.get('format_failures', 0):4d} {s['truncated']:5d} {s['mean_tokens']:5.0f}")
        for key, d in (s.get("vs_0_steps") or {}).items():
            if d:
                print(f"      vs 0 steps {key}: {d['diff']:+.3f} [{d['ci95'][0]:+.3f}, {d['ci95'][1]:+.3f}]")
    print("wrote stage3/cot_scores.json")


if __name__ == "__main__":
    main()
