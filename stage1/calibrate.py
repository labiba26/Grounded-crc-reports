"""calibrate.py - calibrates Stage 1's probabilities (THESIS_LOG.md, Phase 12). numpy only.

Two methods, fitted per task on the cross-validation VALIDATION logits (cases each fold
model never trained on):
  temperature   logits / T            - fixes over/under-confidence; never changes the answer
  temp + bias   logits / T + b        - also shifts each class; CAN change the answer, which
                                        is what targets the pT4 / G3 over-prediction left by
                                        inverse-frequency class weighting
Scored on the out-of-fold COAD predictions (434) and the rectal 5-fold ensemble (151).

No leakage: for fold k's held-out cases, the calibration is re-fitted on validation logits
from which every fold-k case has been removed. The rectal cases are never in any validation
set. The exported parameters are fitted on all validation logits.

Writes calibration.json and ../stage2/inputs/predictions_cv_calibrated.json.

    python3 calibrate.py
"""
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
LABELS = json.loads((HERE / "structured_labels.json").read_text())
TASKS = {"mucinous": [False, True], "grade": [1, 2, 3], "pt_stage": [1, 2, 3, 4],
         "node_positive": [False, True]}


def target(cid, task):
    l = LABELS[cid]["labels"]
    v = {"mucinous": None if l["histologic_type"] is None else l["histologic_type"] in ("mucinous", "signet_ring"),
         "grade": l["histologic_grade"], "pt_stage": l["pt_stage"],
         "node_positive": l["lymph_node_positive"]}[task]
    return TASKS[task].index(v) if v in TASKS[task] else None


def softmax(z):
    z = z - z.max(-1, keepdims=True); e = np.exp(z); return e / e.sum(-1, keepdims=True)


def nll(p, y):
    return float(-np.mean(np.log(np.clip(p[np.arange(len(y)), y], 1e-12, 1))))


def fit(Z, y, bias):
    """Minimise NLL of softmax(Z/T + b). T on a grid (then refined); b by gradient descent."""
    k = Z.shape[1]
    best = (np.inf, 1.0)
    for T in np.exp(np.linspace(np.log(0.2), np.log(8), 80)):
        best = min(best, (nll(softmax(Z / T), y), T))
    T, b = best[1], np.zeros(k)
    if bias:
        onehot = np.eye(k)[y]
        for _ in range(3000):                      # joint refinement of 1/T and b
            p = softmax(Z / T + b)
            g = p - onehot                         # dNLL/dlogit
            b -= 0.05 * g.mean(0)
            invT = 1 / T - 0.01 * float((g * Z).mean(0).sum())
            T = 1 / max(invT, 1e-3)
        b -= b.mean()
    return float(T), b


def apply(Z, T, b):
    return softmax(Z / T + b)


def ece(p, y, bins=10):
    conf, pred = p.max(1), p.argmax(1)
    e, edges = 0.0, np.linspace(0, 1, bins + 1)
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (conf > lo) & (conf <= hi)
        if m.any():
            e += m.mean() * abs((pred[m] == y[m]).mean() - conf[m].mean())
    return float(e)


def bal_acc(p, y, k):
    pred = p.argmax(1)
    rec = [float((pred[y == c] == c).mean()) for c in range(k) if (y == c).any()]
    return float(np.mean(rec))


def metrics(p, y, k):
    return {"n": int(len(y)), "nll": nll(p, y), "ece": ece(p, y), "accuracy": float((p.argmax(1) == y).mean()),
            "bal_acc": bal_acc(p, y, k), "mean_confidence": float(p.max(1).mean()),
            "predicted": {str(TASKS_K[k][c]): int((p.argmax(1) == c).sum()) for c in range(k)},
            "true": {str(TASKS_K[k][c]): int((y == c).sum()) for c in range(k)}}


def main():
    L = json.loads((HERE / "crossval_logits.json").read_text())
    val, oof, read = L["val"], L["oof"], L["read"]
    global TASKS_K
    report, params = {}, {}
    for task, classes in TASKS.items():
        k = len(classes); TASKS_K = {k: classes}
        V = [(v["case_id"], np.array(v["logits"][task])) for v in val if target(v["case_id"], task) is not None]
        report[task] = {}
        for method, bias in (("raw", None), ("temperature", False), ("temp+bias", True)):
            # --- out-of-fold COAD, cross-fitted per fold
            P, Y = [], []
            for fold in range(5):
                held = [c for c, v in oof.items() if v["fold"] == fold and target(c, task) is not None]
                if not held:
                    continue
                Z = np.array([oof[c]["logits"][task] for c in held])
                if bias is None:
                    P.append(softmax(Z))
                else:
                    hs = set(held)
                    tr = [(c, z) for c, z in V if c not in hs]
                    T, b = fit(np.stack([z for _, z in tr]), np.array([target(c, task) for c, _ in tr]), bias)
                    P.append(apply(Z, T, b))
                Y += [target(c, task) for c in held]
            coad = metrics(np.concatenate(P), np.array(Y), k)
            # --- rectal ensemble, calibration fitted on all validation logits
            ids = [c for c in read if target(c, task) is not None]
            if bias is None:
                T, b = 1.0, np.zeros(k)
            else:
                T, b = fit(np.stack([z for _, z in V]), np.array([target(c, task) for c, _ in V]), bias)
            Pr = np.array([np.mean([apply(np.array([f[task]]), T, b)[0] for f in read[c]], 0) for c in ids])
            rect = metrics(Pr, np.array([target(c, task) for c in ids]), k)
            report[task][method] = {"coad_oof": coad, "read_ensemble": rect}
            if bias is not None:
                params.setdefault(task, {})[method] = {"T": T, "b": [float(x) for x in b]}

    print(f"{'task':14s} {'method':12s} | {'COAD 434: ECE':>13s} {'NLL':>6s} {'bal.acc':>7s} {'conf':>5s} |"
          f" {'READ: ECE':>9s} {'bal.acc':>7s} | predicted (COAD) vs true")
    for task, r in report.items():
        for method, m in r.items():
            c, rd = m["coad_oof"], m["read_ensemble"]
            print(f"{task:14s} {method:12s} | {c['ece']:13.3f} {c['nll']:6.3f} {c['bal_acc']:7.3f} "
                  f"{c['mean_confidence']:5.2f} | {rd['ece']:9.3f} {rd['bal_acc']:7.3f} | {c['predicted']} vs {c['true']}")
        print()

    # ---- export calibrated Stage 2 inputs (both versions kept side by side)
    src = json.loads((BASE / "stage2" / "inputs" / "predictions_cv.json").read_text())
    for cid, rec in src["cases"].items():
        for task, classes in TASKS.items():
            if cid in oof:
                Zs = [np.array(oof[cid]["logits"][task])]
            else:
                Zs = [np.array(f[task]) for f in read[cid]]
            for method in ("temperature", "temp+bias"):
                pr = params[task][method]
                p = np.mean([apply(z[None], pr["T"], np.array(pr["b"]))[0] for z in Zs], 0)
                j = int(p.argmax())
                rec[task][method] = {"value": classes[j], "prob": round(float(p[j]), 4),
                                     "probs": {str(cl): round(float(x), 4) for cl, x in zip(classes, p)}}
    src["meta"]["calibration"] = {"fitted_on": "cross-validation validation logits (all folds)",
                                  "methods": ["temperature", "temp+bias"], "params": params,
                                  "note": "top-level value/prob = uncalibrated; per-method blocks inside each task"}
    (BASE / "stage2" / "inputs" / "predictions_cv_calibrated.json").write_text(json.dumps(src, indent=1))
    (HERE / "calibration.json").write_text(json.dumps({"params": params, "report": report}, indent=1))
    print("wrote calibration.json and ../stage2/inputs/predictions_cv_calibrated.json")


if __name__ == "__main__":
    main()
