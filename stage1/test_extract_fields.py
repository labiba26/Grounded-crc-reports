"""test_extract_fields.py - pins the Phase 12 fixes to extract_fields.py.

Every phrase below is taken from a real TCGA report that the first extractor got
wrong, found by comparing against GDC's curator-abstracted clinical data
(THESIS_LOG.md, Phase 12). No torch, no data files; runs in well under a second.

    python3 test_extract_fields.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from extract_fields import histologic_type, lymph_node_positive, pn_stage  # noqa: E402

FAILURES = []


def check(label, got, want):
    ok = got == want
    print(f"  {'PASS' if ok else 'FAIL'}  {label}: {got!r}")
    if not ok:
        FAILURES.append(f"{label}: got {got!r}, wanted {want!r}")


NODE = [
    # read as POSITIVE by the first version: negative phrasing containing "metasta"
    ("negative for metastatic", "F. ELEVEN(11) LYMPH NODES ARE NEGATIVE FOR METASTATIC TUMOR.", False),
    ("count of zero, labelled", "Lymph Nodes: Number with metastasis: 0. Total number examined: 31.", False),
    ("pNO, OCR letter O", "33 lymph nodes negative for malignancy (0/33) (pNO).", False),
    ("N0 after a T code", "TNM PATHOLOGIC STAGE. pT3, NO. MX.", False),
    ("no regional node metastasis", "Lymph Node Stage (AJCC 7th Edition) : NO (No regional lymph node metastasis).", False),
    ("count after the words", "Lymph nodes: 0/8 positive for metastasis. (Regional 0/8).", False),
    ("form heading is not a finding", "location of Suspected Involved lymph Nodes location of Suspected Distant Metastasis", None),
    ("distant metastasis alone says nothing about nodes", "No evidence of distant metastasis.", None),
    # genuine positives must survive
    ("positive count", "Metastatic adenocarcinoma in 3/17 lymph nodes.", True),
    ("pN1", "pT3 pN1 (2/14)", True),
    ("word count", "METASTATIC CARCINOMA in one of thirty two lymph nodes.", True),
    ("labelled positive count", "Lymph nodes: 4/12 positive for metastasis.", True),
    ("Latin positive", "Metastases carcinomatosae in lymphonodis (No II/XIV).", True),
]

TYPE = [
    # read as MUCINOUS by the first version: a mucinous part, not a mucinous tumour
    ("15% component", "Tumor Subtype and Differentiation. Mucinous tumor component (Percentage: 15%).", "adenocarcinoma"),
    ("focal differentiation", "Histologic type: Adenocarcinoma with focal mucinous differentiation.", "adenocarcinoma"),
    ("partially mucinous", "a moderately differentiated, partially mucinous colorectal adenocarcinoma", "adenocarcinoma"),
    ("benign mucocele", "Appendix: Hyperplastic mucinous epithelium consistent with benign mucocele. "
                        "Invasive adenocarcinoma of the colon.", "adenocarcinoma"),
    # missed by the first rewrite: OCR punctuation and adjectives between the words
    ("OCR full stop", "Histologic type: Mucinous. adenocarcinoma. Histologic grade: Moderately.", "mucinous"),
    ("adjectives between", "a mucinous, moderately differentiated adenocarcinoma of the colon", "mucinous"),
    ("Latin et mucinosum", "Adenocarcinoma tubulare et mucinosum (G3).", "mucinous"),
    ("Latin partim mucinosum", "Adenocarcinoma tubulopapillare partim mucinosum (G3).", "adenocarcinoma"),
    ("plain mucinous adenocarcinoma", "Diagnosis: mucinous adenocarcinoma of the sigmoid colon.", "mucinous"),
    ("signet-ring features only", "Adenocarcinoma with focal signet ring cell features.", "adenocarcinoma"),
    ("signet-ring carcinoma", "Signet ring cell carcinoma of the cecum.", "signet_ring"),
]


def main():
    print("lymph_node_positive")
    for label, text, want in NODE:
        check(label, lymph_node_positive(text), want)
    print("histologic_type")
    for label, text, want in TYPE:
        check(label, histologic_type(text), want)
    print("pn_stage")
    check("pNO read as 0", pn_stage("(0/33) (pNO)."), 0)
    check("bare word 'no' is not N0", pn_stage("There is no tumour."), None)
    print()
    if FAILURES:
        print("FAILED:\n  " + "\n  ".join(FAILURES))
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
