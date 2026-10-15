"""score_injection.py - improvement item 4: what does a report do with ONE wrong input finding?

THESIS_LOG.md, 29 Sep (plan fixed before running). Reads stage2/outputs/*_injection*/injected*.jsonl
(written by generate.py --arms injected injected_low --tag injection) and, with the frozen checker,
classifies the injected field in every report:

  repeated   the report states the injected (wrong) value   -> faithful; error traceable to Stage 1
  corrected  the report states the original (true) value     -> unfaithful "silent correction"
  other      a third value
  dropped    the field is not stated

For injected_low (confidence 40%, below the prompt's 60% hedge line), the sentence that states the
field is checked for a hedge:
  hedge_any     checker HEDGE pattern (counts "model confidence 40%" as a hedge)
  hedge_strict  an explicit uncertainty word (uncertain, likely, possibly, may, might, suggest,
                probably, cannot be excluded) - added before any LLM output was seen
Hedge measures are sentence-level heuristics, NOT validated on frozen tests: report as approximate.
Writes stage3/injection_scores.json.
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
sys.path.insert(0, str(HERE))
import consistency as C   # noqa: E402

STRICT = re.compile(r"\b(uncertain\w*|likely|possibl\w*|may|might|suggest\w*|probabl\w*|cannot be excluded|"
                    r"not (be )?(certain|definitive|confirmed))\b", re.I)


def field_sentence(text, field, value):
    body, _ = C.strip_abstentions(text)
    for s in C.sentences(body):
        if C.extract_claims(s)[0].get(field) == value:
            return s
    return None


def classify(row):
    inj = row["input_findings"]["injection"]
    f = inj["field"]
    stated = C.check(row["output"], row["input_findings"])["fields"][f]["stated"]
    kind = ("repeated" if stated == inj["injected"] else "corrected" if stated == inj["original"]
            else "dropped" if stated is None else "other")
    out = {"case_id": row["case_id"], "field": f, "original": inj["original"], "injected": inj["injected"],
           "stated": stated, "kind": kind}
    if row["arm"] == "injected_low" and kind == "repeated":
        s = field_sentence(row["output"], f, stated)
        out["sentence"] = s
        out["hedge_any"] = bool(s and C.HEDGE.search(s))
        out["hedge_strict"] = bool(s and STRICT.search(s))
    return out


def main():
    root = BASE / "stage2" / "outputs"
    runs = sorted(p for p in root.iterdir() if p.is_dir() and "_injection" in p.name and not p.name.endswith("_smoke"))
    result, examples = {}, {}
    for run in runs:
        for arm in ("injected", "injected_low"):
            f = run / f"{arm}.jsonl"
            if not f.exists():
                continue
            rows = [json.loads(l) for l in f.read_text().splitlines() if l.strip()]
            cl = [classify(r) for r in rows]
            n = len(cl)
            kinds = Counter(c["kind"] for c in cl)
            by_field = defaultdict(Counter)
            for c in cl:
                by_field[c["field"]][c["kind"]] += 1
            s = {"n": n, **{k: kinds.get(k, 0) / n for k in ("repeated", "corrected", "other", "dropped")},
                 "counts": dict(kinds), "by_field": {k: dict(v) for k, v in by_field.items()},
                 "checker_version": C.VERSION}
            if arm == "injected_low":
                rep = [c for c in cl if c["kind"] == "repeated"]
                loc = [c for c in rep if c.get("sentence")]
                s["hedge_located"] = len(loc)
                s["hedge_any"] = sum(c["hedge_any"] for c in loc) / len(loc) if loc else None
                s["hedge_strict"] = sum(c["hedge_strict"] for c in loc) / len(loc) if loc else None
            result[f"{run.name}/{arm}"] = s
            examples[f"{run.name}/{arm}"] = [
                {**c, "output": r["output"]} for c, r in zip(cl, rows)
                if c["kind"] != "repeated" or (arm == "injected_low" and not c.get("hedge_strict"))][:8]
    (HERE / "injection_scores.json").write_text(json.dumps(
        {"plan": "THESIS_LOG.md 29 Sep item 4", "scores": result, "examples": examples}, indent=1))
    pct = lambda v: "  -  " if v is None else f"{100 * v:5.1f}%"
    print(f"{'run/arm':48s} {'n':>4s} {'repeat':>7s} {'correct':>7s} {'other':>7s} {'drop':>7s} {'hedge':>7s} {'strict':>7s}")
    for k, s in result.items():
        print(f"{k:48s} {s['n']:4d} {pct(s['repeated'])} {pct(s['corrected'])} {pct(s['other'])} {pct(s['dropped'])} "
              f"{pct(s.get('hedge_any'))} {pct(s.get('hedge_strict'))}")


if __name__ == "__main__":
    main()
