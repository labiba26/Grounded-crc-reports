"""heldout2_depth.py - a SECOND frozen held-out test: depth of invasion written in words.

Why it exists: the first full Stage 2 run (26 Sep) showed the checker reads pT only as a
code ("pT3"). Ungrounded reports describe depth in words ("invades through the muscularis
propria into the pericolic fat"), so their pT was read as "not stated" - a checker gap that
would bias the comparison in favour of the grounded arm.

These 15 sentences and their expected answers were written BEFORE the prose-depth rule was
added to consistency.py, from the AJCC 8th edition definitions (pT1 submucosa; pT2
muscularis propria; pT3 through the muscularis propria into pericolorectal tissue; pT4a
visceral peritoneum; pT4b adjacent organs or structures). The file's SHA-256 was recorded in
THESIS_LOG.md before the rule existed. Run once; record as-is; do not edit to pass.
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import consistency as C   # noqa: E402

CASES = [   # (sentence, expected pT or None)
    ("The tumor invades through the muscularis propria into the pericolic adipose tissue.", 3),
    ("Carcinoma invades the submucosa.", 1),
    ("Tumour infiltrates into, but not through, the muscularis propria.", 2),
    ("The neoplasm penetrates the visceral peritoneum.", 4),
    ("Invasion extends into subserosal tissue.", 3),
    ("The carcinoma directly invades the urinary bladder.", 4),
    ("Tumour is confined to the submucosa.", 1),
    ("Adenocarcinoma extending into the mesorectal fat.", 3),
    ("Metastatic carcinoma involves two pericolic lymph nodes.", None),
    ("The muscularis propria is intact.", None),
    ("Tumour invades the muscularis propria (pT2).", 2),
    ("The tumour reaches the serosal surface.", 4),
    ("Depth of invasion: into pericolorectal tissue.", 3),
    ("No tumour is seen in the submucosa.", None),
    ("Invasive adenocarcinoma, moderately differentiated.", None),
]


def main():
    rows, ok = [], 0
    for text, want in CASES:
        got = C.extract_claims(text)[0]["pt_stage"]
        ok += got == want
        rows.append({"text": text, "expected": want, "got": got, "pass": got == want})
        print(f"{'PASS' if got == want else 'FAIL'}  expected {want!s:4s} got {got!s:4s}  {text}")
    print(f"\n{ok}/{len(CASES)} correct")
    (HERE / "heldout2_results.json").write_text(json.dumps(
        {"n": len(CASES), "correct": ok, "rows": rows}, indent=1))


if __name__ == "__main__":
    main()
