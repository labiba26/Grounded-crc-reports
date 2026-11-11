"""selective_reporting.py - state a finding only when Stage 1 is confident enough; otherwise abstain.

THESIS_LOG.md, 29 Sep, improvement item 2 (plan fixed before running). numpy only.

For each visible field (mucinous, grade, pT; node is always abstained), a finding is stated only if
its calibrated top-class probability >= a threshold. Thresholds and temperatures are fitted on the
cross-validation VALIDATION logits only (never on a test set); for COAD out-of-fold fold k they are
refitted without fold-k cases (cross-fitting). Operating points: lowest threshold whose validation
selective accuracy reaches 0.90 (and 0.80), with at least 10 stated validation cases.

Reports, per cohort (COAD OOF 434, READ 156, CPTAC tumour slides 47): coverage, selective accuracy,
balanced selective accuracy, per-class coverage and accuracy, full risk-coverage curve, AURC against
random abstention, and the report-level share of cases with any wrong stated finding.
Writes stage3/selective_reporting.json.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
sys.path.insert(0, str(BASE / "stage1"))
import calibrate as CAL   # noqa: E402  (numpy only; main() not run)

TASKS = {"mucinous": [False, True], "grade": [1, 2, 3], "pt_stage": [1, 2, 3, 4]}
TARGETS = (0.90, 0.80)
MIN_STATED = 10
GRID = np.round(np.arange(0.30, 1.0001, 0.01), 2)


def softmax(z):
    z = np.asarray(z, float); z = z - z.max(-1, keepdims=True); e = np.exp(z)
    return e / e.sum(-1, keepdims=True)


def pick_threshold(conf, correct, target):
    """Lowest grid threshold whose selective accuracy >= target with >= MIN_STATED stated."""
    for t in GRID:
        m = conf >= t
        if m.sum() >= MIN_STATED and correct[m].mean() >= target:
            return float(t)
    return None                                   # never reached: abstain always


def evaluate(P, y, t, classes):
    pred, conf = P.argmax(1), P.max(1)
    st = np.ones(len(y), bool) if t is None and False else (conf >= t if t is not None else np.zeros(len(y), bool))
    out = {"n": int(len(y)), "threshold": t, "coverage": float(st.mean()),
           "stated": int(st.sum()),
           "selective_accuracy": float((pred[st] == y[st]).mean()) if st.any() else None}
    rec = [float((pred[st & (y == c)] == c).mean()) for c in range(len(classes)) if (st & (y == c)).any()]
    out["balanced_selective_accuracy"] = float(np.mean(rec)) if rec else None
    out["per_class"] = {str(classes[c]): {"n": int((y == c).sum()),
                                          "stated": int((st & (y == c)).sum()),
                                          "coverage": float(st[y == c].mean()) if (y == c).any() else None,
                                          "correct_when_stated": float((pred[st & (y == c)] == c).mean()) if (st & (y == c)).any() else None}
                        for c in range(len(classes))}
    return out, st, pred


def risk_coverage(P, y):
    pred, conf = P.argmax(1), P.max(1)
    order = np.argsort(-conf, kind="stable")
    err = (pred[order] != y[order]).astype(float)
    k = np.arange(1, len(y) + 1)
    risk = np.cumsum(err) / k
    cov = k / len(y)
    aurc = float(risk.mean())
    rand = float(err.mean())                      # expected AURC of random abstention
    best = np.sort(err)                           # oracle: errors abstained first... (errors last)
    oracle = float((np.cumsum(best) / k).mean())
    pts = [{"coverage": float(cov[i]), "risk": float(risk[i])} for i in np.linspace(0, len(y) - 1, 21).astype(int)]
    return {"aurc": aurc, "aurc_random": rand, "aurc_oracle": oracle, "curve": pts}


def main():
    L = json.loads((BASE / "stage1" / "crossval_logits.json").read_text())
    val, oof, read = L["val"], L["oof"], L["read"]
    E = json.loads((BASE / "stage1" / "external_cptac_logits.json").read_text())["logits"]["tumour_slides"]["cv_ensemble"]
    CL = json.loads((BASE / "external" / "cptac_labels.json").read_text())["cases"]

    def cptac_target(pid, task):
        v = CL[pid]["labels"].get(task)
        return TASKS[task].index(v) if v in TASKS[task] else None

    result, per_case = {}, {}
    for task, classes in TASKS.items():
        V = [(v["case_id"], np.array(v["logits"][task])) for v in val if CAL.target(v["case_id"], task) is not None]
        def fit_on(pairs):
            Z = np.stack([z for _, z in pairs]); yv = np.array([CAL.target(c, task) for c, _ in pairs])
            T, _ = CAL.fit(Z, yv, False)
            Pv = softmax(Z / T)
            ths = {a: pick_threshold(Pv.max(1), Pv.argmax(1) == yv, a) for a in TARGETS}
            return T, ths
        res = {}
        # --- COAD out-of-fold, cross-fitted
        P, Y, TH, IDS = [], [], {a: [] for a in TARGETS}, []
        folds_info = []
        for k in range(5):
            held = [c for c, v in oof.items() if v["fold"] == k and CAL.target(c, task) is not None]
            T, ths = fit_on([(c, z) for c, z in V if c not in set(held)])
            folds_info.append({"fold": k, "T": T, "thresholds": ths})
            Pk = softmax(np.array([oof[c]["logits"][task] for c in held]) / T)
            P.append(Pk); Y += [CAL.target(c, task) for c in held]; IDS += held
            for a in TARGETS:
                TH[a] += [ths[a]] * len(held)
        P, Y = np.concatenate(P), np.array(Y)
        coad = {"folds": folds_info, "no_abstention": evaluate(P, Y, 0.0, classes)[0], "rc": risk_coverage(P, Y)}
        for a in TARGETS:
            th = np.array([t if t is not None else 2.0 for t in TH[a]])
            st = P.max(1) >= th
            tmp = {"coverage": float(st.mean()), "stated": int(st.sum())}
            pred = P.argmax(1)
            tmp["selective_accuracy"] = float((pred[st] == Y[st]).mean()) if st.any() else None
            rec = [float((pred[st & (Y == c)] == c).mean()) for c in range(len(classes)) if (st & (Y == c)).any()]
            tmp["balanced_selective_accuracy"] = float(np.mean(rec)) if rec else None
            tmp["per_class"] = {str(classes[c]): {"n": int((Y == c).sum()), "stated": int((st & (Y == c)).sum()),
                                                  "correct_when_stated": float((pred[st & (Y == c)] == c).mean()) if (st & (Y == c)).any() else None}
                                for c in range(len(classes))}
            coad[f"target_{a}"] = tmp
            for i, c in enumerate(IDS):
                per_case.setdefault(("coad", a), {}).setdefault(c, {})[task] = (bool(st[i]), bool(pred[i] == Y[i]))
        res["coad_oof"] = coad
        # --- READ and CPTAC: temperature and thresholds from ALL validation cases
        T, ths = fit_on(V)
        res["fitted_on_all_validation"] = {"T": T, "thresholds": ths}
        for name, ids, getz, gety in (
                ("read", [c for c in read if CAL.target(c, task) is not None],
                 lambda c: [np.array(f[task]) for f in read[c]], lambda c: CAL.target(c, task)),
                ("cptac", [p for p in E if cptac_target(p, task) is not None],
                 lambda p: [np.array(f[task]) for f in E[p]], lambda p: cptac_target(p, task))):
            if not ids:
                continue
            Pc = np.array([np.mean([softmax(z / T) for z in getz(c)], 0) for c in ids])
            Yc = np.array([gety(c) for c in ids])
            block = {"no_abstention": evaluate(Pc, Yc, 0.0, classes)[0], "rc": risk_coverage(Pc, Yc)}
            for a in TARGETS:
                ev, st, pred = evaluate(Pc, Yc, ths[a], classes)
                block[f"target_{a}"] = ev
                for i, c in enumerate(ids):
                    per_case.setdefault((name, a), {}).setdefault(c, {})[task] = (bool(st[i]), bool(pred[i] == Yc[i]))
            res[name] = block
        result[task] = res

    # report level: of the visible fields a case has labels for, how many are stated and is any wrong?
    report_level = {}
    for (cohort, a), cases in per_case.items():
        n_stated = [sum(s for s, _ in f.values()) for f in cases.values()]
        any_wrong = [any(s and not ok for s, ok in f.values()) for f in cases.values()]
        report_level[f"{cohort}_target_{a}"] = {"n_cases": len(cases), "mean_fields_stated": float(np.mean(n_stated)),
                                                "share_reports_with_a_wrong_finding": float(np.mean(any_wrong)),
                                                "share_reports_stating_nothing": float(np.mean([n == 0 for n in n_stated]))}
    for cohort in ("coad", "read", "cptac"):
        # no abstention: every labelled field stated
        cases = per_case.get((cohort, TARGETS[0]), {})
        if not cases:
            continue
    (HERE / "selective_reporting.json").write_text(json.dumps(
        {"plan": "THESIS_LOG.md 29 Sep, fixed before running", "targets": TARGETS, "min_stated": MIN_STATED,
         "fields": result, "report_level": report_level}, indent=1))

    f = lambda v: "  -  " if v is None else f"{v:.2f}"
    for task, res in result.items():
        print(f"\n=== {task}")
        for cohort in ("coad_oof", "read", "cptac"):
            if cohort not in res:
                continue
            b = res[cohort]; na = b["no_abstention"]; rc = b["rc"]
            print(f"  {cohort:9s} all stated: acc {f(na['selective_accuracy'])} bal {f(na['balanced_selective_accuracy'])} | "
                  f"AURC {rc['aurc']:.3f} (random {rc['aurc_random']:.3f}, oracle {rc['aurc_oracle']:.3f})")
            for a in TARGETS:
                t = b[f"target_{a}"]
                pc = " ".join(f"{k}:{v['stated']}/{v['n']}" for k, v in t["per_class"].items())
                print(f"     target {a}: coverage {f(t['coverage'])} acc {f(t['selective_accuracy'])} bal {f(t['balanced_selective_accuracy'])} | stated per class {pc}")
    print("\nreport level (visible fields):")
    for k, v in report_level.items():
        print(f"  {k:22s} fields stated {v['mean_fields_stated']:.2f}  reports with a wrong finding {v['share_reports_with_a_wrong_finding']:.2f}  stating nothing {v['share_reports_stating_nothing']:.2f}")
    print("\nwrote stage3/selective_reporting.json")


if __name__ == "__main__":
    main()
