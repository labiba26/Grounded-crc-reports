"""export_predictions.py - run once on the Mac: everything Stage 2 needs from the slides.

Writes, into stage2/inputs/:
  predictions.json  per case: Stage 1's predicted class AND class probabilities for
                    mucinous, grade, pT and node status, from the saved checkpoint
                    (stage1_mil.pt - seed 44 since the 24 Sep rerun), all 590 cases.
  retrieval.json    per case: the nearest TRAINING case by cosine similarity of the
                    mean-pooled UNI2-h features - the image-conditioned ungrounded
                    baseline (Phase 11) writes that case's report.
After this, Stage 2 never needs the 23 GB of feature files.

Every bag is scored with ALL its patches (no subsampling), as in sensitivity_a6gc.py.

Cases in train_coad carry "in_training_set": true. Their predictions are OVERFIT (the
model was trained on them) and must never be used as test inputs - LoRA is trained on
the extracted findings instead (Phase 11, trap 1). Retrieval for a training case skips
the case itself. TCGA-NH-A6GC carries a note: one of its slides is metastatic.

    cd ~/TCGA_thesis/stage2
    python3 export_predictions.py < /dev/null        # ~10-15 min on the Mac
"""
import datetime
import json
import socket
import subprocess
import sys
from pathlib import Path

import h5py
import numpy as np
import torch

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
sys.path.insert(0, str(BASE / "stage1"))
from models import GatedAttentionMIL          # noqa: E402
from wsi_dataset import TASKS                  # noqa: E402

OUT = HERE / "inputs"
METASTATIC = {"TCGA-NH-A6GC": "one of its two slides is from a metastatic sample (06Z); "
                              "see THESIS_LOG.md, Phase 12"}


def split_of():
    out = {}
    for s in ("train_coad", "test_coad", "holdout_read"):
        for c in json.loads((BASE / "dataset_manifests_final" / f"{s}.json").read_text()):
            out[c["case_id"]] = s
    return out


def git_state():
    run = lambda *a: subprocess.run(["git", *a], cwd=BASE, capture_output=True, text=True).stdout
    try:   # no .strip() before splitting: porcelain lines start with a status column
        return {"git_commit": run("rev-parse", "--short", "HEAD").strip() or None,
                "git_dirty_files": [l[3:] for l in run("status", "--porcelain").splitlines() if l.strip()]}
    except Exception:
        return {"git_commit": None, "git_dirty_files": None}


def main():
    device = torch.device("mps" if torch.backends.mps.is_available()
                          else "cuda" if torch.cuda.is_available() else "cpu")
    model = GatedAttentionMIL(tasks=TASKS).to(device)
    ckpt = BASE / "stage1" / "stage1_mil.pt"
    model.load_state_dict(torch.load(ckpt, map_location=device))
    model.eval()
    index = json.loads((BASE / "dataset_manifests_final" / "dataset_index.json").read_text())
    split = split_of()
    OUT.mkdir(exist_ok=True)

    preds, pooled, ids = {}, [], []
    print(f"device {device} · {len(index)} cases, full bags")
    with torch.no_grad():
        for i, c in enumerate(index, 1):
            feats = []
            for s in c["slides"]:
                with h5py.File(BASE / s["path"], "r") as h:
                    feats.append(np.asarray(h["features"][0], dtype=np.float32))
            f = np.concatenate(feats)
            logits = model(torch.from_numpy(f)[None].to(device))
            rec = {}
            for task, classes in TASKS.items():
                p = torch.softmax(logits[task][0], -1).cpu().numpy()
                k = int(p.argmax())
                rec[task] = {"value": classes[k], "prob": round(float(p[k]), 4),
                             "probs": {str(cl): round(float(x), 4) for cl, x in zip(classes, p)}}
            cid = c["case_id"]
            preds[cid] = {"split": split.get(cid), "cohort": c["cohort"],
                          "in_training_set": split.get(cid) == "train_coad",
                          "n_patches": int(len(f)), **rec}
            if cid in METASTATIC:
                preds[cid]["note"] = METASTATIC[cid]
            m = f.mean(0)
            pooled.append(m / (np.linalg.norm(m) + 1e-8)); ids.append(cid)
            if i % 50 == 0:
                print(f"  {i}/{len(index)}")

    P = np.stack(pooled)
    train = [j for j, c in enumerate(ids) if split.get(c) == "train_coad"]
    sims = P @ P[train].T
    retrieval = {}
    for j, cid in enumerate(ids):
        order = np.argsort(-sims[j])
        best = next(train[k] for k in order if ids[train[k]] != cid)
        retrieval[cid] = {"neighbour": ids[best],
                          "similarity": round(float(sims[j][train.index(best)]), 4),
                          "neighbour_report": next(c["reports"] for c in index if c["case_id"] == ids[best])}

    meta = {"checkpoint": "stage1/stage1_mil.pt", "seed": 44, "device": str(device),
            "eval": "full bags, no subsampling", "host": socket.gethostname(),
            "torch": torch.__version__,
            "finished_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
            **git_state()}
    (OUT / "predictions.json").write_text(json.dumps({"meta": meta, "cases": preds}, indent=1))
    (OUT / "retrieval.json").write_text(json.dumps({"meta": {**meta, "method":
        "cosine similarity of mean-pooled UNI2-h features; neighbours drawn from train_coad only, "
        "never the case itself"}, "cases": retrieval}, indent=1))

    # a quick check that the export agrees with the rerun's test figures in direction
    from collections import Counter
    te = [c for c, r in preds.items() if r["split"] == "test_coad"]
    print(f"\nwrote {OUT.relative_to(BASE)}/predictions.json and retrieval.json")
    print("COAD test prediction mix:",
          {t: dict(Counter(str(preds[c][t]["value"]) for c in te)) for t in TASKS})


if __name__ == "__main__":
    main()
