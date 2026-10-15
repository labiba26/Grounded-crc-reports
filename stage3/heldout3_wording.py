"""heldout3_wording.py - a THIRD frozen held-out set: grade and margins in other word forms.

Why it exists: scoring the secondary LLMs (29 Sep) showed MedGemma 1.5 4B writes grade as a noun
("adenocarcinoma with moderate differentiation") and margins verb-first ("the tumour involves the
lateral margin"). Checker v1.1 reads neither, so the 4B looked as if it omitted the grade in about
half its reports (112 of 243 predicted-arm reports) - a checker gap, not a model error.

Sentences and expected answers written BEFORE any fix (WHO grading words; CAP margin wording),
including traps. The SHA-256 of this file is recorded in THESIS_LOG.md before the fix.
Run once; record as-is; do not edit to pass.
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import consistency as C   # noqa: E402

GRADE = [   # (sentence, expected grade)
    ("Adenocarcinoma with moderate differentiation.", 2),
    ("The carcinoma shows poor differentiation.", 3),
    ("Invasive adenocarcinoma with good differentiation.", 1),
    ("Adenocarcinoma, moderately differentiated.", 2),
    ("The tumour is well-differentiated.", 1),
    ("Poorly-differentiated adenocarcinoma.", 3),
    ("Differentiation: moderate.", 2),
    ("There is no poorly differentiated component.", None),
    ("Invasive adenocarcinoma.", None),
    ("Moderate lymphocytic infiltration is seen.", None),
]
MARGINS = [   # (sentence, margins claimed?)
    ("The tumour involves the lateral margin.", True),
    ("Tumour extends to the radial resection margin.", True),
    ("Carcinoma reaches the circumferential margin.", True),
    ("The margins are free of tumour.", True),
    ("The tumour does not involve the distal margin.", True),
    ("Margins cannot be assessed.", False),
    ("The tumour invades the muscularis propria.", False),
    ("Lymph nodes are negative.", False),
]


def main():
    rows, ok, n = [], 0, 0
    for text, want in GRADE:
        got = C.extract_claims(text)[0]["grade"]
        rows.append({"kind": "grade", "text": text, "expected": want, "got": got, "pass": got == want})
    for text, want in MARGINS:
        got = "margins" in C.extract_claims(text)[2]
        rows.append({"kind": "margins", "text": text, "expected": want, "got": got, "pass": got == want})
    for r in rows:
        ok += r["pass"]; n += 1
        print(f"{'PASS' if r['pass'] else 'FAIL'}  {r['kind']:8s} expected {r['expected']!s:5s} got {r['got']!s:5s}  {r['text']}")
    print(f"\n{ok}/{n} correct")
    (HERE / "heldout3_results.json").write_text(json.dumps({"n": n, "correct": ok, "rows": rows}, indent=1))


if __name__ == "__main__":
    main()
