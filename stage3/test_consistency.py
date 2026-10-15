"""test_consistency.py - pins the checker's verdicts on hand-written cases.

    python3 test_consistency.py
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent / "stage2"))
import consistency as C          # noqa: E402
import findings as F             # noqa: E402

FAIL = []


def check(label, got, want):
    ok = got == want
    print(f"  {'PASS' if ok else 'FAIL'}  {label}: {got!r}")
    if not ok:
        FAIL.append(f"{label}: got {got!r}, wanted {want!r}")


FS = F.from_labels({"histologic_type": "adenocarcinoma", "histologic_grade": 2,
                    "pt_stage": 3, "lymph_node_positive": False})


def status(text, fs=FS):
    r = C.check(text, fs)
    return {k: v["status"] for k, v in r["fields"].items()}, r


def main():
    ok = "Adenocarcinoma, moderately differentiated (G2), pT3. Nodal status is estimated as negative."
    st, r = status(ok)
    check("faithful report: all correct", st, {k: "correct" for k in st})
    check("faithful report: no unsupported claims", r["unsupported_claims"], {})
    check("hedged node claim: no overclaim", r["summary"]["overclaims"], 0)

    st, r = status("Adenocarcinoma, poorly differentiated (G3), pT3. Nodal status is estimated as negative.")
    check("wrong grade -> contradicted", st["grade"], "contradicted")
    st, r = status("Mucinous adenocarcinoma, G2, pT3. Nodal status estimated negative.")
    check("wrong type -> contradicted", st["histologic_type"], "contradicted")
    st, r = status("Adenocarcinoma, G2. Nodal status is estimated as negative.")
    check("missing pT -> omitted", st["pt_stage"], "omitted")
    st, r = status("Adenocarcinoma, G2, pT3. Lymph nodes are negative for metastatic carcinoma.")
    check("unhedged node claim -> overclaim", r["fields"]["node_status"]["overclaim"], True)
    check("...and still correct", st["node_status"], "correct")
    st, r = status("Adenocarcinoma, G2, pT3. Nodal status is estimated as positive.")
    check("wrong node -> contradicted", st["node_status"], "contradicted")

    _, r = status(ok + " Lymphovascular invasion is present. Resection margins are free. "
                       "Tumour size 4.5 cm. 2/15 lymph nodes. Tumour of the sigmoid colon.")
    check("unsupported claims found", sorted(r["unsupported_claims"]),
          ["lymphovascular_invasion", "margins", "node_count", "tumour_site", "tumour_size"])
    _, r = status(ok + " Lymphovascular invasion and margin status could not be assessed on this material.")
    check("abstention is not a claim", r["unsupported_claims"], {})
    _, r = status(ok + " Microsatellite status is not known.")
    check("abstention (not known) is not a claim", r["unsupported_claims"], {})

    st, r = status("Adenocarcinoma, G2, pT3. Nodal status is estimated as negative.", F.empty())
    check("ungrounded input: stated fields are unsupported", set(st.values()), {"unsupported"})

    ref = C.against_reference("Poorly differentiated adenocarcinoma, pT3.", FS)
    check("against reference", ref["fields"],
          {"histologic_type": "correct", "grade": "incorrect", "pt_stage": "correct",
           "node_status": "not stated"})

    st, _ = status("Adenocarcinoma, moderately differentiated, T3. The model predicts node-negative disease.")
    check("paraphrase (words for grade, T3, node-negative) still correct", set(st.values()), {"correct"})
    print()
    if FAIL:
        print("FAILED:\n  " + "\n  ".join(FAIL)); return 1
    print("all checks passed"); return 0


if __name__ == "__main__":
    sys.exit(main())
