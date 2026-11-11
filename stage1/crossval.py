"""crossval.py - 5-fold cross-validation over all 434 COAD cases (THESIS_LOG.md, Phase 12).

Why: the saved Stage 1 model has seen the 347 training cases, so its predictions for them
are overfit (0.86-0.96 balanced accuracy) and cannot feed Stage 2 as test inputs. Here every
COAD case is predicted by a model that NEVER trained on it (out-of-fold), so Stage 2 gets
honest predictions for 434 colon cases instead of 87. The rectal holdout is predicted by the
average of the 5 fold models (none of which saw a rectal case).

The fixed-split results in results_stage1.json remain Stage 1's headline. The cross-validated
figures are a second, larger-sample estimate of the same thing - they should agree roughly.

Folds are stratified by the mucinous label (the rarest class that matters). Each fold trains
exactly as train_stage1.py does (same settings, early stopping on a 15% validation split of
its own training part). With --use_sweep, the setting chosen by reg_sweep.py is applied.
The validation logits of every fold are saved for calibration (calibrate.py).

Every bag is scored with ALL its patches for the saved outputs.

Writes: crossval_results.json (metrics), crossval_logits.json (for calibration),
        ../stage2/inputs/predictions_cv.json (Stage 2 input, same format as predictions.json),
        cv/fold{k}.pt (weights; not in git).

    python3 crossval.py --use_sweep < /dev/null      # ~1-1.5 h on the Mac
"""
import argparse
import datetime
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

import h5py
import numpy as np
import torch

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
sys.path.insert(0, str(HERE))
import train_stage1 as T                         # noqa: E402
from wsi_dataset import TASKS, derive_targets    # noqa: E402

torch.multiprocessing.set_sharing_strategy("file_system")   # see reg_sweep.py

K = 5
FOLD_SEED = 2026
INDEX = {c["case_id"]: c for c in json.loads((BASE / "dataset_manifests_final" / "dataset_index.json").read_text())}


def settings(use_sweep):
    cfg = json.loads((HERE / "results_stage1.json").read_text())["config"]
    a = argparse.Namespace(**cfg)
    a.hidden = getattr(a, "hidden", 512)
    a.shuffle_labels, a.verbose, a.eval_train = False, False, False
    applied = {}
    if use_sweep and (HERE / "reg_sweep.json").exists():
        applied = json.loads((HERE / "reg_sweep.json").read_text())["choice_change"]
        for k, v in applied.items():
            setattr(a, k, v)
    return a, applied


def folds(coad):
    groups = defaultdict(list)
    for c in coad:
        groups[str(derive_targets(T.LABELS[c]["labels"])["mucinous"])].append(c)
    rng, out = random.Random(FOLD_SEED), {}
    i = 0
    for g in sorted(groups):
        members = sorted(groups[g]); rng.shuffle(members)
        for c in members:
            out[c] = i % K; i += 1
    return out


@torch.no_grad()
def logits_for(model, ids, device):
    model.eval()
    out = {}
    for cid in ids:
        parts = []
        for s in INDEX[cid]["slides"]:
            with h5py.File(BASE / s["path"], "r") as h:      # closed at once, never left to GC
                parts.append(np.asarray(h["features"][0], dtype=np.float32))
        f = np.concatenate(parts)
        lg = model(torch.from_numpy(f)[None].to(device))
        out[cid] = {t: [float(x) for x in lg[t][0].cpu()] for t in TASKS}
    return out


def softmax(v):
    v = np.asarray(v, dtype=float); e = np.exp(v - v.max()); return e / e.sum()


def bal_acc(pairs, classes):
    per = {}
    for ci, cl in enumerate(classes):
        sel = [p for g, p in pairs if g == ci]
        if sel:
            per[str(cl)] = {"n": len(sel), "recall": float(np.mean([p == ci for p in sel]))}
    return {"n": len(pairs), "bal_acc": float(np.mean([v["recall"] for v in per.values()])) if per else None,
            "per_class": per}


def score(probs, ids):
    out = {}
    for t, classes in TASKS.items():
        pairs = []
        for c in ids:
            g = derive_targets(T.LABELS[c]["labels"])[t]
            if g in classes:
                pairs.append((classes.index(g), int(np.argmax(probs[c][t]))))
        out[t] = bal_acc(pairs, classes) if pairs else {"n": 0, "bal_acc": float("nan"), "per_class": {}}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--use_sweep", action="store_true")
    ap.add_argument("--smoke", action="store_true",
                    help="2-minute plumbing check on 20 cases; writes only *_smoke files")
    a = ap.parse_args()
    args, applied = settings(a.use_sweep)
    sfx = "_smoke" if a.smoke else ""
    if a.smoke:
        args.epochs, args.patience, args.max_patches, args.num_workers = 2, 2, 256, 0
    device = T.pick_device()
    train_ids, test_ids, read_ids = (T.split_ids("train_coad"), T.split_ids("test_coad"),
                                     T.split_ids("holdout_read"))
    if a.smoke:
        train_ids, test_ids, read_ids = train_ids[:15], test_ids[:5], read_ids[:3]
    coad = train_ids + test_ids
    fold = folds(coad)
    print(f"{len(coad)} COAD cases in {K} folds · settings changed by the sweep: {applied or 'none'}",
          flush=True)
    (HERE / "cv").mkdir(exist_ok=True)

    oof, val_logits, read_logits, per_fold = {}, [], defaultdict(list), []
    for k in range(K):
        held = [c for c in coad if fold[c] == k]
        pool = [c for c in coad if fold[c] != k]
        seed = 42 + k
        print(f"--- fold {k + 1}/{K}: train on {len(pool)}, predict {len(held)}", flush=True)
        res, model = T.run_one_seed(seed, args, pool, [], [], device)
        torch.save(model.state_dict(), HERE / "cv" / f"fold{k}{sfx}.pt")
        shuffled = list(pool); random.Random(seed).shuffle(shuffled)       # same split as run_one_seed
        n_val = max(1, int(round(args.val_frac * len(shuffled))))
        vl = logits_for(model, shuffled[:n_val], device)
        val_logits += [{"case_id": c, "fold": k, "logits": v} for c, v in vl.items()]
        oof.update({c: {"fold": k, "logits": v} for c, v in logits_for(model, held, device).items()})
        for c, v in logits_for(model, read_ids, device).items():
            read_logits[c].append(v)
        per_fold.append({"fold": k, "seed": seed, "n_train_pool": len(pool), "n_heldout": len(held),
                         "best_epoch": res["best_epoch"], "val_bal_acc": res["val_bal_acc"]})
        print(f"    best epoch {res['best_epoch']}  val {res['val_bal_acc']:.3f}", flush=True)

    probs = {c: {t: softmax(v["logits"][t]) for t in TASKS} for c, v in oof.items()}
    probs.update({c: {t: np.mean([softmax(l[t]) for l in ls], 0) for t in TASKS}
                  for c, ls in read_logits.items()})
    metrics = {"coad_oof_all_434": score(probs, coad),
               "coad_oof_original_test_87": score(probs, test_ids),
               "coad_oof_original_train_347": score(probs, train_ids),
               "read_5fold_ensemble": score(probs, read_ids)}

    print(f"\n{'':30s} " + " ".join(f"{t:>14s}" for t in TASKS))
    for name, m in metrics.items():
        print(f"{name:30s} " + " ".join(f"{m[t]['bal_acc']:14.3f}" for t in TASKS))

    prov = {**T.provenance(device), "settings_changed_by_sweep": applied, "config": vars(args)}
    (HERE / f"crossval_results{sfx}.json").write_text(json.dumps(
        {"k": K, "fold_seed": FOLD_SEED, "stratified_by": "mucinous label", "per_fold": per_fold,
         "metrics": metrics, "provenance": prov}, indent=1))
    (HERE / f"crossval_logits{sfx}.json").write_text(json.dumps(
        {"note": "raw logits; val = each fold's early-stopping split (never trained on), "
                 "oof = held-out fold, read = one entry per fold model",
         "val": val_logits, "oof": oof, "read": read_logits}, indent=0))
    cases = {}
    for c, p in probs.items():
        rec = {"split": "holdout_read" if c in read_logits else ("train_coad" if c in train_ids else "test_coad"),
               "cohort": INDEX[c]["cohort"], "in_training_set": False,
               "prediction_source": "5-fold ensemble" if c in read_logits else f"out-of-fold (fold {oof[c]['fold']})"}
        for t, classes in TASKS.items():
            j = int(np.argmax(p[t]))
            rec[t] = {"value": classes[j], "prob": round(float(p[t][j]), 4),
                      "probs": {str(cl): round(float(x), 4) for cl, x in zip(classes, p[t])}}
        cases[c] = rec
    (BASE / "stage2" / "inputs").mkdir(parents=True, exist_ok=True)
    (BASE / "stage2" / "inputs" / f"predictions_cv{sfx}.json").write_text(json.dumps(
        {"meta": {"method": f"{K}-fold CV over COAD (out-of-fold); READ = mean of the {K} fold models",
                  "uncalibrated": True,
                  "finished_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
                  **prov}, "cases": cases}, indent=1))
    print(f"\nwrote crossval_results{sfx}.json, crossval_logits{sfx}.json, "
          f"../stage2/inputs/predictions_cv{sfx}.json" + ("  (SMOKE - not a result)" if a.smoke else ""))


if __name__ == "__main__":
    main()
