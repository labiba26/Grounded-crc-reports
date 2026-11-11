"""
train_stage1.py - train the reasoning stage: WSI features -> structured findings.

Stage 1 of the two-stage design. It does NOT generate text. It learns to predict
the clinical facts a report is built from, because those are the parts that can
be scored, calibrated and audited. Stage 2 conditions a language model on these
predicted fields (and their confidence) to write the narrative.

WHAT CHANGED IN THIS VERSION, AND WHY
The first full run trained for a fixed 30 epochs with no validation set. Training
loss fell from 5.47 to 0.042 - the model had memorised all 347 training cases -
and the reported numbers came from that final, most-overfit epoch. Three changes
make the evaluation trustworthy rather than merely favourable:

  1. VALIDATION SPLIT + EARLY STOPPING.
     A slice of the training cases is held out to decide *when to stop*. The
     weights restored for testing are those that scored best on validation, never
     the last epoch's. Without this, the number you report is measured at the
     point of worst overfitting.

  2. REPEATED SEEDS.
     With 60-90 test cases, a single run's balanced accuracy carries a 95%
     interval roughly +/-0.11 wide - one run cannot distinguish 0.64 from 0.53.
     Every figure is now the mean +/- standard deviation over several seeds, each
     with its own validation split and initialisation.

  3. CHANCE AS THE BASELINE, NOT THE MAJORITY RATE.
     Balanced accuracy weights every class equally, so the value it must beat is
     1/n_classes, not the majority-class frequency. Comparing balanced accuracy
     against the majority rate understates the model on imbalanced fields and
     flatters it on balanced ones. Both are printed; the verdict uses chance.

Stronger regularisation (higher dropout and weight decay) is applied by default
for the same reason - a ~1M-parameter head on 295 training cases will memorise
if allowed to.

OUTPUT FILES ARE PER-RUN, AND THE CONTROL MUST MATCH THE RUN IT CONTROLS
Every run used to write results_stage1.json and stage1_mil.pt regardless of what
it was, so the shuffled-label control silently overwrote the real run's results
and weights - leaving the headline numbers with no machine-readable record and no
checkpoint behind them. Output paths are now derived from the run: the real run
keeps results_stage1.json / stage1_mil.pt, and any other run writes its own
results_<tag>.json / stage1_mil_<tag>.pt. A run with --shuffle_labels can never
write the main paths, whatever tag it is given.

A control is only evidence if it differs from the real run in exactly one thing:
the label-image correspondence. Passing --match_config copies epochs, patience,
val_frac, max_patches, batch_size, lr, dropout, weight_decay and seeds out of a
finished run's results file, so the two differ only in the shuffling. Each results
file also records when it was written, on what host, at which git commit.

USAGE
    python3 train_stage1.py --seeds 5                 # the real run
    python3 train_stage1.py --smoke                   # plumbing check, seconds

    # the control, matched to the real run in every setting but the shuffle:
    python3 train_stage1.py --shuffle_labels --match_config results_stage1.json
"""

from __future__ import annotations

import argparse
import copy
import datetime
import gc
import json
import math
import random
import socket
import subprocess
from collections import Counter
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader

from models import GatedAttentionMIL
from wsi_dataset import (BASE, IGNORE, TASKS, CaseBagDataset, collate,
                         derive_targets, encode)

MAN = BASE / "dataset_manifests_final"
LABELS = json.loads((BASE / "stage1" / "structured_labels.json").read_text())


def split_ids(name):
    return [c["case_id"] for c in json.loads((MAN / f"{name}.json").read_text())]


def pick_device():
    if torch.cuda.is_available():
        return torch.device("cuda")
    if torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


def wilson(p, n, z=1.96):
    """95% interval for a proportion - honest error bars on small test sets."""
    if n == 0:
        return float("nan"), float("nan")
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return centre - half, centre + half


def labels_matrix(case_ids):
    """Class indices per case without touching the H5 files (fast)."""
    return torch.stack([encode(derive_targets(LABELS[c]["labels"])) for c in case_ids])


def class_weights(case_ids, device):
    """Inverse-frequency weights, computed on the training split only."""
    y = labels_matrix(case_ids)
    w = {}
    for ti, (task, classes) in enumerate(TASKS.items()):
        counts = Counter(int(v) for v in y[:, ti] if int(v) != IGNORE)
        freq = np.array([max(counts.get(c, 0), 1) for c in range(len(classes))],
                        dtype=np.float32)
        w[task] = torch.tensor(freq.sum() / (len(classes) * freq), device=device)
    return w


# A class with fewer than this many cases in a split cannot be measured
# meaningfully: its recall can only take a handful of values, yet balanced
# accuracy still gives it a full share of the average. Phase 8 found exactly one
# pT1 case in the COAD test split, so that single patient moves the pt_stage
# figure by a quarter regardless of how the model performs.
MIN_CLASS_N = 5


@torch.no_grad()
def evaluate(model, loader, device):
    """Returns {task: {n, acc, bal_acc, majority, per_class, bal_acc_min5}}."""
    model.eval()
    preds = {t: [] for t in TASKS}
    gold = {t: [] for t in TASKS}
    for b in loader:
        logits = model(b["features"].to(device), b["mask"].to(device))
        for ti, task in enumerate(TASKS):
            y = b["y"][:, ti]
            keep = y != IGNORE
            if keep.any():
                preds[task] += logits[task][keep.to(device)].argmax(-1).cpu().tolist()
                gold[task] += y[keep].tolist()

    out = {}
    for task in TASKS:
        g, p = np.array(gold[task]), np.array(preds[task])
        if len(g) == 0:
            continue
        # balanced accuracy = mean per-class recall, over classes actually present
        per_class = [float((p[g == c] == c).mean()) for c in np.unique(g)]
        counts = Counter(g.tolist())

        # Per-class recall with the support behind it. Without this, a class
        # carried by one or two patients is invisible inside the average.
        breakdown = []
        for ci, label in enumerate(TASKS[task]):
            sup = int(counts.get(ci, 0))
            breakdown.append({
                "class": label,
                "n": sup,
                "recall": float((p[g == ci] == ci).mean()) if sup else None,
            })

        # The same metric with thinly-populated classes left out, so pT and
        # grade can also be reported without one patient controlling the mean.
        big = [c for c in np.unique(g) if int((g == c).sum()) >= MIN_CLASS_N]
        out[task] = {
            "n": int(len(g)),
            "acc": float((g == p).mean()),
            "bal_acc": float(np.mean(per_class)),
            "majority": float(counts.most_common(1)[0][1] / len(g)),
            "per_class": breakdown,
            "bal_acc_min5": (float(np.mean([float((p[g == c] == c).mean())
                                            for c in big])) if big else None),
            "n_classes_min5": len(big),
        }
    return out


def mean_bal_acc(res):
    vals = [v["bal_acc"] for v in res.values()]
    return float(np.mean(vals)) if vals else 0.0


def make_loader(dataset, shuffle, args, device):
    return DataLoader(dataset, batch_size=args.batch_size, shuffle=shuffle,
                      collate_fn=collate, num_workers=args.num_workers,
                      pin_memory=(device.type == "cuda"),
                      persistent_workers=args.num_workers > 0)


def run_one_seed(seed, args, train_pool, test_ids, read_ids, device):
    """Train once with early stopping; return metrics from the BEST checkpoint.

    The four DataLoaders are built ONCE here and reused for every epoch. Building
    one per epoch (as an earlier version did) spawns a fresh set of persistent
    worker processes each time; their file handles accumulate until the OS limit
    is hit and training dies with "Too many open files" partway through a
    multi-seed run. Reusing the loaders is also faster, since workers are not
    respawned 60 times per seed.
    """
    random.seed(seed); np.random.seed(seed); torch.manual_seed(seed)

    # per-seed validation split, so the reported spread includes split variability
    pool = list(train_pool)
    random.Random(seed).shuffle(pool)
    n_val = max(1, int(round(args.val_frac * len(pool))))
    val_ids, tr_ids = pool[:n_val], pool[n_val:]

    train_labels = None
    if args.shuffle_labels:
        # permute which case gets which label, among training cases only.
        # Test and holdout keep their true labels.
        shuffled = list(tr_ids)
        random.Random(seed + 999).shuffle(shuffled)
        train_labels = dict(LABELS)
        for real, donor in zip(tr_ids, shuffled):
            train_labels[real] = LABELS[donor]

    mk = lambda ids_, train, lbl=None: CaseBagDataset(
        ids_, max_patches=args.max_patches, train=train, labels_dict=lbl)
    tr_loader = make_loader(mk(tr_ids, True, train_labels), True, args, device)
    va_loader = make_loader(mk(val_ids, False, train_labels), False, args, device)
    # an empty list means "do not evaluate here" - reg_sweep.py uses this so that the
    # test split cannot influence a model-selection decision even by accident
    te_loader = make_loader(mk(test_ids, False), False, args, device) if test_ids else None
    rd_loader = make_loader(mk(read_ids, False), False, args, device) if read_ids else None

    model = GatedAttentionMIL(tasks=TASKS, dropout=args.dropout,
                              hidden=getattr(args, "hidden", 512)).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=args.weight_decay)
    w = class_weights(tr_ids, device)
    crits = {t: nn.CrossEntropyLoss(weight=w[t], ignore_index=IGNORE) for t in TASKS}

    best_score, best_state, best_epoch, since = -1.0, None, 0, 0
    tr_eval = None
    try:
        for ep in range(1, args.epochs + 1):
            model.train()
            tot = n = 0
            for b in tr_loader:
                logits = model(b["features"].to(device), b["mask"].to(device))
                y = b["y"].to(device)
                # a task contributes loss only when the batch has a label for it;
                # otherwise CrossEntropyLoss divides by zero and returns NaN
                terms = [crits[t](logits[t], y[:, ti])
                         for ti, t in enumerate(TASKS) if (y[:, ti] != IGNORE).any()]
                if not terms:
                    continue
                loss = sum(terms)
                opt.zero_grad(); loss.backward(); opt.step()
                tot += float(loss.detach()); n += 1   # detach: this value is only printed

            score = mean_bal_acc(evaluate(model, va_loader, device))
            flag = ""
            if score > best_score:
                best_score, best_epoch, since = score, ep, 0
                best_state = copy.deepcopy(model.state_dict())
                flag = "  <- best"
            else:
                since += 1
            if args.verbose:
                print(f"    epoch {ep:3d}  train_loss {tot/max(n,1):.4f}  "
                      f"val_bal_acc {score:.3f}{flag}")
            if since >= args.patience:
                if args.verbose:
                    print(f"    early stop at epoch {ep} (no gain for {args.patience})")
                break

        model.load_state_dict(best_state)   # never report the last epoch
        result = {
            "seed": seed,
            "best_epoch": best_epoch,
            "val_bal_acc": best_score,
            "test_coad": evaluate(model, te_loader, device) if te_loader else None,
            "holdout_read": evaluate(model, rd_loader, device) if rd_loader else None,
        }
        if getattr(args, "eval_train", False):   # training-set fit, for the overfitting gap
            # built like the others, so it is shut down in `finally` like the others -
            # the first version left its persistent workers alive, and after 10 runs in one
            # process macOS ran out of file handles (reg_sweep.py, 26 Sep)
            tr_eval = make_loader(mk(tr_ids, False), False, args, device)
            result["train_fit"] = evaluate(model, tr_eval, device)
            result["train_fit_bal_acc"] = mean_bal_acc(result["train_fit"])
    finally:
        # shut the worker processes down before the next seed starts
        for ldr in (tr_loader, va_loader, te_loader, rd_loader, tr_eval):
            if ldr is None:
                continue
            try:
                if getattr(ldr, "_iterator", None) is not None:
                    ldr._iterator._shutdown_workers()
            except Exception:
                pass
        del tr_loader, va_loader, te_loader, rd_loader, tr_eval
        gc.collect()

    return result, model


def class_label(task, v):
    """Render a class the way a pathologist writes it."""
    if task == "pt_stage":
        return f"pT{v}"
    if task == "grade":
        return f"G{v}"
    return str(v)


def print_per_class(rows):
    """Per-class recall next to the number of cases behind it.

    Balanced accuracy weights every class equally, so a class holding one
    patient moves the average as much as one holding a hundred. Printing the
    support alongside makes that visible rather than leaving it to a footnote.
    """
    tasks = [t for t in rows if "per_class" in rows[t]]
    if not tasks:
        return
    print("\n--- per-class recall (n = cases of that class in this split) ---")
    for task in tasks:
        parts = []
        for c in rows[task]["per_class"]:
            name = class_label(task, c["class"])
            if c["recall_mean"] is None:
                parts.append(f"{name} n=0 --")
            else:
                flag = " (thin)" if c["thin"] else ""
                parts.append(f"{name} n={c['n']} {c['recall_mean']:.3f}{flag}")
        print(f"{task:16s} " + "   ".join(parts))
        if ("bal_acc_min5_mean" in rows[task]
                and rows[task]["n_classes_min5"] < len(rows[task]["per_class"])):
            r = rows[task]
            print(f"{'':16s} excluding thin classes: "
                  f"{r['bal_acc_min5_mean']:.3f} ± {r['bal_acc_min5_sd']:.3f} "
                  f"over {r['n_classes_min5']} classes "
                  f"(chance {r['chance_min5']:.3f})")
    print(f"'(thin)' marks a class with fewer than {MIN_CLASS_N} cases. Its recall can "
          f"only take\na few values, yet it still counts a full share of the balanced "
          f"accuracy above.\nReport these counts alongside the average.")


def report(name, per_seed, chance):
    print(f"\n=== {name} · {len(per_seed)} seed(s) ===")
    print(f"{'task':16s} {'n':>4s} {'bal.acc (mean±sd)':>19s} {'95% CI':>16s} "
          f"{'chance':>7s} {'major':>6s}  verdict")
    print("-" * 96)
    rows = {}
    for task in TASKS:
        vals = [s[task]["bal_acc"] for s in per_seed if task in s]
        if not vals:
            continue
        n = per_seed[0][task]["n"]
        m, sd = float(np.mean(vals)), float(np.std(vals))
        lo, hi = wilson(m, n)
        ch = chance[task]
        verdict = ("above chance" if lo > ch and m - sd > ch else
                   "borderline" if lo > ch or m - sd > ch else
                   "not above chance")
        rows[task] = {"n": n, "bal_acc_mean": m, "bal_acc_sd": sd,
                      "ci95": [lo, hi], "chance": ch,
                      "majority": per_seed[0][task]["majority"],
                      "acc_mean": float(np.mean([s[task]["acc"] for s in per_seed])),
                      "verdict": verdict}
        print(f"{task:16s} {n:4d}      {m:.3f} ± {sd:.3f}   [{lo:.3f},{hi:.3f}] "
              f"{ch:7.3f} {rows[task]['majority']:6.3f}  {verdict}")

        # per-class recall, averaged over seeds, with its support
        pcs = [s[task].get("per_class") for s in per_seed if task in s]
        if pcs and all(pcs):
            per_class_rows = []
            for i, entry in enumerate(pcs[0]):
                recs = [pc[i]["recall"] for pc in pcs
                        if pc[i]["recall"] is not None]
                per_class_rows.append({
                    "class": entry["class"],
                    "n": entry["n"],
                    "recall_mean": float(np.mean(recs)) if recs else None,
                    "recall_sd": float(np.std(recs)) if recs else None,
                    "thin": entry["n"] < MIN_CLASS_N,
                })
            rows[task]["per_class"] = per_class_rows

        m5 = [s[task]["bal_acc_min5"] for s in per_seed
              if task in s and s[task].get("bal_acc_min5") is not None]
        if m5:
            k = per_seed[0][task]["n_classes_min5"]
            rows[task]["bal_acc_min5_mean"] = float(np.mean(m5))
            rows[task]["bal_acc_min5_sd"] = float(np.std(m5))
            rows[task]["n_classes_min5"] = k
            rows[task]["chance_min5"] = (1.0 / k) if k else None

    print_per_class(rows)
    return rows


# settings a control run must share with the run it controls. Anything outside
# this list (num_workers, verbose, device) cannot change what the model learns.
MATCHABLE = ("seeds", "epochs", "patience", "val_frac", "max_patches",
             "batch_size", "lr", "dropout", "weight_decay", "hidden")


def resolve_run_tag(args):
    """Name this run. Controls and smoke tests get their own name by default so
    they cannot land on top of the real run's results."""
    if args.run_tag:
        return args.run_tag
    if args.smoke:
        return "smoke"
    if args.shuffle_labels:
        return "shuffled"
    return "main"


def run_paths(tag):
    d = BASE / "stage1"
    if tag == "main":
        # the canonical names, referenced by README.md and SERVER_SETUP.md
        return {"results": d / "results_stage1.json",
                "partial": d / "results_partial.json",
                "model": d / "stage1_mil.pt"}
    return {"results": d / f"results_{tag}.json",
            "partial": d / f"results_partial_{tag}.json",
            "model": d / f"stage1_mil_{tag}.pt"}


def apply_match_config(args, ref):
    """Copy the training settings out of a finished run's results file, so this
    run differs from it only in the thing being tested."""
    path = Path(ref)
    if not path.is_absolute():
        path = BASE / "stage1" / path
    if not path.exists():
        raise SystemExit(f"--match_config: no such file: {path}")
    cfg = json.loads(path.read_text()).get("config")
    if not cfg:
        raise SystemExit(f"--match_config: {path.name} has no 'config' block to match")
    if bool(cfg.get("shuffle_labels")) == bool(args.shuffle_labels):
        print(f"note: {path.name} was itself run with shuffle_labels="
              f"{bool(cfg.get('shuffle_labels'))}, the same as this run - "
              f"a control should match the run it is a control for.")
    taken = {}
    for k in MATCHABLE:
        if k in cfg:
            setattr(args, k, cfg[k])
            taken[k] = cfg[k]
    print(f"matched config from {path.name}: "
          + "  ".join(f"{k}={v}" for k, v in taken.items()))
    return path.name


def git_state(repo):
    """The commit a run started from, and whether the working tree matched it.

    A commit hash alone is not provenance. The Phase 9 reruns recorded 2c5a219,
    but ran with per-class reporting that was only in the working tree, not in
    that commit - so the hash pointed at code that could not have produced the
    file. `git_dirty_code` is True whenever a .py file differs from the commit,
    and `git_dirty_files` names every path that does, so a results file says
    plainly when its hash is not the whole story.
    """
    def run(*cmd):
        return subprocess.run(["git", *cmd], cwd=str(repo), capture_output=True,
                              text=True, timeout=10)
    try:
        head = run("rev-parse", "--short", "HEAD")
        status = run("status", "--porcelain")
    except Exception:
        return {"git_commit": None, "git_dirty_code": None, "git_dirty_files": None}
    if head.returncode != 0 or status.returncode != 0:
        return {"git_commit": None, "git_dirty_code": None, "git_dirty_files": None}
    files = sorted(line[3:].strip().strip('"') for line in status.stdout.splitlines()
                   if line.strip())
    return {
        "git_commit": head.stdout.strip() or None,
        "git_dirty_code": any(f.endswith(".py") for f in files),
        "git_dirty_files": files,
    }


def provenance(device):
    """Stamp each results file with enough to identify the run that made it."""
    return {
        "finished_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        **git_state(BASE),
        "host": socket.gethostname(),
        "torch": torch.__version__,
        "device": str(device),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=5, help="independent runs to average")
    ap.add_argument("--epochs", type=int, default=60, help="max epochs; early stopping usually stops sooner")
    ap.add_argument("--patience", type=int, default=8, help="epochs without val improvement before stopping")
    ap.add_argument("--val_frac", type=float, default=0.15, help="fraction of training cases held out to early-stop on")
    ap.add_argument("--max_patches", type=int, default=2048)
    ap.add_argument("--batch_size", type=int, default=8)
    ap.add_argument("--lr", type=float, default=2e-4)
    ap.add_argument("--dropout", type=float, default=0.4)
    ap.add_argument("--hidden", type=int, default=512, help="width of the MIL trunk")
    ap.add_argument("--weight_decay", type=float, default=1e-2)
    ap.add_argument("--num_workers", type=int, default=4)
    ap.add_argument("--verbose", action="store_true", help="print every epoch")
    ap.add_argument("--shuffle_labels", action="store_true",
                    help="CONTROL: randomly permute the training labels between cases. The "
                         "images no longer correspond to their findings, so a correct pipeline "
                         "must score at chance. Anything above chance means information is "
                         "leaking from somewhere it should not.")
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--run_tag", default=None,
                    help="name for this run's output files. Defaults to 'main' for a normal "
                         "run, 'shuffled' with --shuffle_labels, 'smoke' with --smoke. Only "
                         "the 'main' run writes results_stage1.json and stage1_mil.pt.")
    ap.add_argument("--match_config", default=None, metavar="RESULTS_JSON",
                    help="copy training settings from a finished run's results file so this "
                         "run differs from it only in what is being tested. Use it for the "
                         "shuffled-label control: --shuffle_labels --match_config results_stage1.json")
    args = ap.parse_args()

    matched_from = apply_match_config(args, args.match_config) if args.match_config else None

    tag = resolve_run_tag(args)
    if args.shuffle_labels and tag == "main":
        raise SystemExit(
            "refusing to write the real run's results and weights from a --shuffle_labels "
            "control. Drop --run_tag main, or give the control its own tag.")
    paths = run_paths(tag)

    train_pool, test_ids, read_ids = (split_ids("train_coad"), split_ids("test_coad"),
                                      split_ids("holdout_read"))
    if args.smoke:
        train_pool, test_ids, read_ids = train_pool[:10], test_ids[:4], read_ids[:4]
        args.seeds, args.epochs, args.patience, args.max_patches = 1, 2, 2, 256

    device = pick_device()
    print(f"train pool (COAD) {len(train_pool)}  ->  ~{int(len(train_pool)*(1-args.val_frac))} train "
          f"+ {int(len(train_pool)*args.val_frac)} val per seed")
    print(f"test (COAD) {len(test_ids)}   holdout (READ) {len(read_ids)}")
    print(f"device: {device}  workers: {args.num_workers}  seeds: {args.seeds}")
    print(f"dropout {args.dropout}  weight_decay {args.weight_decay}  "
          f"early stopping on val balanced accuracy (patience {args.patience})")
    print(f"run tag: {tag}"
          + ("   [CONTROL: training labels shuffled]" if args.shuffle_labels else ""))
    print(f"will write: {paths['results'].name}  {paths['model'].name}")

    chance = {t: 1.0 / len(c) for t, c in TASKS.items()}
    all_runs, best_model, best_val = [], None, -1.0
    for i in range(args.seeds):
        seed = 42 + i
        print(f"\n--- seed {seed} ({i+1}/{args.seeds}) ---")
        res, model = run_one_seed(seed, args, train_pool, test_ids, read_ids, device)
        print(f"    best epoch {res['best_epoch']}, val bal.acc {res['val_bal_acc']:.3f}")
        all_runs.append(res)
        if res["val_bal_acc"] > best_val:
            best_val, best_model = res["val_bal_acc"], model
        # checkpoint progress after each seed: a crash in seed 4 should not
        # discard seeds 1-3
        paths["partial"].write_text(json.dumps(
            {"run_tag": tag, "completed_seeds": len(all_runs), "per_seed": all_runs}, indent=2))

    test_rows = report("TEST (COAD, held out)", [r["test_coad"] for r in all_runs], chance)
    read_rows = report("HOLDOUT (READ, unseen cohort)", [r["holdout_read"] for r in all_runs], chance)

    print("\nRead the verdict column, not the raw number. 'chance' is what balanced")
    print("accuracy scores by guessing; 'major' is the majority-class rate, which is")
    print("the baseline for plain accuracy, not for balanced accuracy.")

    out = {
        "run_tag": tag,
        "is_control": bool(args.shuffle_labels),
        "matched_config_from": matched_from,
        "provenance": provenance(device),
        "config": vars(args),
        "n_seeds": args.seeds,
        "best_epochs": [r["best_epoch"] for r in all_runs],
        "test_coad": test_rows,
        "holdout_read": read_rows,
        "per_seed": all_runs,
    }
    paths["results"].write_text(json.dumps(out, indent=2))
    torch.save(best_model.state_dict(), paths["model"])
    print(f"\nsaved -> {paths['results'].name} (all seeds), "
          f"{paths['model'].name} (best by validation)")
    if args.shuffle_labels:
        print("These are CONTROL numbers: the training labels were shuffled, so the "
              "pipeline is sound only if they sit at chance. Do not report them as results.")


if __name__ == "__main__":
    main()
