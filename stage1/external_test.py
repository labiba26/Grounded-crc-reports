"""external_test.py - Stage 1 on CPTAC-COAD, a cohort it has never seen (THESIS_LOG.md).

A TEST SET. Run it once. Nothing here is tuned on CPTAC: the models, the calibration and
the label mapping (external/cptac_labels.py) were all fixed before the first run. If a
number looks wrong, find the bug and log it; do not change a setting to move the number.

Models scored (all already trained on TCGA only):
  cv_ensemble   PRIMARY. Mean of the 5 cross-validation fold models (cv/fold{k}.pt), each
                with the temperature from calibration.json - the same recipe that produced the
                Stage 2 inputs for the rectal holdout.
  seed44        stage1_mil.pt, the fixed-split model (trained on the 347 train cases).
  shuffled      stage1_mil_shuffled.pt, trained on shuffled labels - the empirical floor.
Both single models use the same temperatures (fitted on the fold models; an approximation).

Slide selections (external/cptac_labels.json): tumour_slides (PRIMARY, 47 patients) and
all_slides (sensitivity, 110 patients, bag = every slide, broken down by slide_group).
Grade is not in CPTAC, so it is not tested here. pT has no T1 in CPTAC: balanced accuracy is
over T2-T4, and the TCGA reference is recomputed over the same classes so they are comparable.

Known differences from TCGA, all reported, none corrected: different hospitals; features cut
by CLAM (512 px at 40x, downsampled) instead of TRIDENT (256 px at 20x) - same 128 um field;
cBioPortal lists the CPTAC specimens as frozen tissue (TCGA diagnostic slides are FFPE).

Writes stage1/external_cptac_results.json, stage1/external_cptac_logits.json,
       stage2/inputs/predictions_cptac.json (primary model, both selections).

    python3 external/cptac_labels.py          # once, stdlib only
    python3 stage1/external_test.py --smoke   # 1-minute plumbing check (5 patients)
    python3 stage1/external_test.py < /dev/null   # the real run, ~10-20 min on the Mac
"""
import argparse
import datetime
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

import h5py
import numpy as np
import torch

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
sys.path.insert(0, str(HERE))
import train_stage1 as T                      # noqa: E402
import calibrate as C                         # noqa: E402  (numpy only; main() not run)
from models import GatedAttentionMIL          # noqa: E402
from wsi_dataset import TASKS                 # noqa: E402

EXT_TASKS = ["mucinous", "pt_stage", "node_positive"]      # grade: no CPTAC label
N_BOOT, BOOT_SEED = 2000, 2026


def load(path, device):
    cfg = json.loads((HERE / "results_stage1.json").read_text())["config"]
    m = GatedAttentionMIL(tasks=TASKS, dropout=cfg["dropout"], hidden=cfg.get("hidden", 512))
    m.load_state_dict(torch.load(path, map_location="cpu"))
    return m.to(device).eval()


def softmax(z):
    z = np.asarray(z, float); z = z - z.max(-1, keepdims=True); e = np.exp(z)
    return e / e.sum(-1, keepdims=True)


def auroc(score, y):
    """Mann-Whitney AUROC with ties counted as half."""
    score, y = np.asarray(score, float), np.asarray(y, int)
    pos, neg = score[y == 1], score[y == 0]
    if len(pos) == 0 or len(neg) == 0:
        return None
    gt = (pos[:, None] > neg[None, :]).mean()
    eq = (pos[:, None] == neg[None, :]).mean()
    return float(gt + 0.5 * eq)


def bal_acc(pred, y, classes):
    rec = {classes[c]: float((pred[y == c] == c).mean()) for c in range(len(classes)) if (y == c).any()}
    return (float(np.mean(list(rec.values()))) if rec else None), rec


def task_metrics(P, y, classes, rng):
    """P: (n, k) probabilities, y: (n,) class indices."""
    pred = P.argmax(1)
    ba, rec = bal_acc(pred, y, classes)
    boots = []
    for _ in range(N_BOOT):
        i = rng.integers(0, len(y), len(y))
        b, _ = bal_acc(pred[i], y[i], classes)
        if b is not None:
            boots.append(b)
    out = {"n": int(len(y)), "bal_acc": ba,
           "bal_acc_95ci": [float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))],
           "per_class_recall": {str(k): {"n": int((y == classes.index(k)).sum()), "recall": v} for k, v in rec.items()},
           "predicted": {str(classes[c]): int((pred == c).sum()) for c in range(len(classes))},
           "true": {str(classes[c]): int((y == c).sum()) for c in range(len(classes))},
           "ece": C.ece(P, y), "mean_confidence": float(P.max(1).mean())}
    if len(classes) == 2:
        out["auroc"] = auroc(P[:, 1], y)
        au = []
        for _ in range(N_BOOT):
            i = rng.integers(0, len(y), len(y))
            a = auroc(P[i, 1], y[i])
            if a is not None:
                au.append(a)
        out["auroc_95ci"] = [float(np.percentile(au, 2.5)), float(np.percentile(au, 97.5))] if au else None
    return out


def score(probs, labels, ids, seed):
    rng = np.random.default_rng(seed)
    res = {}
    for t in EXT_TASKS:
        classes = TASKS[t]
        keep = [c for c in ids if labels[c][t] in classes]
        if not keep:
            continue
        P = np.stack([probs[c][t] for c in keep])
        y = np.array([classes.index(labels[c][t]) for c in keep])
        res[t] = task_metrics(P, y, classes, rng)
    return res


def tcga_reference():
    """TCGA out-of-fold COAD (434) and rectal ensemble (151), temperature-calibrated, scored the
    same way - pT restricted to T2-T4 so the numbers line up with CPTAC."""
    src = json.loads((BASE / "stage2" / "inputs" / "predictions_cv_calibrated.json").read_text())["cases"]
    out = {}
    for name, split in (("tcga_coad_oof", ("train_coad", "test_coad")), ("tcga_read_ensemble", ("holdout_read",))):
        probs, labels, ids = {}, {}, []
        for cid, rec in src.items():
            if rec["split"] not in split:
                continue
            ids.append(cid)
            probs[cid] = {t: np.array([rec[t]["temperature"]["probs"][str(k)] for k in TASKS[t]]) for t in EXT_TASKS}
            labels[cid] = {}
            for t in EXT_TASKS:
                i = C.target(cid, t)
                v = None if i is None else TASKS[t][i]
                labels[cid][t] = None if (t == "pt_stage" and v == 1) else v   # drop T1 to match CPTAC
        out[name] = score(probs, labels, ids, BOOT_SEED)
    return out


def feature_shift(bags, n_tcga=60):
    """How different do the two cohorts look to UNI2-h? Mean patch-feature norm and the cosine
    between the cohort centroids (1.0 = same centre). A description, not a correction."""
    def slide_stats(path):
        with h5py.File(BASE / path, "r") as h:
            f = np.asarray(h["features"][0], dtype=np.float32)
        return f.mean(0), float(np.linalg.norm(f, axis=1).mean()), len(f)
    idx = json.loads((BASE / "dataset_manifests_final" / "dataset_index.json").read_text())
    tc = [s["path"] for c in idx for s in c["slides"] if c["cohort"] == "COAD"]
    random.Random(0).shuffle(tc)
    cp = sorted({p for v in bags.values() for p in v})
    stats = {}
    for name, paths in (("tcga_coad", tc[:n_tcga]), ("cptac_coad", cp)):
        s = [slide_stats(p) for p in paths]
        stats[name] = {"slides": len(s), "centroid": np.mean([x[0] for x in s], 0),
                       "mean_patch_norm": float(np.mean([x[1] for x in s])),
                       "median_patches_per_slide": float(np.median([x[2] for x in s]))}
    a, b = stats["tcga_coad"].pop("centroid"), stats["cptac_coad"].pop("centroid")
    stats["centroid_cosine"] = float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b)))
    return stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true", help="5 patients, writes only *_smoke files")
    a = ap.parse_args()
    sfx = "_smoke" if a.smoke else ""
    L = json.loads((BASE / "external" / "cptac_labels.json").read_text())
    labels = {p: c["labels"] for p, c in L["cases"].items()}
    sel = L["selections"]
    if a.smoke:
        keep = sorted(sel["tumour_slides"])[:3] + sorted(set(sel["all_slides"]) - set(sel["tumour_slides"]))[:2]
        sel = {k: {p: v[p] for p in keep if p in v} for k, v in sel.items()}
    temps = {t: json.loads((HERE / "calibration.json").read_text())["params"][t]["temperature"]["T"] for t in TASKS}

    device = T.pick_device()
    models = {"cv_ensemble": [HERE / "cv" / f"fold{k}.pt" for k in range(5)],
              "seed44": [HERE / "stage1_mil.pt"], "shuffled": [HERE / "stage1_mil_shuffled.pt"]}
    models = {k: v for k, v in models.items() if all(p.exists() for p in v)}
    if "cv_ensemble" not in models:
        sys.exit("cv/fold0-4.pt not found - run crossval.py first (or copy the fold weights here)")
    print(f"device {device} · models {list(models)} · "
          + " · ".join(f"{k}: {len(v)} patients" for k, v in sel.items()), flush=True)

    # raw logits for every (selection, model file, patient); features read once per patient
    raw = {s: {m: defaultdict(list) for m in models} for s in sel}
    loaded = {m: [load(p, device) for p in paths] for m, paths in models.items()}
    patients = sorted({p for v in sel.values() for p in v})
    with torch.no_grad():
        for i, pid in enumerate(patients):
            feats = {}
            for s, bags in sel.items():
                if pid not in bags:
                    continue
                parts = []
                for path in bags[pid]:
                    if path not in feats:
                        with h5py.File(BASE / path, "r") as h:
                            feats[path] = np.asarray(h["features"][0], dtype=np.float32)
                    parts.append(feats[path])
                x = torch.from_numpy(np.concatenate(parts))[None].to(device)
                for m, ms in loaded.items():
                    for net in ms:
                        lg = net(x)
                        raw[s][m][pid].append({t: [float(v) for v in lg[t][0].cpu()] for t in TASKS})
            if (i + 1) % 10 == 0 or i + 1 == len(patients):
                print(f"  {i + 1}/{len(patients)} patients", flush=True)

    def probs_of(s, m):
        return {pid: {t: np.mean([softmax(np.array(r[t]) / temps[t]) for r in rs], 0) for t in TASKS}
                for pid, rs in raw[s][m].items()}

    results = {}
    for s in sel:
        results[s] = {}
        for m in models:
            pr = probs_of(s, m)
            results[s][m] = {"all": score(pr, labels, sorted(pr), BOOT_SEED)}
            if s == "all_slides":
                for g in sorted({L["cases"][p]["slide_group"] for p in pr}):
                    ids = [p for p in pr if L["cases"][p]["slide_group"] == g]
                    results[s][m][g] = score(pr, labels, ids, BOOT_SEED)
    ref = tcga_reference()
    shift = feature_shift(sel["all_slides"], n_tcga=10 if a.smoke else 60)

    print(f"\nbalanced accuracy [95% CI]   (grade not tested; pT over T2-T4)")
    print(f"{'':52s}" + "".join(f"{t:>24s}" for t in EXT_TASKS))
    def row(name, r):
        cells = []
        for t in EXT_TASKS:
            v = r.get(t)
            cells.append(f"{v['bal_acc']:.3f} [{v['bal_acc_95ci'][0]:.2f}-{v['bal_acc_95ci'][1]:.2f}]"
                         if v and v["bal_acc"] is not None else "-")
        print(f"{name:52s}" + "".join(f"{c:>24s}" for c in cells))
    for name, r in ref.items():
        row(f"TCGA ref: {name}", r)
    for s in sel:
        for m in models:
            for g, r in results[s][m].items():
                row(f"{s}/{m}" + ("" if g == "all" else f"/{g}"), r)
    print(f"\nAUROC  mucinous / node (primary: tumour_slides/cv_ensemble): "
          f"{results['tumour_slides']['cv_ensemble']['all']['mucinous'].get('auroc')} / "
          f"{results['tumour_slides']['cv_ensemble']['all']['node_positive'].get('auroc')}")
    print(f"feature shift: {json.dumps(shift)}")

    prov = {**T.provenance(device), "temperatures": temps, "models": {k: [str(p.relative_to(BASE)) for p in v]
                                                                       for k, v in models.items()}}
    (HERE / f"external_cptac_results{sfx}.json").write_text(json.dumps(
        {"cohort": "CPTAC-COAD (cBioPortal coad_cptac_2019 labels; IDC slide index)",
         "primary": "tumour_slides / cv_ensemble", "tasks": EXT_TASKS, "bootstrap": N_BOOT,
         "results": results, "tcga_reference": ref, "feature_shift": shift,
         "selection_sizes": {k: len(v) for k, v in sel.items()}, "provenance": prov}, indent=1))
    (HERE / f"external_cptac_logits{sfx}.json").write_text(json.dumps(
        {"note": "raw logits, one entry per model file", "logits": raw}, indent=0))
    cases = {}
    for s in sel:
        for pid, p in probs_of(s, "cv_ensemble").items():
            rec = {"cohort": "CPTAC-COAD", "selection": s, "in_training_set": False,
                   "prediction_source": "5-fold ensemble, temperature-calibrated",
                   "slides": sel[s][pid], "labels": labels[pid]}
            for t, classes in TASKS.items():
                j = int(np.argmax(p[t]))
                rec[t] = {"value": classes[j], "prob": round(float(p[t][j]), 4),
                          "probs": {str(cl): round(float(x), 4) for cl, x in zip(classes, p[t])}}
            cases[f"{pid}|{s}"] = rec
    (BASE / "stage2" / "inputs" / f"predictions_cptac{sfx}.json").write_text(json.dumps(
        {"meta": {"method": "5-fold CV ensemble, temperature-calibrated; keys are <patient>|<selection>",
                  "finished_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"), **prov},
         "cases": cases}, indent=1))
    print(f"\nwrote external_cptac_results{sfx}.json, external_cptac_logits{sfx}.json, "
          f"../stage2/inputs/predictions_cptac{sfx}.json" + ("  (SMOKE - not a result)" if a.smoke else ""))


if __name__ == "__main__":
    main()
