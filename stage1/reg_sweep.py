"""reg_sweep.py - does stronger regularisation narrow the overfitting gap? (THESIS_LOG.md, Phase 12)

Four settings x 3 seeds, all on the train_coad pool:
  baseline     the current Stage 1 configuration (copied from results_stage1.json)
  dropout0.6   dropout 0.4 -> 0.6
  hidden128    trunk width 512 -> 128 (about a quarter of the parameters)
  wd0.05       weight decay 0.01 -> 0.05
For each run it records VALIDATION balanced accuracy and TRAINING-set balanced accuracy
(the gap between them is the overfitting). THE TEST SPLIT AND THE RECTAL HOLDOUT ARE NEVER
EVALUATED HERE - run_one_seed is given empty lists for both - so this choice cannot be
tuned to the numbers the thesis reports.

DECISION RULE, fixed before any result exists:
  The validation split depends only on the seed, so each candidate is compared with the
  baseline seed by seed (paired). A candidate replaces the baseline only if its mean paired
  gain in validation balanced accuracy is at least 0.03 AND it beats the baseline on all 3
  seeds. Among qualifying candidates the largest mean gain wins. Otherwise: baseline.
  (0.03 is about one standard error of a 3-seed mean at the validation spread seen so far;
  the Phase 9 run-to-run drift was 0.014.)

    python3 reg_sweep.py < /dev/null      # ~2.5 h on the Mac; writes reg_sweep.json
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import train_stage1 as T      # noqa: E402
import torch                  # noqa: E402

# many training runs in one process: pass tensors between workers through the file
# system rather than file descriptors, so handles cannot pile up (26 Sep crash)
torch.multiprocessing.set_sharing_strategy("file_system")
PARTIAL = HERE / "reg_sweep_partial.json"

SEEDS = (42, 43, 44)
CANDIDATES = {"baseline": {}, "dropout0.6": {"dropout": 0.6}, "hidden128": {"hidden": 128},
              "wd0.05": {"weight_decay": 0.05}}
MIN_GAIN = 0.03


def base_args():
    cfg = json.loads((HERE / "results_stage1.json").read_text())["config"]
    a = argparse.Namespace(**cfg)
    a.hidden = getattr(a, "hidden", 512)
    a.shuffle_labels, a.verbose, a.eval_train = False, False, True
    return a


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true", help="2-minute plumbing check; writes reg_sweep_smoke.json")
    smoke = ap.parse_args().smoke
    device = T.pick_device()
    pool = T.split_ids("train_coad")[:14] if smoke else T.split_ids("train_coad")
    seeds = SEEDS[:2] if smoke else SEEDS
    cands = dict(list(CANDIDATES.items())[:2]) if smoke else CANDIDATES
    # resume: runs already finished (saved after each run) are not repeated
    runs = {} if smoke or not PARTIAL.exists() else json.loads(PARTIAL.read_text())
    for name, change in cands.items():
        runs.setdefault(name, [])
        for seed in seeds:
            if any(r["seed"] == seed for r in runs[name]):
                print(f"--- {name} seed {seed}: already done, skipped", flush=True)
                continue
            args = base_args()
            if smoke:
                args.epochs, args.patience, args.max_patches, args.num_workers = 2, 2, 256, 0
            for k, v in change.items():
                setattr(args, k, v)
            print(f"--- {name} seed {seed}", flush=True)
            res, _ = T.run_one_seed(seed, args, pool, [], [], device)
            runs[name].append({"seed": seed, "best_epoch": res["best_epoch"],
                               "val": res["val_bal_acc"], "train": res["train_fit_bal_acc"]})
            print(f"    val {res['val_bal_acc']:.3f}  train {res['train_fit_bal_acc']:.3f}  "
                  f"best epoch {res['best_epoch']}", flush=True)
            if not smoke:
                PARTIAL.write_text(json.dumps(runs, indent=1))

    base_val = {r["seed"]: r["val"] for r in runs["baseline"]}
    summary, qualifying = {}, {}
    for name, rs in runs.items():
        gains = [r["val"] - base_val[r["seed"]] for r in rs]
        summary[name] = {"val_mean": float(np.mean([r["val"] for r in rs])),
                         "train_mean": float(np.mean([r["train"] for r in rs])),
                         "gap_mean": float(np.mean([r["train"] - r["val"] for r in rs])),
                         "paired_gain_mean": float(np.mean(gains)),
                         "wins_all_seeds": all(g > 0 for g in gains)}
        if name != "baseline" and np.mean(gains) >= MIN_GAIN and all(g > 0 for g in gains):
            qualifying[name] = float(np.mean(gains))
    choice = max(qualifying, key=qualifying.get) if qualifying else "baseline"

    print(f"\n{'setting':12s} {'val':>7s} {'train':>7s} {'gap':>7s} {'gain vs base':>13s} {'all seeds':>10s}")
    for name, s in summary.items():
        print(f"{name:12s} {s['val_mean']:7.3f} {s['train_mean']:7.3f} {s['gap_mean']:7.3f} "
              f"{s['paired_gain_mean']:+13.3f} {str(s['wins_all_seeds']):>10s}")
    print(f"\nDECISION (rule: mean paired gain >= {MIN_GAIN} and better on every seed): {choice}")
    flags = " ".join(f"--{k} {v}" for k, v in CANDIDATES[choice].items())
    (HERE / ("reg_sweep_smoke.json" if smoke else "reg_sweep.json")).write_text(json.dumps(
        {"rule": f"mean paired val gain >= {MIN_GAIN} and positive on all seeds {list(SEEDS)}",
         "test_split_evaluated": False, "runs": runs, "summary": summary,
         "qualifying": qualifying, "choice": choice, "choice_change": CANDIDATES[choice],
         "choice_flags": flags, "smoke": smoke, "provenance": T.provenance(device)}, indent=1))
    print("wrote " + ("reg_sweep_smoke.json (SMOKE - not a result)" if smoke else "reg_sweep.json"))


if __name__ == "__main__":
    main()
