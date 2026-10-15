"""consistency.py - the Stage 3 consistency checker (THESIS_LOG.md, Phases 11-12).

Given a report (generated or real) and the FindingSet it was supposed to be written
from, the checker says, field by field:

  correct       the report states the input value
  contradicted  the report states a different value
  omitted       the input has the field, the report does not state it
  unsupported   the report states a field the input does NOT contain
  absent        neither has it

and separately:

  unsupported claims  anything else asserted that no input supports - lymphovascular
                      invasion, margins, node counts, pN category, site, size, distant
                      metastasis, MSI/MMR, perineural invasion, budding, other staging
                      systems, treatment history
  overclaim           a NOT-VISIBLE field (node status: the slides are primary tumour)
                      stated as an observation, without any hedge

Sentences that explicitly abstain ("margins could not be assessed") are removed first,
so declining to answer is never counted as a claim.

It is rule-based on purpose: every verdict can be traced to a pattern. Its accuracy is
measured, not assumed - see planted_errors.py (known errors), the gold labels, and the
double annotation of generated reports.
"""
from __future__ import annotations

VERSION = "v1.4"   # bumped with every behaviour change (THESIS_LOG.md)
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "stage1"))
sys.path.insert(0, str(HERE.parent / "stage2"))
import extract_fields as X          # noqa: E402
from findings import FIELDS, VISIBILITY  # noqa: E402

I = re.I
SPLIT = re.compile(r"(?<=[.;!?])\s+|\n+")
ABSTAIN = re.compile(
    r"\b(not|cannot be|could not be|can ?not be|un)\s*(be\s+)?"
    r"(assessed|assessable|evaluated|evaluable|determined|determinable|available|reported|provided|known)\b"
    r"|\bunknown\b|\bno information\b|\binsufficient (tissue|material|information)\b", I)
HEDGE = re.compile(
    r"\b(estimat\w*|predict\w*|infer\w*|likely|probabl\w*|suggest\w*|may|might|possibl\w*|"
    r"model|confidence|uncertain\w*|not (directly )?(observed|assessed|examined|seen))\b", I)
NODE_WORDS = re.compile(r"lymph|\bnod(e|es|al)\b|\bp?N[0-3O]\b", I)

# generated-report phrasing the report extractor was never written for
NODE_NEG = [r"\bnode[- ]negative\b",
            r"\bnodal (status|involvement|disease)\b[^.;]{0,60}\bnegative\b",
            r"\bno (evidence of )?(regional )?(lymph ?node|nodal) (metasta\w*|involvement|disease)",
            r"\blymph ?nodes? (are |is )?(negative|free of (tumou?r|metasta\w*)|uninvolved)",
            r"\b(lymph ?node|nodal) (metasta\w*|involvement|disease)[^.;]{0,40}\b(absent|unlikely|not (expected|present|identified|likely))\b",
            r"\b(lymph ?node|nodal) (involvement|metasta\w*|status|disease)\s*:?\s*((un)?likely|probably|predicted|estimated)?\s*(no|negative|absent)\b",
            # v1.4 (29 Sep, heldout5_node_serosa.py)
            r"\blymph ?node status\b[^.;]{0,30}\bnegative\b",
            r"\bno (malignan\w*|metasta\w*|tumou?r|carcinoma|cancer)( (cells?|disease|deposits?))?[^.;]{0,30}\blymph ?nodes?\b",
            r"\bnone of the (\w+\s+){0,2}lymph ?nodes\b",
            r"\bno (\w+\s+){0,2}involvement of (\w+\s+){0,3}lymph ?nodes\b"]
NODE_POS = [r"\bnode[- ]positive\b",
            # v1.4 (29 Sep, heldout5_node_serosa.py)
            r"\blymph ?node status\b[^.;]{0,30}\bpositive\b",
            r"(?<!no )\binvolvement of (\w+\s+){0,3}lymph ?nodes\b",
            r"\bnodal (status|involvement|disease)\b[^.;]{0,60}\b(positive|present|likely|involved)\b",
            r"\b(lymph ?node|nodal) metasta\w*[^.;]{0,30}\b(present|likely|probable|identified|expected)\b",
            r"\bmetasta\w* (to|in|involving) (the )?(regional )?lymph ?nodes",
            r"\b(lymph ?node|nodal) (involvement|metasta\w*|status|disease)\s*:?\s*(likely|probably|predicted|estimated)?\s*(yes|positive|present)\b"]

UNSUPPORTED = {
    "lymphovascular_invasion": r"(lymphovascular|angiolymphatic|lymphatic|vascular|venous) (invasion|infiltration)|\b[LV][01]\b",
    "margins": r"\bmargins?\b[^.;]{0,50}\b(free|clear|negative|uninvolved|involved|positive|infiltrated)\b|\bR[012]\b|resection lines?",
    "node_count": X._NUM + r"\s+(\(\d+\)\s*)?of\s+" + X._NUM + r"\s+(\w+\s+){0,2}lymph|" + r"\(\d+\s*/\s*\d+\)|\b\d+\s+(positive\s+|involved\s+)?(regional\s+)?lymph ?nodes?\b|\b\d+\s*(/|of)\s*\d+\s*(\(?\w+\)?\s*){0,3}(lymph|nod)|lymph ?nodes?[^.;]{0,25}\b\d+\s*(/|of)\s*\d+|(number|no\.)\s+(of\s+)?(lymph\s+nodes?\s+)?(with metastas\w*|positive|examined)",
    "pn_category": r"\bp?N[0-3O][abc]?\b(?![a-z])",
    "tumour_size": r"\b\d+(\.\d+)?\s*(x\s*\d+(\.\d+)?\s*)*(cm|mm)\b",
    "distant_metastasis": r"\bp?M[01][abc]?\b|distant metasta|(liver|hepatic|lung|pulmonary|peritoneal) metasta",
    "msi_mmr": r"\b(MSI|MSS|microsatellite|mismatch repair|MMR|MLH1|MSH2|MSH6|PMS2)\b",
    "perineural_invasion": r"perineural",
    "tumour_budding": r"\bbudding\b",
    "other_staging": r"\bDukes\b|Astler|\bAJCC stage\b|\bstage\s+(I{1,3}V?|IV)[ABC]?\b",
    "treatment_history": r"neoadjuvant|treatment effect|regression grade|\byp[TN]",
}


def sentences(text):
    return [s.strip() for s in SPLIT.split(text) if s and s.strip()]


def strip_abstentions(text):
    kept, dropped = [], []
    for s in sentences(text):
        (dropped if ABSTAIN.search(s) else kept).append(s)
    return " ".join(kept), dropped


def _node_in(s):
    """Node claim in one sentence: generated phrasing first (negatives before
    positives), then the report extractor (pN, counts, report phrasing)."""
    for pats, val in ((NODE_NEG, False), (NODE_POS, True)):
        if any(re.search(p, s, I) for p in pats):
            return val
    return X.lymph_node_positive(s)


ROMAN = {"i": 1, "ii": 2, "iii": 3, "iv": 4}


def _grade_number(t):
    """'grade 2', 'Grade: II', 'histologic grade 3/4' - not caught by the report
    extractor. Regression grades and dysplasia grades are excluded."""
    for m in re.finditer(r"\bgrade\s*[:\-]?\s*(\d|iv|i{1,3})\b", t, I):
        before = t[max(0, m.start() - 25): m.start()].lower()
        if "regression" in before or "dysplas" in t[m.end(): m.end() + 20].lower():
            continue
        v = m.group(1).lower()
        v = int(v) if v.isdigit() else ROMAN[v]
        if 1 <= v <= 4:
            return v
    return None


# Depth of invasion written in words (checker v1.1, 26 Sep - THESIS_LOG.md). AJCC 8th edition:
# pT1 submucosa, pT2 muscularis propria, pT3 through it into pericolorectal tissue,
# pT4 visceral peritoneum (4a) or adjacent organs/structures (4b). Used only when no pT code
# is present; sentences about lymph nodes and negated sentences are skipped; the deepest
# level stated anywhere in the report is taken.
_VERB = r"(invad|infiltrat|extend|penetrat|involv|reach|spread|grow)\w*"
_DEPTH = [
    (4, [_VERB + r"[^.;]{0,40}\b(visceral peritoneum|serosal? surface|peritoneal surface|peritoneum)\b",
         # v1.4: the serosa itself (never "subserosa": \b before "serosa"), and named adjacent organs
         _VERB + r"[^.;]{0,40}\bserosa(l)?\b",
         _VERB + r"[^.;]{0,40}\b(small (bowel|intestine)|(urinary )?bladder|uterus|vagina|prostate|seminal vesicles?|ovar(y|ies)|abdominal wall)\b",
         _VERB + r"[^.;]{0,40}\b(adjacent|neighbou?ring|other) (organs?|structures?)\b"]),
    (3, [r"(?<!not )\bthrough (the )?muscularis propria\b",
         _VERB + r"[^.;]{0,40}\b(peri-?(colic|colonic|rectal|colorectal)|subserosa\w*|mesorect\w*|mesocolic|adipose|fat)\b",
         r"\binto (the )?(peri-?(colic|colonic|rectal|colorectal)|subserosa\w*|mesorect\w*)"]),
    (2, [_VERB + r"[^.;]{0,30}\bmuscularis propria\b", r"\binto (the )?muscularis propria\b",
         r"\b(limited|confined|restricted) to (the )?muscularis propria\b"]),
    (1, [_VERB + r"[^.;]{0,30}\bsubmucosa\b", r"\bconfined to (the )?submucosa\b"]),
]
_NEG = re.compile(r"\bno\b[^.;]{0,25}\b(invasion|tumou?r|carcinoma|neoplasm)\b", I)


_NEG_CLAUSE = re.compile(r"\b(?:does|do|did|is|are)?\s*not\b[^.;,]*", I)   # v1.4: a negated clause is not a depth claim


def _pt_prose(text):
    best = None
    for s in sentences(text):
        s = _NEG_CLAUSE.sub(" ", s)
        if re.search(r"lymph|\bnod(e|es|al)\b", s, I) or _NEG.search(s):
            continue
        for level, pats in _DEPTH:
            if any(re.search(p, s, I) for p in pats):
                best = level if best is None else max(best, level)
                break
    return best


# Checker v1.2 (29 Sep, THESIS_LOG.md): grade as a noun ("moderate differentiation",
# "Differentiation: poor") and margins verb-first ("involves the lateral margin"). Used only when
# the v1.1 readers find nothing, so earlier verdicts cannot change except where they were blank.
_GRADE_NOUN = re.compile(
    r"\b(good|well|moderate|intermediate|poor|low|high)\s+differentiation\b"
    r"|\bdifferentiation\s*[:\-]\s*(good|well|moderate|intermediate|poor)\b", I)
_GRADE_WORD = {"good": 1, "well": 1, "moderate": 2, "intermediate": 2, "poor": 3}
_MARGIN_VERB = re.compile(
    r"\b(involv\w*|reach\w*|extend\w*\s+to|abut\w*|transect\w*)\s+(the\s+)?(\w+\s+){0,2}margins?\b", I)


def _grade_noun(t):
    for s in sentences(t):
        m = _GRADE_NOUN.search(s)
        if m and not re.search(r"\bno\b[^.;]{0,20}" + re.escape(m.group(0)), s, I):
            w = (m.group(1) or m.group(2)).lower()
            if w in _GRADE_WORD:
                return _GRADE_WORD[w]
    return None


# v1.3 (29 Sep, heldout4_confidence.py): a model confidence is not a mucin share. The type rule
# reads any percentage <= 50 near "mucinous" as the WHO mucin share, so "(model confidence 40%)"
# flipped a mucinous claim. Confidence/probability percentages are masked before the type is read,
# and a negated type ("not of mucinous type", "non-mucinous") is read as adenocarcinoma.
_CONF_PCT = re.compile(
    r"\b(?:model\s+)?(?:confidence|probability|certainty|likelihood)\b[^%.;()]{0,25}?\d{1,3}(?:\.\d+)?\s*%"
    r"|\d{1,3}(?:\.\d+)?\s*%\s*(?:model\s+)?(?:confidence|probability|certainty|likelihood)\b", I)
_NOT_MUCIN = re.compile(r"\b(?:not|non|without)[\s-]+(?:of\s+|a\s+)?mucinous(?:\s+type)?\b", I)


def _type_text(body):
    return _NOT_MUCIN.sub("non-mucin type", _CONF_PCT.sub("confidence", body))


def extract_claims(text):
    """What the report asserts. Returns (claims, hedges, abstentions)."""
    body, dropped = strip_abstentions(text)
    sents = sentences(body)
    claims = {}

    t = X.histologic_type(_type_text(body))
    if t == "adenocarcinoma" and not re.search(r"adenocarcinom|adeno-?ca\b", body, I):
        t = None                               # bare "carcinoma" is not a type claim
    claims["histologic_type"] = t
    claims["grade"] = X.histologic_grade(body) or _grade_number(body) or _grade_noun(body)
    claims["pt_stage"] = X.pt_stage(body) or _pt_prose(body)

    node, node_hedged = None, False
    for i, s in enumerate(sents):
        if not NODE_WORDS.search(s):
            continue
        v = _node_in(s)
        if v is not None:
            node = v
            window = [s]                   # the claim sentence, and the one before only if it
            if i > 0 and NODE_WORDS.search(sents[i - 1]):   # is about nodes too
                window.insert(0, sents[i - 1])
            node_hedged = bool(HEDGE.search(" ".join(window)))
            break
    if node is None:                              # messy real reports: whole-text fallback
        node = X.lymph_node_positive(body)
        node_hedged = node is not None and bool(HEDGE.search(body))
    claims["node_status"] = node

    extra = {}
    for name, pat in UNSUPPORTED.items():
        m = re.search(pat, body, I if name not in ("pn_category", "distant_metastasis") else 0)
        if m:
            extra[name] = m.group(0)
    if "margins" not in extra:
        m = _MARGIN_VERB.search(body)
        if m:
            extra["margins"] = m.group(0)
    site = X.tumour_site(body)
    if site and site != "colon_nos":              # "colon" alone says nothing for a colorectal cohort
        extra["tumour_site"] = site
    return claims, {"node_status": node_hedged}, extra, dropped


def check(text, finding_set):
    """Compare a report with the FindingSet it was written from."""
    claims, hedges, extra, dropped = extract_claims(text)
    inp = finding_set["findings"]
    fields = {}
    for f in FIELDS:
        want = None if inp.get(f) is None else inp[f]["value"]
        got = claims[f]
        if want is None:
            status = "absent" if got is None else "unsupported"
        elif got is None:
            status = "omitted"
        else:
            status = "correct" if got == want else "contradicted"
        overclaim = (VISIBILITY[f] == "not visible" and got is not None
                     and not hedges.get(f, False))
        fields[f] = {"input": want, "stated": got, "status": status,
                     "visibility": VISIBILITY[f], "overclaim": overclaim}
    summary = {s: sum(v["status"] == s for v in fields.values())
               for s in ("correct", "contradicted", "omitted", "unsupported", "absent")}
    summary["unsupported_claims"] = len(extra)
    summary["overclaims"] = sum(v["overclaim"] for v in fields.values())
    return {"fields": fields, "unsupported_claims": extra, "abstentions": dropped,
            "summary": summary}


def against_reference(text, reference_set):
    """Correctness of a report's claims against a reference (e.g. the weak labels),
    regardless of what the generator was given - this is how the UNGROUNDED arm is
    scored, since it had no input to be faithful to."""
    claims, _, extra, _ = extract_claims(text)
    ref = reference_set["findings"]
    out = {}
    for f in FIELDS:
        want = None if ref.get(f) is None else ref[f]["value"]
        got = claims[f]
        out[f] = ("not stated" if got is None else "no reference" if want is None
                  else "correct" if got == want else "incorrect")
    return {"fields": out, "unsupported_claims": extra}
