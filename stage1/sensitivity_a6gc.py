"""sensitivity_a6gc.py - is the colon test result carried by TCGA-NH-A6GC?

TCGA-NH-A6GC is the only case in the cohort with a slide from a METASTATIC sample
(sample type 06; every other slide is primary tumour, type 01). Its patches are
pooled with its primary-tumour slide into one bag. It is in the COAD test split, so
it never influenced training - the question is only whether it moves the test
figures, and whether its metastatic slide drives its own predictions.
(THESIS_LOG.md, Phase 12.)

Uses the saved checkpoint (stage1_mil.pt, the best-validation seed of the latest
run). The per-seed weights are not saved, so this is one model, not a 5-seed mean.
Every bag is evaluated with ALL its patches - no subsampling - so the result does not
depend on which patches a subsample happened to draw.

    python3 sensitivity_a6gc.py        # ~1-2 min on the Mac; writes sensitivity_a6gc.json
"""
import json
from pathlib import Path

import h5py
import numpy as np
import torch

from models import GatedAttentionMIL
from wsi_dataset import BASE, TASKS, derive_targets

CASE = "TCGA-NH-A6GC"
HERE = Path(__file__).resolve().parent
LABELS = json.loads((HERE / "structured_labels.json").read_text())
TEST = json.loads((BASE / "dataset_manifests_final" / "test_coad.json").read_text())

device = torch.device("mps" if torch.backends.mps.is_available()
                      else "cuda" if torch.cuda.is_available() else "cpu")
model = GatedAttentionMIL(tasks=TASKS).to(device)
model.load_state_dict(torch.load(HERE / "stage1_mil.pt", map_location=device))
model.eval()


def load(slides):
    f = [h5py.File(BASE / s["path"], "r")["features"][0] for s in slides]
    return [np.asarray(x, dtype=np.float32) for x in f]


@torch.no_grad()
def predict(feat_list):
    x = torch.from_numpy(np.concatenate(feat_list))[None].to(device)
    logits, attn = model(x, return_attention=True)
    probs = {t: torch.softmax(l[0], -1).cpu().numpy() for t, l in logits.items()}
    return probs, attn[0].cpu().numpy()


def gold(case_id):
    t = derive_targets(LABELS[case_id]["labels"])
    return {k: (TASKS[k].index(t[k]) if t.get(k) in TASKS[k] else None) for k in TASKS}


def metrics(preds):
    out = {}
    for task, classes in TASKS.items():
        pairs = [(g[task], int(np.argmax(p[task]))) for g, p in preds if g[task] is not None]
        if not pairs:
            continue
        g = np.array([a for a, _ in pairs]); pr = np.array([b for _, b in pairs])
        per = {str(classes[c]): {"n": int((g == c).sum()), "recall": float((pr[g == c] == c).mean())}
               for c in np.unique(g)}
        out[task] = {"n": len(pairs), "bal_acc": float(np.mean([v["recall"] for v in per.values()])),
                     "per_class": per}
    return out


def main():
    print(f"device {device} · checkpoint stage1_mil.pt · {len(TEST)} COAD test cases, full bags")
    preds, case_detail = [], {}
    for i, c in enumerate(TEST, 1):
        feats = load(c["slides"])
        probs, attn = predict(feats)
        preds.append((gold(c["case_id"]), probs, c["case_id"]))
        if c["case_id"] == CASE:
            names = [Path(s["path"]).name.split(".")[0] for s in c["slides"]]
            sizes = [len(f) for f in feats]
            edges = np.cumsum([0] + sizes)
            attn_share = {n: float(attn[edges[k]:edges[k + 1]].sum()) for k, n in enumerate(names)}
            variants = {"both slides (as evaluated)": probs}
            for k, n in enumerate(names):
                variants[f"{n} only"] = predict([feats[k]])[0]
            case_detail = {"slides": dict(zip(names, sizes)), "attention_share": attn_share,
                           "gold": {t: (TASKS[t][v] if v is not None else None)
                                    for t, v in gold(CASE).items()},
                           "predictions": {vn: {t: {str(TASKS[t][j]): round(float(p[j]), 3)
                                                    for j in range(len(TASKS[t]))}
                                                for t, p in pv.items()}
                                           for vn, pv in variants.items()}}
        if i % 20 == 0:
            print(f"  {i}/{len(TEST)}")

    with_case = metrics([(g, p) for g, p, _ in preds])
    without = metrics([(g, p) for g, p, cid in preds if cid != CASE])
    if not case_detail:
        raise SystemExit(f"{CASE} not found in the test split")

    print(f"\n=== COAD test, one checkpoint, full bags: with vs without {CASE} ===")
    print(f"{'task':15s} {'with':>18s} {'without':>18s} {'change':>8s}")
    for t in TASKS:
        a, b = with_case[t], without[t]
        print(f"{t:15s} {a['bal_acc']:.3f} (n={a['n']:3d})   {b['bal_acc']:.3f} (n={b['n']:3d})  "
              f"{b['bal_acc'] - a['bal_acc']:+.3f}")

    print(f"\n=== {CASE}: gold labels {case_detail['gold']} ===")
    print("slides (patches):", case_detail["slides"])
    print("attention share when pooled:",
          {k: round(v, 3) for k, v in case_detail["attention_share"].items()})
    for vn, pv in case_detail["predictions"].items():
        print(f"\n  {vn}")
        for t, p in pv.items():
            top = max(p, key=p.get)
            print(f"    {t:15s} -> {top:6s} {p}")

    out = {"checkpoint": "stage1_mil.pt", "device": str(device), "eval": "full bags, no subsampling",
           "with_case": with_case, "without_case": without, "case": case_detail}
    (HERE / "sensitivity_a6gc.json").write_text(json.dumps(out, indent=1))
    print("\nwrote sensitivity_a6gc.json")


if __name__ == "__main__":
    main()
