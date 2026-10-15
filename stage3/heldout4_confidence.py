"""heldout4_confidence.py - a FOURTH frozen held-out set: confidence percentages near "mucinous".

Why it exists: the error-injection sanity check (29 Sep, improvement item 4) found that checker v1.2
reads "mucinous adenocarcinoma (model confidence 40%)" as NOT mucinous. The type rule borrowed from
the label extractor treats any percentage <= 50 within 60 characters as the mucin share (WHO: >50%
mucin), so a model confidence below 50% flips the reading.

Sentences and expected answers written BEFORE any fix, including controls where a real mucin
percentage must still decide the type. The SHA-256 of this file is recorded in THESIS_LOG.md before
the fix. Run once; record as-is; do not edit to pass.
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import consistency as C   # noqa: E402

TYPE = [   # (sentence, expected histologic type claim)
    # traps: a confidence or probability, not a mucin share
    ("Mucinous adenocarcinoma (model confidence 40%).", "mucinous"),
    ("Histologic type: mucinous adenocarcinoma (model confidence 45%), although this is uncertain.", "mucinous"),
    ("The tumour is a mucinous adenocarcinoma; model confidence is 38%, so this is uncertain.", "mucinous"),
    ("Mucinous adenocarcinoma, moderately differentiated (confidence 30%).", "mucinous"),
    ("Moderately differentiated (model confidence 45%) mucinous adenocarcinoma.", "mucinous"),
    ("Mucinous adenocarcinoma, with a probability of 42%.", "mucinous"),
    ("Mucinous adenocarcinoma (40% confidence).", "mucinous"),
    ("Mucinous adenocarcinoma, grade 2 (model confidence 20%), invading the muscularis propria (pT2).", "mucinous"),
    # controls: a real mucin share still decides; plain cases unchanged
    ("Adenocarcinoma with a mucinous component (30%).", "adenocarcinoma"),
    ("Mucinous adenocarcinoma (mucin 30% of tumour).", "adenocarcinoma"),
    ("Mucinous adenocarcinoma, extracellular mucin 80%.", "mucinous"),
    ("Adenocarcinoma, not of mucinous type (model confidence 91%).", "adenocarcinoma"),
    ("Adenocarcinoma (model confidence 85%).", "adenocarcinoma"),
    ("Mucinous adenocarcinoma (model confidence 75%).", "mucinous"),
]


def main():
    rows = []
    for text, want in TYPE:
        got = C.extract_claims(text)[0]["histologic_type"]
        rows.append({"text": text, "expected": want, "got": got, "pass": got == want})
    ok = sum(r["pass"] for r in rows)
    for r in rows:
        print(f"{'PASS' if r['pass'] else 'FAIL'}  expected {r['expected']:14s} got {str(r['got']):14s}  {r['text']}")
    print(f"\n{ok}/{len(rows)} correct (checker {getattr(C, 'VERSION', '?')})")
    out = HERE / "heldout4_results.json"
    prev = json.loads(out.read_text()) if out.exists() else {}
    prev[str(getattr(C, "VERSION", "?"))] = {"n": len(rows), "correct": ok, "rows": rows}
    out.write_text(json.dumps(prev, indent=1))


if __name__ == "__main__":
    main()
