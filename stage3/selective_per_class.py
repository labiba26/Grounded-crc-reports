"""selective_per_class.py - item 2b: per-answer (class-aware) abstention thresholds.

THESIS_LOG.md, 29 Sep, "Improvement item 2b" (plan fixed before running). numpy only.

A predicted class c is stated only if its calibrated confidence >= t_c, where t_c is the lowest grid
value at which VALIDATION cases predicted as c (with confidence >= t_c) reach the target precision,
with at least MIN_PER_CLASS such cases; otherwise c is never stated. No fallback to the second class.
Cross-fitted per COAD fold exactly as selective_reporting.py. Compared side by side with item 2's rule.
Writes stage3/selective_per_class.json.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
sys.path.insert(0, str(BASE / "stage1")); sys.path.insert(0, str(HERE))
import calibrate as CAL            # noqa: E402
import selective_reporting as SR   # noqa: E402  (reuses softmax, GRID, pick_threshold, TASKS)

TARGETS = (0.95, 0.90, 0.80)
MIN_PER_CLASS = 5


def per_class_thresholds(P, y, target):
    pred, conf = P.argmax(1), P.max(1)
    out = []
    for c in range(P.shape[1]):
        t_c = None
        for t in SR.GRID:
            m = (pred == c) & (conf >= t)
            if m.sum() >= MIN_PER_CLASS and (y[m] == c).mean() >= target:
                t_c = float(t); break
        out.append(t_c)
    return out


def stated_mask(P, ths):
    pred, conf = P.argmax(1), P.max(1)
    t = np.array([ths[p] if ths[p] is not None else 2.0 for p in pred])
    return conf >= t


def summarise(P, y, st, classes):
    pred = P.argmax(1)
    ok = pred == y
    rec_all = [float((st & ok & (y == c)).sum() / (y == c).sum()) for c in range(len(classes)) if (y == c).any()]
    bal = [float((pred[st & (y == c)] == c).mean()) for c in range(len(classes)) if (st & (y == c)).any()]
    return {"n": int(len(y)), "coverage": float(st.mean()), "stated": int(st.sum()),
            "selective_accuracy": float(ok[st].mean()) if st.any() else None,
            "balanced_selective_accuracy": float(np.mean(bal)) if bal else None,
            "mean_recall_over_all_cases": float(np.mean(rec_all)),
            "per_class": {str(classes[c]): {"n": int((y == c).sum()),
                                            "stated": int((st & (y == c)).sum()),
                                            "stated_and_correct": int((st & ok & (y == c)).sum()),
                                            "recall": float((st & ok & (y == c)).sum() / (y == c).sum()) if (y == c).any() else None,
                                            "predicted_as_this_and_stated": int((st & (pred == c)).sum()),
                                            "precision_when_stated": float(ok[st & (pred == c)].mean()) if (st & (pred == c)).any() else None}
                          for c in range(len(classes))}}


def main():
    L = json.loads((BASE / "stage1" / "crossval_logits.json").read_text())
    val, oof, read = L["val"], L["oof"], L["read"]
    E = json.loads((BASE / "stage1" / "external_cptac_logits.json").read_text())["logits"]["tumour_slides"]["cv_ensemble"]
    CL = json.loads((BASE / "external" / "cptac_labels.json").read_text())["cases"]

    def cptac_target(pid, task):
        v = CL[pid]["labels"].get(task)
        return SR.TASKS[task].index(v) if v in SR.TASKS[task] else None

    result, per_case = {}, {}
    rules = {f"per_class_{a}": ("pc", a) for a in TARGETS}
    rules.update({f"overall_{a}": ("ov", a) for a in (0.90, 0.80)})

    for task, classes in SR.TASKS.items():
        V = [(v["case_id"], np.array(v["logits"][task])) for v in val if CAL.target(v["case_id"], task) is not None]

        def fit_on(pairs):
            Z = np.stack([z for _, z in pairs]); yv = np.array([CAL.target(c, task) for c, _ in pairs])
            T, _ = CAL.fit(Z, yv, False)
            Pv = SR.softmax(Z / T)
            th = {}
            for name, (kind, a) in rules.items():
                if kind == "pc":
                    th[name] = per_class_thresholds(Pv, yv, a)
                else:
                    t = SR.pick_threshold(Pv.max(1), Pv.argmax(1) == yv, a)
                    th[name] = [t] * len(classes)          # overall rule = same threshold for every class
            return T, th

        res = {}
        # COAD out-of-fold, cross-fitted
        P, Y, IDS, TH = [], [], [], {r: [] for r in rules}
        folds = []
        for k in range(5):
            held = [c for c, v in oof.items() if v["fold"] == k and CAL.target(c, task) is not None]
            T, th = fit_on([(c, z) for c, z in V if c not in set(held)])
            folds.append({"fold": k, "T": T, "thresholds": th})
            Pk = SR.softmax(np.array([oof[c]["logits"][task] for c in held]) / T)
            P.append(Pk); Y += [CAL.target(c, task) for c in held]; IDS += held
            for r in rules:
                TH[r] += [th[r]] * len(held)
        P, Y = np.concatenate(P), np.array(Y)
        coad = {"folds": folds, "no_abstention": summarise(P, Y, np.ones(len(Y), bool), classes)}
        for r in rules:
            st = np.array([stated_mask(P[i:i + 1], TH[r][i])[0] for i in range(len(Y))])
            coad[r] = summarise(P, Y, st, classes)
            for i, c in enumerate(IDS):
                per_case.setdefault(("coad", r), {}).setdefault(c, {})[task] = (bool(st[i]), bool(P[i].argmax() == Y[i]))
        res["coad_oof"] = coad
        # READ, CPTAC: fitted on all validation
        T, th = fit_on(V)
        res["fitted_on_all_validation"] = {"T": T, "thresholds": th}
        for name, ids, getz, gety in (
                ("read", [c for c in read if CAL.target(c, task) is not None],
                 lambda c: [np.array(f[task]) for f in read[c]], lambda c: CAL.target(c, task)),
                ("cptac", [p for p in E if cptac_target(p, task) is not None],
                 lambda p: [np.array(f[task]) for f in E[p]], lambda p: cptac_target(p, task))):
            if not ids:
                continue
            Pc = np.array([np.mean([SR.softmax(z / T) for z in getz(c)], 0) for c in ids])
            Yc = np.array([gety(c) for c in ids])
            block = {"no_abstention": summarise(Pc, Yc, np.ones(len(Yc), bool), classes)}
            for r in rules:
                st = stated_mask(Pc, th[r])
                block[r] = summarise(Pc, Yc, st, classes)
                for i, c in enumerate(ids):
                    per_case.setdefault((name, r), {}).setdefault(c, {})[task] = (bool(st[i]), bool(Pc[i].argmax() == Yc[i]))
            res[name] = block
        result[task] = res

    report_level = {}
    for (cohort, r), cases in sorted(per_case.items()):
        n_st = [sum(s for s, _ in f.values()) for f in cases.values()]
        wrong = [any(s and not ok for s, ok in f.values()) for f in cases.values()]
        report_level[f"{cohort}|{r}"] = {"n_cases": len(cases), "mean_fields_stated": float(np.mean(n_st)),
                                         "share_reports_with_a_wrong_finding": float(np.mean(wrong)),
                                         "share_reports_stating_nothing": float(np.mean([n == 0 for n in n_st]))}
    (HERE / "selective_per_class.json").write_text(json.dumps(
        {"plan": "THESIS_LOG.md 29 Sep item 2b, fixed before running", "targets": TARGETS,
         "min_per_class": MIN_PER_CLASS, "fields": result, "report_level": report_level}, indent=1))

    f = lambda v: "  - " if v is None else f"{v:.2f}"
    for task, res in result.items():
        print(f"\n=== {task}  thresholds (all validation): {res['fitted_on_all_validation']['thresholds']}")
        for cohort in ("coad_oof", "read", "cptac"):
            if cohort not in res:
                continue
            for r in ["no_abstention"] + list(rules):
                b = res[cohort][r]
                pc = " ".join(f"{k}:{v['stated_and_correct']}/{v['n']}(st{v['stated']})" for k, v in b["per_class"].items())
                print(f"  {cohort:8s} {r:15s} cov {f(b['coverage'])} acc {f(b['selective_accuracy'])} bal {f(b['balanced_selective_accuracy'])} | {pc}")
    print("\nreport level:")
    for k, v in report_level.items():
        print(f"  {k:24s} stated {v['mean_fields_stated']:.2f} wrong {v['share_reports_with_a_wrong_finding']:.3f} nothing {v['share_reports_stating_nothing']:.3f}")


if __name__ == "__main__":
    main()
