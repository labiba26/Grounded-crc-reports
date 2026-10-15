"""
wsi_dataset.py - case-level multiple-instance dataset over UNI2-h features.

DESIGN NOTES (these are the thesis-relevant choices, not incidental code):

* THE BAG IS THE CASE, NOT THE SLIDE. A TCGA case can have several slides
  (e.g. TCGA-3L-AA1B has DX1 with 14,853 patches and DX2 with 8,133) but only
  one report. The report describes the case, so the model must see the whole
  case at once. Patches from all of a case's slides are concatenated into a
  single bag; `slide_ix` records which slide each patch came from so attention
  can still be mapped back per slide.

* PATCH BUDGET. Bags range from 328 to ~31,500 patches (mean ~6,100). At
  1536-d float32 a full bag can reach ~190 MB, which neither fits a laptop
  training loop nor is necessary. During training we draw a random subsample of
  `max_patches` (a free augmentation - the model sees a different view of the
  same slide each epoch). At eval time the subsample is deterministic (seeded
  per case) so numbers are reproducible.

* COORDS ARE KEPT. Every file stores patch coordinates at level 0 with a 512 px
  stride. They are returned alongside the features so attention weights can be
  painted back onto the slide as a heatmap - this is the evidence layer for the
  trustworthiness component, and it costs nothing to carry.

* LABELS MAY BE MISSING. Weak labels come from extract_fields.py and are None
  whenever the report does not state the field. Missing is encoded as -100 and
  the loss ignores it (see train_stage1.py). Missing is NOT negative.
"""

from __future__ import annotations

import json
import zlib
from pathlib import Path

import h5py
import numpy as np
import torch
from torch.utils.data import Dataset

BASE = Path(__file__).resolve().parent.parent
IGNORE = -100

# --------------------------------------------------------------------------- #
# Task definitions.
#
# Only fields that survived the quality audit are trained on. margins_involved
# is deliberately EXCLUDED: after tightening the regex it collapsed to 432
# negative / 1 positive, i.e. the extractor cannot find the (genuinely rare)
# positive cases in this OCR'd multi-institutional text. Training on it would
# just learn the majority class. lymphovascular_invasion is also excluded from
# the default task set - at 215 True / 53 False it is very likely over-called
# relative to the ~30-50% reported for colorectal cancer. Both are better done
# with an LLM extractor validated against a hand-labelled subset.
# --------------------------------------------------------------------------- #

SIDEDNESS = {
    "cecum": "right", "ascending": "right", "hepatic_flexure": "right",
    "transverse": "right",
    "splenic_flexure": "left", "descending": "left", "sigmoid": "left",
    "rectosigmoid": "rectal", "rectum": "rectal",
    "colon_nos": None,          # cannot infer a side from "colon" alone
}

# sidedness is DELIBERATELY NOT TRAINED. It is degenerate across these two
# cohorts: COAD supplies almost no "rectal" examples, while ~88% of the READ
# holdout is rectal by definition, so a model fitted on colon can never answer
# it there. The first run made this visible - READ sidedness scored 0.113
# accuracy but 0.555 balanced accuracy, because balanced accuracy averages
# per-class recall and a class with a handful of cases counts as much as one
# with 124. Reporting that 0.555 as a success would be misleading. The mapping
# is kept above so the field can still be analysed on COAD alone if wanted.
TASKS = {
    "mucinous":        [False, True],
    "grade":           [1, 2, 3],
    "pt_stage":        [1, 2, 3, 4],
    "node_positive":   [False, True],
}


def derive_targets(labels: dict) -> dict:
    """Map raw extracted fields onto the five trained tasks."""
    site = labels.get("tumour_site")
    htype = labels.get("histologic_type")
    return {
        "sidedness":     SIDEDNESS.get(site) if site else None,
        "mucinous":      None if htype is None else htype in ("mucinous", "signet_ring"),
        "grade":         labels.get("histologic_grade"),
        "pt_stage":      labels.get("pt_stage"),
        "node_positive": labels.get("lymph_node_positive"),
    }


def encode(targets: dict) -> torch.Tensor:
    """Class indices per task, IGNORE where the report did not state the field."""
    out = []
    for task, classes in TASKS.items():
        v = targets.get(task)
        out.append(classes.index(v) if v in classes else IGNORE)
    return torch.tensor(out, dtype=torch.long)


class CaseBagDataset(Dataset):
    def __init__(self, case_ids, index_path=None, labels_path=None,
                 max_patches=4096, train=True, return_text=False, labels_dict=None):
        index_path = index_path or BASE / "dataset_manifests_final" / "dataset_index.json"
        labels_path = labels_path or BASE / "stage1" / "structured_labels.json"

        by_id = {c["case_id"]: c for c in json.loads(Path(index_path).read_text())}
        # labels_dict lets a caller substitute labels (used by the shuffled-label
        # control, which must break the image-label link without touching anything else)
        self.labels = labels_dict if labels_dict is not None else json.loads(Path(labels_path).read_text())
        self.cases = [by_id[c] for c in case_ids if c in by_id]
        self.max_patches = max_patches
        self.train = train
        self.return_text = return_text

    def __len__(self):
        return len(self.cases)

    def __getitem__(self, i):
        case = self.cases[i]
        feats, coords, slide_ix = [], [], []

        for s_i, slide in enumerate(case["slides"]):
            with h5py.File(BASE / slide["path"], "r") as h:
                f = h["features"][0]          # (N, 1536), leading dim is always 1
                c = h["coords"][0]            # (N, 2) level-0 pixel coords
            feats.append(f)
            coords.append(c)
            slide_ix.append(np.full(len(f), s_i, dtype=np.int64))

        f = np.concatenate(feats); c = np.concatenate(coords)
        s = np.concatenate(slide_ix)

        if len(f) > self.max_patches:
            # random view while training, fixed view at eval so metrics repeat
            # zlib.crc32, not hash(): Python salts str hashes per process, so hash()
            # gave a DIFFERENT "fixed" view in every run (found 24 Sep, Phase 12)
            rng = np.random.default_rng(None if self.train else zlib.crc32(case["case_id"].encode()))
            keep = rng.choice(len(f), self.max_patches, replace=False)
            f, c, s = f[keep], c[keep], s[keep]

        item = {
            "features": torch.from_numpy(np.ascontiguousarray(f)),
            "coords": torch.from_numpy(np.ascontiguousarray(c)),
            "slide_ix": torch.from_numpy(s),
            "y": encode(derive_targets(self.labels[case["case_id"]]["labels"])),
            "case_id": case["case_id"],
            "cohort": case["cohort"],
        }
        if self.return_text:
            item["report"] = "\n".join((BASE / p).read_text(errors="ignore")
                                       for p in case["reports"])
        return item


def collate(batch):
    """Pad variable-length bags and return a validity mask."""
    n = max(b["features"].shape[0] for b in batch)
    d = batch[0]["features"].shape[1]
    feats = torch.zeros(len(batch), n, d)
    mask = torch.zeros(len(batch), n, dtype=torch.bool)
    for i, b in enumerate(batch):
        k = b["features"].shape[0]
        feats[i, :k] = b["features"]
        mask[i, :k] = True
    return {
        "features": feats,
        "mask": mask,
        "y": torch.stack([b["y"] for b in batch]),
        "case_id": [b["case_id"] for b in batch],
        "cohort": [b["cohort"] for b in batch],
    }
