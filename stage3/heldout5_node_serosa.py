"""heldout5_node_serosa.py - a FIFTH frozen held-out set: node statements and pT4/pT2 in words.

Why it exists: the blind LLM judge (29 Sep, improvement item 3) read 60 generated reports and found
that checker v1.3 misses node statements such as "lymph node status is positive" and reads
serosal involvement as pT3 rather than pT4. The 60 reports themselves are NOT used here: these
sentences are new, written BEFORE any fix (AJCC 8: pT4a = through the visceral peritoneum/serosa,
pT4b = into an adjacent organ), including traps. The SHA-256 of this file is recorded in
THESIS_LOG.md before the fix. Run once per checker version; do not edit to pass.
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import consistency as C   # noqa: E402

NODE = [   # (sentence, expected node_status claim: True / False / None)
    ("The lymph node status is reported as positive.", True),
    ("Regional lymph node status was found to be positive.", True),
    ("Metastatic carcinoma is identified in the regional lymph nodes.", True),
    ("Two lymph nodes are involved by metastatic adenocarcinoma.", True),
    ("There is involvement of several regional lymph nodes.", True),
    ("No malignant cells are seen in the lymph nodes sampled.", False),
    ("None of the examined lymph nodes contain tumour.", False),
    ("The regional lymph nodes show no metastatic carcinoma.", False),
    ("Lymph node status is reported as negative.", False),
    # controls: no node claim
    ("No lymph nodes were submitted for examination.", None),
    ("Lymph nodes are not included in this sample.", None),
    ("Lymphovascular invasion is present.", None),
]
PT = [     # (sentence, expected pT)
    ("The tumour penetrates the serosa.", 4),
    ("Carcinoma involves the serosal layer.", 4),
    ("The tumour extends to the serosa.", 4),
    ("The tumour grows into the wall of the small bowel.", 4),
    ("The carcinoma directly invades the urinary bladder.", 4),
    ("Invasion is limited to the muscularis propria.", 2),
    ("The tumour is confined to the muscularis propria.", 2),
    # controls
    ("The tumour infiltrates the subserosa.", 3),
    ("The tumour extends into the subserosal tissue but does not reach the serosa.", 3),
    ("Chronic serosal inflammation is present.", None),
    ("The tumour reaches the serosal surface.", 4),
]


def main():
    rows = []
    for text, want in NODE:
        got = C.extract_claims(text)[0]["node_status"]
        rows.append({"kind": "node", "text": text, "expected": want, "got": got, "pass": got == want})
    for text, want in PT:
        got = C.extract_claims(text)[0]["pt_stage"]
        rows.append({"kind": "pT", "text": text, "expected": want, "got": got, "pass": got == want})
    ok = sum(r["pass"] for r in rows)
    for r in rows:
        print(f"{'PASS' if r['pass'] else 'FAIL'}  {r['kind']:4s} expected {str(r['expected']):5s} got {str(r['got']):5s}  {r['text']}")
    print(f"\n{ok}/{len(rows)} correct (checker {C.VERSION})")
    out = HERE / "heldout5_results.json"
    prev = json.loads(out.read_text()) if out.exists() else {}
    prev[C.VERSION] = {"n": len(rows), "correct": ok, "rows": rows}
    out.write_text(json.dumps(prev, indent=1))


if __name__ == "__main__":
    main()
