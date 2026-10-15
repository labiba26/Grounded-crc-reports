"""
qc_labels.py - objective quality check on the weak labels from extract_fields.py.

Hand-auditing a sample tells you whether labels *look* right; this measures it
without opinion, by cross-checking fields that must agree clinically:

  pn_stage 0  <-> lymph_node_positive False
  pn_stage 1+ <-> lymph_node_positive True

Both are extracted by independent patterns, so their agreement rate is a lower
bound on label quality for the nodal fields. Disagreements are printed so they
can be inspected individually. Report this number in the thesis next to the
coverage table - it is the difference between "we used regex labels" and "we
used regex labels and quantified how far they can be trusted".
"""
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
labels = json.loads((BASE / "stage1" / "structured_labels.json").read_text())

agree = disagree = 0
bad = []
for cid, rec in labels.items():
    pn, ln = rec["labels"]["pn_stage"], rec["labels"]["lymph_node_positive"]
    if pn is None or ln is None:
        continue
    expected = pn > 0
    if expected == ln:
        agree += 1
    else:
        disagree += 1
        bad.append((cid, pn, ln))

total = agree + disagree
print("=== Nodal-field cross-check (pn_stage vs lymph_node_positive) ===")
print(f"Cases where both fields were extracted: {total}")
if total:
    print(f"  agree:    {agree}  ({100*agree/total:.1f}%)")
    print(f"  disagree: {disagree}  ({100*disagree/total:.1f}%)")
    for cid, pn, ln in bad[:10]:
        print(f"    {cid}: pn_stage={pn} but lymph_node_positive={ln}")

n = len(labels)
per_case = [sum(v is not None for v in r["labels"].values()) for r in labels.values()]
print(f"\n=== Fields extracted per case (out of 8) ===")
print(f"  mean {sum(per_case)/n:.1f}   min {min(per_case)}   max {max(per_case)}")
print(f"  cases with >=5 fields: {sum(x>=5 for x in per_case)}/{n} "
      f"({100*sum(x>=5 for x in per_case)/n:.0f}%)")
