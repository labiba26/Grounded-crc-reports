"""
extract_fields.py

Turns the 543 free-text pathology reports into a normalised, machine-readable
findings schema, so the vision model can be trained to predict *verifiable
clinical facts* instead of imitating raw OCR text.

WHY THIS EXISTS
The TCGA reports are multi-institutional, OCR'd and highly heterogeneous. Some
are two lines ("Diagnosis: invasive, moderately differentiated rectal carcinoma
(G2) with penetration of all parietal layers (pT3, L1, v1)"); some are full
macroscopic + microscopic templates; a subset use Latin/Polish terminology
("Infiltratio carcinomatosa", "Metastases carcinomatosae in lymphonodis").
Training a generator to reproduce that text verbatim would also teach it to
reproduce OCR noise and institution-specific formatting as if it were clinical
content. Extracting a normalised schema first gives you:
  1. a reasoning target that is checkable field-by-field (accuracy / F1),
  2. per-field confidence for the trustworthiness component,
  3. a stable intermediate to condition report generation on.

IMPORTANT - THESE ARE WEAK LABELS.
They come from regex over noisy OCR text. Every field may be None, meaning
"not stated in this report" - which is NOT the same as negative. The training
loss must mask None (train_stage1.py does). Before using these in the thesis,
hand-audit the random sample this script prints and report the audited
precision alongside the coverage numbers.

USAGE
    python3 extract_fields.py                     # writes structured_labels.json
    python3 extract_fields.py --sample 15         # print 15 reports + extraction
"""

import argparse
import json
import random
import re
from collections import Counter
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
INDEX = BASE / "dataset_manifests_final" / "dataset_index.json"
OUT = BASE / "stage1" / "structured_labels.json"


def _search(patterns, text):
    for p in patterns:
        m = re.search(p, text, flags=re.I)
        if m:
            return m
    return None


# --------------------------------------------------------------------------- #
# Guards against FORM-STYLE reports.
#
# Some TCGA reports are not narrative prose but printed forms the pathologist
# ticks. Two shapes appear in this cohort:
#
#   radio fields   "Signet Ring Feature : ( ) No ( ) Yes ( ) Yes (Focal)"
#   numbered menus "6. Mucinous Adenocarcinoma  7. Signet ring cell type ..."
#
# In both, the answer is a mark on paper. The PDF text layer carries the
# question and every option but not the mark, so a naive pattern reads the
# printed option as a positive finding. Before this guard, adding 47 recovered
# cases pushed signet-ring carcinoma from 7 to 35 cases (6% of the cohort,
# against roughly 1% in reality) - 28 false positives, all from forms.
#
# These fields are therefore NOT recoverable from the text of a form. The
# honest answer is None ("not stated"), which the training loss masks out,
# rather than a guess.
# --------------------------------------------------------------------------- #

TUMOUR_TYPE_TERMS = [r"adenocarcinom", r"mucinous", r"signet[- ]?ring", r"neuroendocrin",
                     r"carcinoid", r"lymphoma", r"sarcoma", r"squamous",
                     r"stromal tumou?r", r"smooth muscle tumou?r"]
GRADE_TERMS = [r"well[- ]?diff", r"moderately[- ]?diff", r"poorly[- ]?diff", r"undifferentiated"]


def _is_option_list(text, terms, threshold):
    """A document naming this many mutually exclusive alternatives is a printed
    menu, not a diagnosis - a real report commits to one."""
    return sum(1 for k in terms if re.search(k, text, re.I)) >= threshold


def _is_form_option(text, m):
    """True if this match is immediately followed by a Yes/No option run."""
    tail = text[m.end(): m.end() + 90]
    return bool(re.search(r"\bno\b.{0,45}\byes\b|\byes\b.{0,45}\bno\b", tail, re.I))


def _stated(patterns, text):
    """Like _search, but ignores matches that sit inside a form's option list.
    Checks every occurrence, so a real mention later in the report still counts."""
    for pat in patterns:
        for m in re.finditer(pat, text, flags=re.I):
            if not _is_form_option(text, m):
                return m
    return None


# --------------------------------------------------------------------------- #
# Field extractors. Each returns a normalised value, or None when the report
# does not state the field. Order matters where categories overlap
# (rectosigmoid before rectum/sigmoid; signet-ring before adenocarcinoma).
# --------------------------------------------------------------------------- #

def tumour_site(t):
    for label, pats in [
        ("rectosigmoid", [r"recto-?sigmoid"]),
        ("cecum",        [r"c[ae]ec(um|al)", r"ileo-?c[ae]cal", r"valvulae?\s+baughini"]),
        ("ascending",    [r"ascending colon", r"colon ascendens"]),
        ("hepatic_flexure",  [r"hepatic flexure", r"flexura hepatica"]),
        ("transverse",   [r"transverse colon", r"colon transversum"]),
        ("splenic_flexure",  [r"splenic flexure", r"flexura lienalis"]),
        ("descending",   [r"descending colon", r"colon descendens"]),
        ("sigmoid",      [r"\bsigmoid"]),
        ("rectum",       [r"\brect(um|al|i)\b"]),
        ("colon_nos",    [r"\bcolon\b", r"large intestine", r"large bowel"]),
    ]:
        if _search(pats, t):
            return label
    return None


# A mucin mention counts as the DIAGNOSIS only when it names the tumour type.
# WHO defines mucinous adenocarcinoma as >50% extracellular mucin (and signet-ring
# cell carcinoma as >50% signet-ring cells). "Mucinous component (15%)", "focal
# mucinous differentiation" or "partially mucinous" describe an adenocarcinoma with
# a mucinous part, and GDC's curators code those as adenocarcinoma, NOS.
_PARTIAL = (r"(partial(ly)?|partly|partim|focal(ly)?|minor|foci of|areas? of|component|"
            r"with|features?|differentiation|elements?|some)")
# OCR drops full stops into phrases ("mucinous. adenocarcinoma") and adjectives
# sit between the words ("mucinous, moderately differentiated adenocarcinoma"),
# so up to four words and any punctuation may separate them.
_MUCIN_DX = [r"mucinous[\s.,]+(?:[\w-]+[\s.,]+){0,4}?(adeno)?carcinoma",
             r"\bmucinosum", r"colloid\s+carcinoma",
             r"adenocarcinoma[,\s]+mucinous\s+type", r"mucinous\s+type",
             r"(adeno)?carcinoma\s+mucosum", r"carcinoma\s+mucocellulare",
             r"predominantly\s+mucinous", r"mucinous\s+tumou?r(?!\s+component)"]
_SIGNET_DX = [r"signet[- ]?ring[- ]cell\s+(adeno)?carcinoma", r"signet[- ]?ring\s+carcinoma",
              r"carcinoma\s+(e\s+)?cellulis\s+anuli"]


def _diagnostic(patterns, t):
    """A match whose preceding words do not make it partial, and that is not a
    form option. Returns True/False."""
    for pat in patterns:
        for m in re.finditer(pat, t, flags=re.I):
            if _is_form_option(t, m):
                continue
            before = t[max(0, m.start() - 35): m.start()]
            after = t[m.end(): m.end() + 30]
            if re.search(_PARTIAL + r"\W+(\w+\W+){0,2}$", before, re.I):
                continue
            if re.search(r"^\W*(component|features?|differentiation|areas?|foci)", after, re.I):
                continue
            pct = re.search(r"(\d{1,3})\s*%", t[max(0, m.start() - 60): m.end() + 60])
            if pct and int(pct.group(1)) <= 50:
                continue
            return True
    return False


def histologic_type(t):
    """Rewritten 24 Sep 2026 (THESIS_LOG.md, Phase 12) to the WHO definition.

    The first version called a case mucinous if "mucinous" appeared anywhere, so a
    15% mucinous component, focal mucinous differentiation or a benign appendiceal
    mucocele all counted. Of 36 cases labelled mucinous that GDC codes as
    adenocarcinoma, about two-thirds were exactly that. Now only a statement that
    the tumour IS mucinous (or signet-ring cell) carcinoma counts.
    """
    if _is_option_list(t, TUMOUR_TYPE_TERMS, 4):
        return None                       # printed list of tumour types, not a diagnosis
    if _diagnostic(_SIGNET_DX, t):
        return "signet_ring"
    if _diagnostic(_MUCIN_DX, t):
        return "mucinous"
    if _stated([r"adenocarcinom", r"adeno-?ca\b", r"carcinoma", r"mucinous"], t):
        return "adenocarcinoma"
    return None


def histologic_grade(t):
    m = re.search(r"\bG\s?([1-4])\b", t)
    if m:
        return int(m.group(1))
    # "Grade: Moderately Differentiated" is a statement even on a form, because the
    # value follows the label. A bare list of all four grades is a menu.
    m = re.search(r"grade\s*[:\-]\s*(well|moderately|poorly|un)[a-z]*\s*diff", t, re.I)
    if m:
        return {"well": 1, "moderately": 2, "poorly": 3, "un": 4}[m.group(1).lower()]
    if _is_option_list(t, GRADE_TERMS, 3):
        return None                       # every grade printed as an option
    for grade, pats in [
        (1, [r"well[- ]differentiated", r"bene differentiatum"]),
        (2, [r"moderately[- ]differentiated", r"medium[- ]differentiated"]),
        (3, [r"poorly[- ]differentiated", r"male differentiatum"]),
        (4, [r"undifferentiated", r"anaplastic"]),
    ]:
        if _search(pats, t):
            return grade
    return None


def pt_stage(t):
    m = re.search(r"\bp?\s?T\s?([0-4])\s?[a-d]?\b", t)
    return int(m.group(1)) if m else None


def pn_stage(t):
    m = re.search(r"\bp?\s?N\s?([0-3])\s?[a-c]?\b", t)
    if m:
        return int(m.group(1))
    # OCR renders zero as the letter O ("pNO"); accepted only with the p prefix,
    # since a bare "NO" is usually the word "no".
    m = re.search(r"\bp\s?N\s?O(?![a-z])", t, re.I)
    return 0 if m else None


_NUM = (r"(\d+|no|none|zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|"
        r"twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty)")
_WORDS = {"no": 0, "none": 0, "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4,
          "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
          "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
          "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20}


def _n(tok):
    tok = tok.lower()
    return int(tok) if tok.isdigit() else _WORDS.get(tok)


def lymph_node_positive(t):
    """True = nodal metastasis, False = nodes examined and negative, None = not stated.

    Rewritten 24 Sep 2026 (THESIS_LOG.md, Phase 12). The first version tested
    POSITIVE patterns first and loosely ("lymph node ... metasta" within 60
    characters), so "eleven lymph nodes are negative for metastatic tumour" and
    "Number with metastasis: 0" were read as positive. Checked against GDC's
    curator-abstracted pathologic N, 96 cases were labelled positive where both the
    report and GDC say N0 - about 30% of all positives. It is the same failure as
    the first margin extractor, and the fix is the same: the most specific evidence
    decides, and negative phrasing is tested before generic positive phrasing.

    Order of evidence, strongest first:
      1. pN stage, tolerating OCR's letter O for zero ("pNO"), and the
         "pT3, N0" run of a TNM line.
      2. Explicit counts: "3/17 lymph nodes", "Number with metastasis: 0",
         "0 of 12", "three of fifteen lymph nodes".
      3. Negative statements about the nodes.
      4. Positive statements about the nodes.
    The generic "metasta ... lymph" window is gone: it matched form headings
    ("Suspected Involved lymph Nodes ... Distant Metastasis") and "no distant
    metastasis" alike.
    """
    # 1. pN stage (letter O accepted as zero; N-category after a T code)
    m = _stated([r"\bp\s?N\s?([0-3O])(?![a-z])", r"\bp?T\s?[0-4][a-d]?\s*[,;/]?\s*p?N\s?([0-3O])(?![a-z])",
                 r"lymph node stage[^:]{0,40}:\s*p?N\s?([0-3O])(?![a-z])"], t)
    if m:
        v = m.group(1).upper()
        return v not in ("0", "O")

    # 2. explicit counts
    pos_counts, zero_counts = False, False
    for m in re.finditer(r"\b(\d+)\s*(?:/|of)\s*(\d+)\s*(?:\(?\w+\)?\s*){0,3}(?:lymph|nod|ln\b)", t, re.I):
        k, n = int(m.group(1)), int(m.group(2))
        if k <= n:
            pos_counts |= k > 0
            zero_counts |= k == 0
    # count AFTER the words: "Lymph nodes: 0/8 positive for metastasis"
    for m in re.finditer(r"lymph\s?nod\w*\s*[:\-]?\s*(\d+)\s*(?:/|of)\s*(\d+)", t, re.I):
        k, n = int(m.group(1)), int(m.group(2))
        if k <= n:
            pos_counts |= k > 0
            zero_counts |= k == 0
    for m in re.finditer(r"(?:number|no\.?)\s+(?:of\s+)?(?:lymph\s+nodes?\s+)?"
                         r"(?:with metastas\w*|positive|involved)[^:\d]{0,20}:?\s*" + _NUM, t, re.I):
        k = _n(m.group(1))
        if k is not None:
            pos_counts |= k > 0
            zero_counts |= k == 0
    for m in re.finditer(_NUM + r"\s+(?:\(\d+\)\s*)?of\s+" + _NUM +
                         r"\s+(?:\w+\s+){0,2}lymph", t, re.I):
        k, n = _n(m.group(1)), _n(m.group(2))
        if k is not None and n is not None and k <= n:
            pos_counts |= k > 0
            zero_counts |= k == 0
    if pos_counts:
        return True
    if zero_counts:
        return False

    # 3. negative statements about the nodes
    if _search([
        r"lymph\s?nod\w*[^.]{0,50}\b(negative|free of|uninvolved|benign|"
        r"no (evidence of )?(metasta|tumou?r|carcinoma|malignan))",
        r"no\s+(evidence of\s+)?(regional\s+)?(lymph\s?nod\w*\s+)?metasta\w*[^.]{0,20}lymph",
        r"no (regional )?lymph\s?node metasta",
        r"(negative|free) (for|of) (metasta\w*|tumou?r|carcinoma|malignan\w*)[^.]{0,40}lymph",
        r"lymph\s?nod\w*[^.]{0,40}(reactive|hyperplas)",
        r"sine metastas", r"absque metastas", r"lymphonod\w*[^.]{0,40}sine",
    ], t):
        return False

    # 4. positive statements about the nodes
    if _stated([
        r"metasta\w*\s+(adeno)?carcinoma[^.]{0,40}(in|involving)[^.]{0,30}lymph\s?nod",
        r"lymph\s?nod\w*[^.]{0,30}(positive for|involved by|with|showing|containing)"
        r"[^.]{0,20}(metasta|carcinoma|adenocarcinom|tumou?r)",
        r"metastases carcinomatosae in lymphonod", r"metastas\w*[^.]{0,20}in lymphonodis",
    ], t):
        return True
    return None


def margins_involved(t):
    """True = margin involved, False = margin clear, None = not stated.

    Negatives are tested FIRST and with a tight window. OCR drops sentence
    boundaries, so a wide window lets an unrelated clause ("...5 cm from the
    surgical margin there is a circular, ulcerated ... infiltrated") satisfy a
    "margin ... infiltrat" pattern and flip a clear margin to involved. That
    exact false positive was found by hand-auditing TCGA-G4-6628 and
    TCGA-F5-6864, so clear-margin phrasing now wins ties.
    """
    if _search([
        r"margins?[^.]{0,25}(free|negative|uninvolved|not involved|clear)",
        r"(incision|resection) lines?[^.]{0,25}free",
        r"free of (neoplastic|tumou?r|carcinom)",
        r"tumou?r[- ]free[^.]{0,20}margin", r"\bR0\b",
    ], t):
        return False
    if _search([
        r"margins?[^.]{0,25}(involved|positive for tumou?r|infiltrated)",
        r"(incision|resection) lines?[^.]{0,25}(involved|infiltrated)",
        r"\bR1\b", r"\bR2\b",
    ], t):
        return True
    return None


def lymphovascular_invasion(t):
    """True/False/None.

    A bare "L1" or "V1" is NOT trusted on its own - those tokens also appear as
    specimen labels and OCR debris. They are only accepted inside a TNM-style
    classification run (e.g. "G3, P T 3, L1, V1, p N0"), i.e. when an L/V code
    sits near another staging code. Explicit prose is always trusted.
    """
    if _search([r"lymphovascular invasion", r"venous invasion", r"lymphatic invasion",
                r"angioinvasion", r"lymphangio(sis|invasion)"], t):
        return True
    if _search([r"no lymphovascular", r"no venous invasion", r"no lymphatic invasion",
                r"without lymphovascular"], t):
        return False
    # TNM-style run: an L or V code within ~25 chars of a T/N/other L-V code.
    m = _search([r"\b[LV]\s?[01]\b[^.]{0,25}\b[pTNLV]\s?\d\b",
                 r"\b[pTN]\s?\d\b[^.]{0,25}\b[LV]\s?[01]\b"], t)
    if m:
        run = m.group(0)
        if re.search(r"\b[LV]\s?1\b", run):
            return True
        if re.search(r"\b[LV]\s?0\b", run):
            return False
    return None


FIELDS = {
    "tumour_site": tumour_site,
    "histologic_type": histologic_type,
    "histologic_grade": histologic_grade,
    "pt_stage": pt_stage,
    "pn_stage": pn_stage,
    "lymph_node_positive": lymph_node_positive,
    "margins_involved": margins_involved,
    "lymphovascular_invasion": lymphovascular_invasion,
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=0,
                    help="print N random reports with their extraction, for hand-auditing")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    cases = json.loads(INDEX.read_text())
    out, per_field = {}, {k: Counter() for k in FIELDS}

    for c in cases:
        text = "\n".join((BASE / p).read_text(errors="ignore") for p in c["reports"])
        labels = {name: fn(text) for name, fn in FIELDS.items()}
        out[c["case_id"]] = {"cohort": c["cohort"], "labels": labels,
                             "report_chars": len(text)}
        for k, v in labels.items():
            per_field[k][v] += 1

    OUT.write_text(json.dumps(out, indent=2))

    print(f"Cases labelled: {len(out)}  ->  {OUT.relative_to(BASE)}\n")
    print(f"{'FIELD':24s} {'COVERAGE':>10s}   VALUE DISTRIBUTION")
    print("-" * 96)
    for k, counter in per_field.items():
        n_missing = counter[None]
        cov = 100 * (len(out) - n_missing) / len(out)
        dist = ", ".join(f"{v}={n}" for v, n in
                         sorted(counter.items(), key=lambda kv: (kv[0] is None, -kv[1]))
                         if v is not None)
        print(f"{k:24s} {cov:8.1f}%   {dist[:60]}")

    if args.sample:
        random.seed(args.seed)
        print("\n" + "=" * 96)
        print("RANDOM SAMPLE FOR HAND-AUDIT (check these before trusting the labels)")
        print("=" * 96)
        for cid in random.sample(list(out), args.sample):
            c = next(x for x in cases if x["case_id"] == cid)
            text = "\n".join((BASE / p).read_text(errors="ignore") for p in c["reports"])
            print(f"\n--- {cid} ({out[cid]['cohort']}) ---")
            print(" ".join(text.split())[:420], "...")
            print("  ->", {k: v for k, v in out[cid]["labels"].items() if v is not None})


if __name__ == "__main__":
    main()
