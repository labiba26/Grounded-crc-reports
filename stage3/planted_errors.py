"""planted_errors.py - validates the consistency checker on errors whose truth is known.

Every test takes a report the checker should pass, plants ONE known change, and asks
two questions: did the checker report exactly that change (detection), and did it
report anything else (a false alarm)?

Suite A - template reports (3 styles) for real cases, from extracted or simulated
          predicted findings: wrong values, omissions, unsupported claims, and
          overclaims on node status. Controls that must NOT be flagged: abstentions,
          and paraphrases written in different vocabulary from the templates.
Suite B - REAL pathology reports (OCR, many institutions) with a value swapped in the
          text: grade, pT, histologic type. Tests the checker on messy text it was not
          written against.
Also    - the unsupported-claim profile of the real reports: what human pathologists
          write beyond the four fields - i.e. what an LLM fine-tuned on them will learn.

The 50 gold-label cases are excluded throughout.

    python3 planted_errors.py            # writes planted_errors_results.json
"""
import copy
import json
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(BASE / "stage2"))
import consistency as C                      # noqa: E402
import findings as F                         # noqa: E402
import template_report as T                  # noqa: E402

rng = random.Random(7)
LABELS = json.loads((BASE / "stage1" / "structured_labels.json").read_text())
GOLD = {r["case_id"] for r in json.loads((BASE / "gold_labels" / "sample_key.json").read_text())["rows"]}
INDEX = {c["case_id"]: c for c in json.loads((BASE / "dataset_manifests_final" / "dataset_index.json").read_text())}
N_CASES = 150

OTHER = {"histologic_type": lambda v: rng.choice([x for x in ("adenocarcinoma", "mucinous") if x != v]),
         "grade": lambda v: rng.choice([x for x in (1, 2, 3) if x != v]),
         "pt_stage": lambda v: rng.choice([x for x in (1, 2, 3, 4) if x != v]),
         "node_status": lambda v: not v}
UNHEDGED = {True: "Metastatic carcinoma is present in the regional lymph nodes.",
            False: "The regional lymph nodes are negative for metastatic carcinoma."}
INSERT = {"lymphovascular_invasion": "Lymphovascular invasion is identified.",
          "margins": "All resection margins are free of tumour.",
          "node_count": "Two of fourteen lymph nodes contain metastatic carcinoma.",
          "pn_category": "Nodal category pN1b.",
          "tumour_size": "The tumour measures 4.2 x 3.1 cm.",
          "distant_metastasis": "There is no evidence of distant metastasis (M0).",
          "msi_mmr": "Mismatch repair proteins are retained.",
          "perineural_invasion": "Perineural invasion is present.",
          "tumour_site": "The tumour is located in the sigmoid colon.",
          "treatment_history": "No treatment effect is seen."}
ABSTAIN = ["Lymphovascular invasion and margin status cannot be assessed from this material.",
           "Lymph node counts are not available.", "Mismatch repair status is unknown.",
           "Tumour size could not be determined."]
TYPE_P = {"adenocarcinoma": ["Invasive adenocarcinoma", "Adenocarcinoma of colorectal type",
                             "An adenocarcinoma"],
          "mucinous": ["Invasive mucinous adenocarcinoma", "Colloid carcinoma",
                       "A mucinous carcinoma"]}
GRADE_P = {"words": lambda g: T.GRADE_WORDS[g], "G-code": lambda g: f"G{g}",
           "WHO words": lambda g: f"grade: {T.GRADE_WORDS[g]}",
           "grade N": lambda g: f"grade {g}", "roman": lambda g: f"grade {'I' * g if g < 4 else 'IV'}"}
T_P = {"pT": lambda t: f"pT{t}", "T": lambda t: f"T{t}", "stage": lambda t: f"tumour category pT{t}"}
NODE_P = {"predicted present/absent": lambda n: f"Regional nodal metastasis is predicted to be {'present' if n else 'absent'}.",
          "model suggests node-x": lambda n: f"The model suggests the tumour is node-{'positive' if n else 'negative'}.",
          "likely yes/no": lambda n: f"Lymph node involvement: likely {'yes' if n else 'no'}.",
          "estimate nodal disease": lambda n: f"Estimated nodal disease: {'positive' if n else 'negative'}."}


def cases():
    ok = [c for c in sorted(LABELS) if c not in GOLD and all(
        LABELS[c]["labels"][k] is not None for k in
        ("histologic_type", "histologic_grade", "pt_stage", "lymph_node_positive"))
        and LABELS[c]["labels"]["histologic_type"] != "signet_ring"]
    return rng.sample(ok, min(N_CASES, len(ok)))


def finding_set(cid, predicted):
    fs = F.from_labels(LABELS[cid]["labels"])
    if predicted:
        fs["source"] = "predicted"
        for f in fs["findings"].values():
            f["prob"] = round(rng.uniform(0.5, 0.99), 2)
    return fs


def verdict(text, fs):
    r = C.check(text, fs)
    return {k: v["status"] for k, v in r["fields"].items()}, set(r["unsupported_claims"]), \
        {k for k, v in r["fields"].items() if v["overclaim"]}


def suite_a():
    res = defaultdict(lambda: {"n": 0, "detected": 0, "false_alarm": 0, "examples": []})
    base_fail = 0

    def record(kind, text, fs, expect_fields, expect_extra=frozenset(), expect_over=frozenset()):
        st, extra, over = verdict(text, fs)
        want_st = {k: expect_fields.get(k, "correct") for k in st}
        detected = st == want_st and set(expect_extra) <= extra and over == set(expect_over)
        alarm = (any(st[k] != "correct" for k in st if k not in expect_fields)
                 or bool(extra - set(expect_extra)) or bool(over - set(expect_over)))
        r = res[kind]; r["n"] += 1; r["detected"] += detected; r["false_alarm"] += alarm
        if (not detected or alarm) and len(r["examples"]) < 3:
            r["examples"].append({"text": text, "got": [st, sorted(extra), sorted(over)]})

    for i, cid in enumerate(cases()):
        fs = finding_set(cid, predicted=i % 2 == 0)
        style = i % 3
        base = T.render(fs, style)
        st, extra, over = verdict(base, fs)
        if set(st.values()) != {"correct"} or extra or over:
            base_fail += 1
            continue
        for f in F.FIELDS:                                   # wrong value / omission
            wrong = copy.deepcopy(fs); wrong["findings"][f]["value"] = OTHER[f](fs["findings"][f]["value"])
            record(f"wrong {f}", T.render(wrong, style), fs, {f: "contradicted"})
            gone = copy.deepcopy(fs); gone["findings"][f] = None
            record(f"omitted {f}", T.render(gone, style), fs, {f: "omitted"})
        no_node = copy.deepcopy(fs); no_node["findings"]["node_status"] = None
        n = fs["findings"]["node_status"]["value"]
        record("overclaim node (unhedged)", T.render(no_node, style) + " " + UNHEDGED[n], fs, {},
               expect_over={"node_status"})
        for claim, sent in INSERT.items():                   # unsupported claims
            record(f"unsupported: {claim}", base + " " + sent, fs, {}, expect_extra={claim})
        record("control: abstention", base + " " + rng.choice(ABSTAIN), fs, {})
        # paraphrase controls: vocabulary unlike the templates, ONE dimension varied at a
        # time around a neutral sentence, so each failure is attributable
        v = {k: fs["findings"][k]["value"] for k in F.FIELDS}
        parts = {"type": "Adenocarcinoma" if v["histologic_type"] == "adenocarcinoma"
                 else "Mucinous adenocarcinoma",
                 "grade": f"G{v['grade']}", "t": f"pT{v['pt_stage']}",
                 "node": f"Nodal status is estimated as {'positive' if v['node_status'] else 'negative'}."}
        variants = ([("type", n, x) for n, x in enumerate(TYPE_P[v["histologic_type"]])] +
                    [("grade", n, f(v["grade"])) for n, f in GRADE_P.items()] +
                    [("t", n, f(v["pt_stage"])) for n, f in T_P.items()] +
                    [("node", n, f(v["node_status"])) for n, f in NODE_P.items()])
        for dim, name, val in variants:
            pp = dict(parts); pp[dim] = val
            text = f"{pp['type']}, {pp['grade']}, {pp['t']}. {pp['node']}"
            label = TYPE_P[v["histologic_type"]][name] if dim == "type" else name
            record(f"control: paraphrase {dim} as '{label}'", text, fs, {})
    return res, base_fail


def swap_text(text, field, old, new):
    if field == "grade":
        words = {1: "well", 2: "moderately", 3: "poorly"}
        t = re.sub(rf"\bG\s?{old}\b", f"G{new}", text)
        return re.sub(rf"\b{words[old]}([- ]?differentiated)", rf"{words[new]}\1", t, flags=re.I)
    if field == "pt_stage":
        return re.sub(rf"\b(p?\s?T\s?){old}(?=\s?[a-d]?\b)", rf"\g<1>{new}", text)
    if field == "histologic_type":        # adenocarcinoma -> mucinous only
        return re.sub(r"\badenocarcinoma\b", "mucinous adenocarcinoma", text, count=1, flags=re.I)


def suite_b():
    res = defaultdict(lambda: {"n": 0, "detected": 0, "false_alarm": 0, "skipped_base": 0})
    for cid in sorted(LABELS):
        if cid in GOLD:
            continue
        text = "\n".join((BASE / p).read_text(errors="ignore") for p in INDEX[cid]["reports"])
        fs = F.from_labels(LABELS[cid]["labels"])
        base_st, _, _ = verdict(text, fs)
        for f in ("grade", "pt_stage", "histologic_type"):
            v = fs["findings"][f]
            if v is None or (f == "grade" and v["value"] == 4) or \
               (f == "histologic_type" and v["value"] != "adenocarcinoma"):
                continue
            r = res[f"real report: wrong {f}"]
            if base_st[f] != "correct":
                r["skipped_base"] += 1; continue
            new = OTHER[f](v["value"]) if f != "histologic_type" else "mucinous"
            st, _, _ = verdict(swap_text(text, f, v["value"], new), fs)
            r["n"] += 1
            r["detected"] += st[f] == "contradicted"
            r["false_alarm"] += any(st[k] != base_st[k] for k in st if k != f)
    return res


def real_profile():
    counts, n = Counter(), 0
    for cid in sorted(LABELS):
        if cid in GOLD:
            continue
        text = "\n".join((BASE / p).read_text(errors="ignore") for p in INDEX[cid]["reports"])
        _, _, extra, _ = C.extract_claims(text)
        counts.update(list(extra)); n += 1
    return {k: round(v / n, 3) for k, v in counts.most_common()}, n


def main():
    a, base_fail = suite_a()
    b = suite_b()
    prof, n_real = real_profile()
    print(f"Suite A - template reports ({N_CASES} cases; {base_fail} base reports failed the "
          f"clean check and were skipped)\n")
    print(f"{'test':46s} {'n':>5s} {'detected':>9s} {'false alarm':>12s}")
    rows = {}
    for k in sorted(a, key=lambda k: (k.startswith("control"), k)):
        r = a[k]
        rows[k] = {"n": r["n"], "detected": r["detected"] / r["n"],
                   "false_alarm": r["false_alarm"] / r["n"], "examples": r["examples"]}
        label = "passed clean" if k.startswith("control") else "detected"
        print(f"{k:46s} {r['n']:5d} {r['detected'] / r['n']:9.1%} {r['false_alarm'] / r['n']:12.1%}")
    print("\n(for controls, 'detected' = correctly left unflagged)\n")
    print("Suite B - real reports, one value swapped in the text")
    for k, r in b.items():
        rows[k] = {"n": r["n"], "detected": r["detected"] / r["n"],
                   "false_alarm": r["false_alarm"] / r["n"], "skipped_base": r["skipped_base"]}
        print(f"{k:46s} {r['n']:5d} {r['detected'] / r['n']:9.1%} {r['false_alarm'] / r['n']:12.1%}"
              f"   (base not correct, skipped: {r['skipped_base']})")
    print(f"\nWhat real reports assert beyond the four fields ({n_real} reports, share mentioning):")
    for k, v in prof.items():
        print(f"  {k:26s} {v:6.1%}")
    (HERE / "planted_errors_results.json").write_text(json.dumps(
        {"suite_a": rows, "suite_a_base_failures": base_fail,
         "real_report_claim_profile": prof, "n_real_reports": n_real}, indent=1, default=str))
    print("\nwrote planted_errors_results.json")


if __name__ == "__main__":
    main()
