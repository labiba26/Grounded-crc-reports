# Thesis working log

Everything decided, tried, broken and fixed — in order, in plain language.

**What this is for.** When you write the thesis, most of your Methods chapter is
"what we did and why", and most of your Limitations and Discussion chapters are
"what didn't work and how we know". That is exactly what is written down here.
Every entry ends with **→ goes in:** telling you which chapter it belongs to.

**Rule for this file:** anything that gets decided, breaks, or gets fixed goes in
here at the time it happens — not from memory in November.

Last updated: 24 September 2026, evening (Stage 1 rerun on corrected labels: mucinous
now transfers to the rectal cohort, node status sits near chance — Phase 12).
Earlier the same day (Stage 2 reframed as a grounded-vs-ungrounded
comparison, Phase 11. No pathologist reader study — the consistency metric is
validated by planted errors, GDC clinical data and double annotation instead; and
the slides are primary-tumour only, so nodal status is inferred, not seen; and GDC
exposed two label bugs, now fixed, which reopens Stage 1 for a rerun. Phase 12.
Stage 1 closed 10 September, Phase 9.)

---

## Quick reference — the numbers that matter

| | |
|---|---|
| Cases in final dataset | **590** (434 colon, 156 rectal) |
| Slides | 599 |
| Reports with real text | 592 of 594 (**99.7%**) |
| Split | 347 train / 87 test (colon) / **156 rectal held out entirely** |
| Patches per slide | 328 – 31,521 (mean 6,360) |
| Report length | median 1,215 characters (~300 words) |
| Feature size | 1,536 numbers per patch, UNI2-h, **frozen** |
| Trainable model | **1,056,524 parameters** (4 MB) |
| Feature data on disk | 23 GB (18 GB colon + 4.7 GB rectal) |

---

# Phase 0 — Choosing the data

### Decision: use pre-extracted features, not raw slide images

**The options.** (1) REG²/MICCAI challenge dataset, (2) raw TCGA slide images,
(3) TCGA with UNI2-h features already extracted.

**Why option 3.** Only 300 GB of disk was available. REG² is 2.1 TB of raw images,
and even a colon-only subset would have filled the disk entirely. More importantly,
REG² ships *raw images only* — so the expensive step of converting slides into
numbers would have had to be repeated, on a GPU, before any thesis work could start.
Raw TCGA slides have the same problem.

**What this buys.** The costly part (running a 600-million-parameter model over
gigapixel images) was already done by someone else. What remains is small enough
to train on a laptop.

**→ goes in:** Methods (dataset selection), and Introduction as a design rationale.

---

# Phase 1 — Assembling the dataset

### Bug: the slide-ID pattern matched nothing

The code that pulled a slide ID out of each filename expected a trailing letter on
the "portion" part of the TCGA barcode. Real barcodes never have one.

**Result:** it matched **0 of 600** filenames — silently. Nothing crashed; the field
was just empty everywhere.

**Fix:** corrected the pattern to match real barcodes.

**Lesson worth writing down:** the failure was silent. It produced empty values
rather than an error, so it would have gone unnoticed without a count.

**→ goes in:** Methods (footnote), or Discussion on validation practice.

### Bug: invented slide-to-report pairs

When a case had 2 slides and 2 reports, the old code produced **4 rows** — as if
each slide had been matched to each report. Those pairings were never verified and
do not exist in the data; GDC does not say which report belongs to which slide.

**Fix:** one row per slide, with all of that case's reports listed together. No
fabricated correspondence.

**→ goes in:** Methods (data structure). Good example of avoiding invented data.

### Bug: a feature array that wasn't the features

The code that inspected each feature file looked for "any 2-D array". Each file also
contains a `coords` array of shape (patches × 2) — the patch coordinates. That
matched the same rule, so coordinates were sometimes read as if they were the
1,536-dimensional features.

**Fix:** look for known feature key names first, and reject anything whose last
dimension is implausibly small for an embedding.

**→ goes in:** Methods footnote / Limitations on data validation.

---

# Phase 2 — Getting the report text

### Problem: we had file names, not words

The metadata from GDC listed 594 pathology report PDFs but contained **none of their
text**. Without the text there is nothing to pair the images with.

### Solution: match against a published corpus instead of OCR-ing

The TCGA-Reports corpus (Kefeli et al., *Patterns*, 2024) contains 9,523 TCGA
pathology reports already converted to text. Each report has a unique ID, and so do
ours, so they were matched **by exact ID** — no fuzzy matching, no guessing.

**Result: 543 of 594 matched (91.4%).** The remaining 51 were flagged, not ignored.

**→ goes in:** Methods (report text acquisition) + citation.

### Trap avoided: an older manifest that overcounted

An earlier version of the dataset claimed **591** usable cases. It counted a case as
usable if a report *PDF file existed* — even when nobody had read the text out of it.
The honest number was **543**: cases with features *and* readable text.

**Lesson:** be precise about what "usable" means. These numbers appear in your thesis.

**→ goes in:** Methods (be explicit about inclusion criteria).

---

# Phase 3 — Recovering the 51 missing reports

### Surprise: no OCR was needed

All 51 leftover PDFs turned out to have a **text layer** already, so the text could be
read directly. This is *cleaner* than the OCR behind the other 543.

### 2 of the 51 were not reports at all

They were **"TCGA Missing Pathology Report Form"** documents — official placeholders
saying no report was available, padded with scanned barcode noise. That is very likely
why the published corpus excluded them. Both were discarded.

**Result: 49 usable reports → 47 new cases. Dataset went 543 → 590.**

**→ goes in:** Methods (data recovery) + Limitations (2 cases excluded, with reason).

---

# Phase 4 — Turning reports into labels

The model needs to know the right answer for each case. Those answers are buried in
free text, so a program extracts them. These are **weak labels** — automatic, useful,
imperfect. Every field is allowed to be "not stated", and "not stated" is never
treated as "no".

### Current coverage (of 590 cases)

| Field | Coverage | Distribution | Used? |
|---|---|---|---|
| histologic_type | 94.2% | adeno 462 · mucinous 88 · signet-ring 6 | **yes** |
| tumour_site | 92.9% | colon NOS 107 · sigmoid 99 · cecum 94 · rectosigmoid 86 … | derived only |
| histologic_grade | 88.6% | G2 391 · G3 110 · G1 22 | **yes** |
| pt_stage | 84.1% | pT3 329 · pT2 98 · pT4 54 · pT1 15 | **yes** |
| lymph_node_positive | 78.3% | positive 317 · negative 145 | **yes** |
| pn_stage | 42.2% | pN1 115 · pN2 91 · pN0 42 · pN3 1 | cross-check only |
| lymphovascular_invasion | 50.2% | present 242 · absent 54 | **excluded** |
| margins_involved | 75.3% | clear 442 · involved 2 | **excluded** |

84% of cases carry at least 5 of the 8 fields.

### How label quality was measured (not just asserted)

`pn_stage` and `lymph_node_positive` describe the same thing in different words and
are extracted by completely separate rules. Clinically they must agree (pN0 means
node-negative). **They agree 95.2% of the time** across the 249 cases where both were
found.

That number is a *lower bound* on label quality for the nodal fields, and it is
evidence rather than opinion.

**→ goes in:** Methods (label extraction + validation). This is a strong paragraph.

### Failure: margin status cannot be extracted

**First attempt** found 89 cases with an involved surgical margin. Hand-checking a
random sample showed most were wrong. Example — TCGA-G4-6628 says
*"SURGICAL RESECTION MARGINS, NEGATIVE FOR TUMOR"*, but was labelled as involved.

**Cause:** OCR loses full stops, so two unrelated sentences run together:
*"…5 cm from the surgical margin there is a circular, ulcerated tumour… infiltrated"*
— which satisfies a "margin … infiltrated" pattern.

**Second attempt** (stricter) collapsed to **442 clear vs 1 involved** — now far too
few, since involved margins genuinely occur in a few percent of resections.

**Conclusion: margin status is not reliably extractable from this corpus by pattern
matching, in either direction. Excluded.** It would need an LLM-based extractor
validated against hand-labelled cases.

**→ goes in:** Limitations. This is a genuine finding, not a mistake to hide.

### Failure: lymphovascular invasion is over-called

The extractor found it "present" in 80% of cases. Published rates for colorectal
cancer are roughly 30–50%. Almost certainly over-counting. **Excluded.**

**→ goes in:** Limitations.

### Big catch: tick-box forms fool the extractor

After adding the 47 recovered cases, signet-ring carcinoma jumped from **7 to 35**
cases — about 6% of the cohort, when the real-world rate is around 1%.

**Cause.** Many recovered reports are printed forms, not prose:

```
Signet Ring Feature :  ( ) No   ( ) Yes   ( ) Yes (Focal)   ( ) Unknown
6. Mucinous Adenocarcinoma   7. Signet ring cell type Adenocarcinoma
```

The pathologist answers by **ticking a box**. The text layer carries the question and
every option — but not the tick, which is a mark on paper. So the extractor saw the
words "signet ring" and called it positive. **28 false positives**, heading straight
into training.

**Fix.** The extractor now detects (a) a "Yes/No" option run following a field label,
and (b) any document listing four or more mutually exclusive tumour types, and
returns "not stated" for those fields rather than guessing.

**Result: signet-ring back to 6 cases (1.0%)** — matching published incidence. Grade
was unaffected, because "Grade: Moderately Differentiated" states its value *after*
the label rather than listing options.

**→ goes in:** Methods (extraction safeguards) **and** Discussion. This is one of the
most interesting things in the project: a document-format problem masquerading as a
clinical finding.

---

# Phase 5 — The model

### What is actually being trained

| | Parameters | Trained? |
|---|---|---|
| UNI2-h (produced the features) | ~600,000,000 | **No — frozen, ran before this project** |
| Your attention model | **1,056,524** | **Yes — this is the whole thing** |

UNI2-h is not on the laptop. Only its *output* (23 GB of numbers) is. The two models
never run together: one finished its work before the other existed.

**Breakdown of the 1.06 M:**

| Piece | Parameters | Share |
|---|---|---|
| Compress each patch 1,536 → 512 | 786,944 | 74.5% |
| Attention (deciding which patches matter) | 262,913 | 24.9% |
| Normalisation | 1,024 | 0.1% |
| The four prediction heads | 5,643 | 0.5% |

### Why attention instead of averaging

A case has thousands of patches; the tumour may be in a few dozen. Averaging all of
them drowns the tumour in normal tissue. Attention scores each patch and takes a
weighted average, so important tissue dominates.

**Bonus:** every patch has coordinates stored in its file, so the attention scores can
be painted back onto the slide as a heatmap — showing which tissue drove each
prediction. That is the explainability component, obtained for free.

**→ goes in:** Methods (model architecture) + Discussion (explainability).

### Design choice: the bag is the case, not the slide

A case can have several slides but only one report. So all patches from all of a
case's slides go into one bag. Splitting is also done **by case**, so no patient
appears in both training and testing.

**→ goes in:** Methods. Preventing patient leakage is a point examiners look for.

### Bug: NaN loss

Some batches contained no labelled example for a given field. The loss function then
divided by zero and returned "not a number", corrupting the reported loss.

**Fix:** a field contributes to the loss only when the batch actually has a label for it.

**→ goes in:** Methods footnote.

---

# Phase 6 — First results, and what was wrong with them

**Setup:** 30 epochs, fixed. No validation set.

**Training loss fell from 5.47 to 0.042** — the model had memorised all 347 training
cases. And because there was no validation set, the reported results came from the
*final, most-overfitted* checkpoint.

| Field | COAD test | READ holdout |
|---|---|---|
| mucinous | 0.694 | 0.700 |
| node_positive | 0.638 | **0.504 (= chance)** |
| grade | 0.407 | 0.410 |
| pt_stage | 0.307 | 0.308 |

### Also wrong: the baseline being compared against

Balanced accuracy was initially compared to the **majority-class rate**. That is the
baseline for *plain* accuracy. Balanced accuracy weights every class equally, so its
baseline is **1 ÷ number of classes** (0.50 for yes/no, 0.33 for grade, 0.25 for pT).

**→ goes in:** Methods (evaluation metrics). Getting this right matters.

### The broken task: sidedness

Rectal holdout showed **accuracy 0.113 but balanced accuracy 0.555** — contradictory.

**Why.** 88% of rectal cases are labelled "rectal", and the model almost never
predicted it, so plain accuracy collapsed. But balanced accuracy averages each class
equally, so a class with a handful of cases counted as much as one with 124, and a few
lucky rare cases pulled the average up.

**Root cause:** the model trains on colon, where "rectal" barely appears as an answer,
so it never learns to say it. For rectal cases the answer is "rectal" by definition.

**The task is unanswerable across these cohorts. Dropped.**

**→ goes in:** Limitations + Discussion (a good worked example of why balanced accuracy
alone can mislead on very imbalanced classes).

---

# Phase 7 — Fixed methodology, and the real results

### What changed

1. **Validation split + early stopping.** 15% of training cases held out to choose when
   to stop; the tested weights are the best on validation, never the last epoch's.
2. **5 seeds.** With 66–151 test cases a single run's balanced accuracy has a 95%
   interval about ±0.11 wide — one run cannot separate 0.64 from 0.53.
3. **Chance baselines + 95% confidence intervals** printed for every field.
4. **Stronger regularisation** (dropout 0.25 → 0.4, weight decay 1e-4 → 1e-2).

### Bug on the way: "Too many open files"

A five-seed run crashed in seed 2. A fresh data loader was being created every epoch,
each spawning worker processes that stayed alive, until the operating system's file
limit was hit.

**Fix:** build the loaders once per seed and shut their workers down between seeds.
Also added per-seed checkpointing so a late crash never discards completed seeds.

**→ goes in:** nowhere in the thesis, but keep it here — it cost an hour.

### The results

Balanced accuracy, mean ± sd over 5 seeds:

| Field | COAD test (n) | READ holdout (n) | Chance | Verdict |
|---|---|---|---|---|
| **mucinous** | **0.758 ± 0.031** (81) | **0.646 ± 0.017** (151) | 0.500 | **works, both cohorts** |
| **node_positive** | 0.619 ± 0.023 (66) | **0.620 ± 0.025** (119) | 0.500 | **works, transfers perfectly** |
| grade | 0.409 ± 0.020 (78) | 0.413 ± 0.026 (139) | 0.333 | marginal — do not rely on it |
| pt_stage | 0.336 ± 0.021 (72) | 0.317 ± 0.021 (127) | 0.250 | not usable |

**Best epoch per seed: 6, 10, 6, 6, 10.** Consistent, so the stopping rule is
trustworthy. It also says something real: the model extracts what it can within about
ten passes, and everything after that is memorisation.

### What the fix bought

| Field | Before (overfit) | After |
|---|---|---|
| mucinous, colon | 0.694 | **0.758** |
| node_positive, rectal | **0.504 (chance)** | **0.620** |

Nodal status went from *nothing* to a real signal on the unseen cohort. Same data,
same model — only the training discipline changed.

**→ goes in:** Results, and a short Discussion section on why methodology matters.

### How to read these honestly

- **mucinous** is the headline. It drops from 0.758 to 0.646 on the unseen cohort —
  that gap is the honest generalisation cost. Report it; don't hide it.
- **node_positive** shows 0.619 vs 0.620 — no drop at all across cohorts. It reads
  "borderline" on colon only because 66 cases give a wider interval than 119 do.
- **grade** on rectal is technically above chance (interval starts at 0.334 against
  0.333). That is meaningless in practice. Do not build an argument on it.
- **pt_stage** genuinely fails. Likely reason: depth of invasion is decided at the
  invasive front — one specific place — and the model sees a random 2,048 of ~6,360
  patches, so it may never be shown the region holding the answer. **This suggests a
  real experiment:** sample more patches, or select rather than sample randomly.

**→ goes in:** Results + Discussion.

---

# Phase 8 — Verification and audit

Everything above was re-checked independently. This section is what you point at
when someone asks "how do you know this is right?"

### Integrity checks — all pass

| Check | Result |
|---|---|
| No case appears in two splits | pass |
| Splits cover the dataset exactly (590) | pass |
| No duplicate case IDs | pass |
| All 599 slide files and 592 report files present | pass |
| Labels cover exactly the manifest cases | pass |
| Every rectal case in the holdout, none in training | pass |
| No slide file used by two different cases | pass |

### The control that matters: shuffled labels

Randomly permute which training case gets which label, change nothing else, retrain.
Test and holdout keep their true labels. **A pipeline with no leakage must then score
at chance.**

| Field | Real labels | Shuffled labels | Chance |
|---|---|---|---|
| mucinous | **0.758** | **0.364** | 0.500 |
| grade | 0.409 | 0.339 | 0.333 |
| pt_stage | 0.336 | 0.315 | 0.250 |
| node_positive | 0.619 | 0.548 | 0.500 |

Mucinous collapses to *below* chance once the image-label link is broken. This is
direct evidence the signal is real, not leakage, not a metric artefact, not a bug.
Rerun any time with `--shuffle_labels`.

**→ goes in:** Methods (validation). Put this in — it forecloses the most obvious
criticism of the whole thesis.

### Problem found: pT stage has one case in a class

The colon test set contains **exactly 1 pT1 case**. Balanced accuracy averages the
four stages equally, so that single patient controls **25% of the metric** — getting
them right or wrong swings the score by a quarter. Grade has a milder version of the
same issue (6 G1 cases in test, 5 in holdout).

**The pT number is unstable regardless of how well the model performs.** Options:
report per-class recall with counts alongside the average; merge pT1 and pT2; or
exclude classes with fewer than 5 cases from the average and say so.

**→ goes in:** Limitations, and fix the reporting before writing up Results.

### Problem found: the split is not stratified

Splitting was random at case level, so class balance drifts between train and test.
Grade G3 is **27% of training cases but only 12% of test**.

Either stratify on the primary task when splitting, or state plainly in Methods that
the split was random at case level and show the class distributions per split.

**→ goes in:** Methods (be explicit) or fix by re-splitting.

### Naming point

The task called `mucinous` actually treats **mucinous OR signet-ring** as positive —
94 positive cases, not 88. Call it "mucinous or signet-ring histology" in the write-up.

**→ goes in:** Methods.

### Checked: does the model see only the tumour, or the whole slide?

You asked whether Stage 1 is only looking at tumour tissue or at tumour and
non-tumour tissue together. Opened the actual feature files on disk to check,
rather than answer from memory.

Each slide's `.h5` file (produced before this project, by the group that ran the
UNI2-h feature extraction) has an `annots` array alongside the features — one entry
per patch, same length as the patch count. Checked it across 15 slides from both
cohorts: it is **all zeros in every file, for every patch.** No tumour/non-tumour
label was ever attached to a patch. There is no tumour-only crop and no tissue mask
beyond ordinary background removal.

Patch counts per slide range from about 950 to over 13,000 (whole tissue area,
size varies slide to slide) — consistent with "every patch of tissue on the
slide," not a small tumour-only region.

**Answer: the model sees both.** Every case's bag of patches mixes tumour, normal
colon/rectal tissue, and some stroma/background, all together. Nothing tells the
model in advance which patches are tumour. This is exactly why the attention
mechanism matters (see Phase 5) — it is the part of the model that has to learn,
from the training labels alone, to weight tumour-relevant patches more heavily.
A model that only ever saw pre-cropped tumour patches would not need attention to
do this; it would already have been done by hand.

Practical note: if a future direction wants tumour-only analysis (e.g. comparing
tumour-region attention against a pathologist's annotation), that would need a
separate tumour segmentation step — a different, heavier piece of work, not
something already implicit in the current pipeline.

**→ goes in:** Methods (describe patch extraction as whole-slide, not tumour-only)
and Discussion (attention as the mechanism that finds tumour-relevant patches
without supervision).

---

# Phase 9 — The control had overwritten the results

Found on 10 September while re-reading the repository, not while running anything.

### Problem: `results_stage1.json` was not the results

The file on disk had `"shuffle_labels": true` and `"seeds": 1`. It was the
**shuffled-label control** from Phase 8, not the five-seed run from Phase 7.
`stage1_mil.pt` carried the same timestamp, so the saved weights were the control's
too.

**Cause.** `train_stage1.py` wrote to three fixed paths — `results_stage1.json`,
`results_partial.json`, `stage1_mil.pt` — no matter what the run was. The control
was run after the real run, so it landed on top of it. Nothing warned; the numbers
inside simply changed.

**What was lost.** The headline figures (mucinous 0.758 / 0.646, node_positive
0.619 / 0.620) survive **only as prose** in this log and the README. There is no
machine-readable record behind them, and no trained checkpoint — which Stage 3
needs, since the attention heatmaps have to come from actual weights.

**Lesson worth writing down:** the same silent-failure shape as the barcode bug in
Phase 1 and the coords-as-features bug in Phase 1. Nothing crashed. A file that was
supposed to hold one thing quietly held another. Results that only exist as a
sentence in a document are not results yet.

**→ goes in:** nowhere in the thesis directly, but it is why Results must be written
from a checked-in results file rather than from notes.

### Problem: the control was not a matched control

Phase 8 prints "Real labels" and "Shuffled labels" side by side, which reads as one
experiment run twice. The two runs actually differed in four settings:

| Setting | Real run | Control as run |
|---|---|---|
| seeds | 5 | 1 |
| epochs | 60 (early stopping) | 8 |
| patience | 8 | 3 |
| max_patches | 2048 | 512 |

The control's *argument* still holds — mucinous collapsing to 0.364, below chance,
is not something leakage explains. But a control is only evidence about the run it
controls if it differs from it in exactly one thing, and this one differed in five.
An examiner reading that table will ask why the patch budget changed, and the honest
answer right now is that it was not deliberate.

**→ goes in:** Methods (validation). Rerun before the table goes in the thesis.

### Fix: output paths are derived from the run

`train_stage1.py` now names its own outputs. A normal run keeps
`results_stage1.json` / `stage1_mil.pt`; anything else writes
`results_<tag>.json` / `stage1_mil_<tag>.pt`, with the tag defaulting to
`shuffled` for a control and `smoke` for a plumbing check. A run with
`--shuffle_labels` **cannot** write the real run's filenames even if told to.

`--match_config results_stage1.json` copies seeds, epochs, patience, val_frac,
max_patches, batch_size, lr, dropout and weight_decay out of a finished run, so the
control differs from it in one thing only. Each results file now also records the
time, host, torch version and git commit that produced it, so no results file is
ever anonymous again.

Verified by `stage1/test_run_paths.py` (20 checks, about a second, no torch or
feature files needed): tag derivation, path separation across four run types, the
refusal to overwrite the real run from a control, config matching reducing the
difference to `shuffle_labels` alone, and a clear error rather than a silent skip
when `--match_config` is pointed at a missing or malformed file.

The old control's numbers are kept in `results_shuffled_unmatched.json` so the
Phase 8 table stays traceable, and `results_stage1.json` carries a warning at the
top of it until the real run is rerun.

**→ goes in:** Methods footnote (reproducibility), if anywhere. Mainly it is here so
the same thing cannot happen twice.

### Still to do: rerun both

Neither run can happen on this laptop's Linux side, and both need the features. On
the college server, or on the Mac with the environment that produced the originals:

```bash
cd stage1
python3 train_stage1.py --seeds 5                                          # ~restores Phase 7
python3 train_stage1.py --shuffle_labels --match_config results_stage1.json  # matched control
```

Expect the real run to reproduce Phase 7 closely but not exactly — the seeds are the
same (42–46) but library and hardware differences move balanced accuracy by a little.
**If it comes back materially different, that is itself a finding and belongs in this
log.** The control must land near chance; if it does not, stop and investigate before
anything else.

**→ goes in:** Results (regenerated numbers replace the ones quoted in Phase 7).

### Correction to the above: the numbers were recoverable, the checkpoint was not

Written later the same day, after checking rather than assuming. Phase 9 says the
headline figures "survive only as prose ... there is no machine-readable record
behind them". **That part was wrong.** The real five-seed `results_stage1.json` was
committed to git on 7 September at 17:35 (commit `ba9fb74`), before the control
overwrote the working copy that evening. It was recovered with

```bash
git show ba9fb74:stage1/results_stage1.json > stage1/results_stage1.json
```

and the restored file matches the quoted figures exactly — mucinous 0.758 / 0.646,
node_positive 0.619 / 0.620, best epochs [6, 10, 6, 6, 10]. Committed as `017eb99`.

**The checkpoint claim, however, was right, and is now proven rather than inferred.**
`stage1_mil.pt` was loaded and evaluated directly on the 87-case COAD test split:

| Field | Saved checkpoint scores | Real Phase 7 run | Control run |
|---|---|---|---|
| mucinous | **0.3641** | 0.758 | 0.3641 |
| grade | 0.3386 | 0.409 | 0.3386 |
| pt_stage | 0.3149 | 0.336 | 0.3149 |
| node_positive | 0.5483 | 0.619 | 0.5483 |

Every figure matches the control to four decimal places. The weights on disk are the
shuffled-label control's, not the real model's. Timestamps agree: the checkpoint was
written 7 Sep at 20:12:42, twenty-four seconds before the control was committed at
20:13:06, and nearly three hours after the real run was committed at 17:35.

**So: the results are safe, the model is not.** Stage 3 needs real attention weights,
so the rerun above is genuinely required — not for the numbers, but for the
checkpoint.

**Lesson:** a timestamp is not provenance. The file looked untouched because its date
sat in the right place; only running it settled the question. This is why every
results file now records host, torch version and git commit.

**→ goes in:** Methods (provenance discipline); Limitations if the rerun's numbers
differ from Phase 7.

### The rerun was attempted and died at seed 3 of 5

`nohup caffeinate -is python3 -u train_stage1.py --seeds 5 > run_main.log 2>&1 &`
completed seed 42 (best epoch 6, val 0.617) and seed 43 (best epoch 2, val 0.612),
then failed on seed 44:

```
Fatal Python error: init_sys_streams: can't initialize sys standard streams
OSError: [Errno 9] Bad file descriptor
BrokenPipeError: [Errno 32] Broken pipe   (while spawning a DataLoader worker)
```

**Cause.** Not the earlier file-descriptor leak — that fix held. `stdin` was left
attached to the terminal. macOS spawns DataLoader workers with `spawn`, and a spawned
child needs valid standard streams; once the terminal went away, the next worker
could not start. Seeds 42 and 43 survived only because their workers were created
while the terminal still existed.

**Fix — detach stdin as well as stdout:**

```bash
nohup caffeinate -is python3 -u train_stage1.py --seeds 5 < /dev/null > run_main.log 2>&1 &
```

**→ goes in:** nowhere in the thesis. Recorded because it will otherwise be
rediscovered the hard way.

---

### Both reruns completed — 10 September

Both ran on the Mac (device `mps`, torch 2.14.0, commit `2c5a219`): the real
five-seed run finished 20:55, the matched control 21:26. The stdin fix held —
seed 44, where the previous attempt died, passed without incident.

**The real run reproduces Phase 7.** Balanced accuracy, mean ± sd over 5 seeds:

| Field | Phase 7 COAD | Rerun COAD | Phase 7 READ | Rerun READ |
|---|---|---|---|---|
| mucinous | 0.758 ± 0.031 | **0.755 ± 0.014** | 0.646 ± 0.017 | **0.656 ± 0.012** |
| node_positive | 0.619 ± 0.023 | **0.621 ± 0.022** | 0.620 ± 0.025 | **0.601 ± 0.017** |
| grade | 0.409 ± 0.020 | 0.414 ± 0.025 | 0.413 ± 0.026 | 0.408 ± 0.032 |
| pt_stage | 0.336 ± 0.021 | 0.325 ± 0.034 | 0.317 ± 0.021 | 0.312 ± 0.017 |

Every field lands inside its own spread. The largest move — node_positive on the
rectal holdout, 0.620 → 0.601 — is under one standard deviation, so it is drift,
not a finding. Phase 7's conclusions stand as written. Best epochs came out
[7, 10, 6, 14, 11] against [6, 10, 6, 6, 10]; seed 45 ran longer, but the
stopping rule still finds the same short window.

`results_stage1.json` and `stage1_mil.pt` are now both from this run, and the
results file records host, torch version, git commit and finish time.
**The checkpoint Stage 3 needs exists.**

*(These numbers were superseded an hour later by a second five-seed run, made
after per-class reporting was added to the evaluation — see below. The two runs
agree to within 0.014, which is itself useful and is recorded there. Quote the
later run.)*

**→ goes in:** Results (these are the numbers to quote, from a file rather than
from prose).

### The matched control lands at chance — and corrects Phase 8

The control now differs from the run it controls in exactly one setting.
Comparing the two config blocks field by field, the only difference is
`shuffle_labels: false → true`, plus `match_config`, which merely records where
the settings were copied from. That is what Phase 9 asked for and what the
earlier control was not.

| Field | Real labels | Matched control | Chance |
|---|---|---|---|
| mucinous, COAD | 0.755 | 0.471  [0.366, 0.578] | 0.500 |
| mucinous, READ | 0.656 | 0.485  [0.407, 0.565] | 0.500 |
| node_positive, COAD | 0.621 | 0.525 | 0.500 |
| node_positive, READ | 0.601 | 0.499 | 0.500 |
| grade, COAD | 0.414 | 0.326 | 0.333 |
| pt_stage, COAD | 0.325 | 0.252 | 0.250 |

Every control figure reads "not above chance" on both cohorts, and the control's
best epochs are [1, 1, 8, 2, 1] — with the image-label link broken there is
nothing to learn, so early stopping fires almost immediately. **The pipeline has
no leakage**, and this time the control is evidence about the run it controls.

**Correction to Phase 8.** That section says mucinous "collapses to *below*
chance once the image-label link is broken", quoting 0.364 against a 0.500
baseline. Under a properly matched control it sits **at** chance: 0.471, with a
95% interval of [0.366, 0.578] that comfortably contains 0.500. The old 0.364
was an artifact of the crippled control — 1 seed, 8 epochs, 512 patches — not a
real effect, and "below chance" was always the harder claim to defend. At chance
is exactly what a sound pipeline should produce, so the argument is unchanged
and the wording is now defensible. Quote the matched numbers;
`results_shuffled_unmatched.json` keeps the old ones traceable (removed from the working folder 26 Sep; still in git history, e.g. `git show 286ea35:stage1/results_shuffled_unmatched.json`).

**Lesson:** the unmatched control did not just weaken the argument, it produced a
number that looked *more* impressive than the truth. A crippled control is not a
conservative one.

*(This control was also rerun after per-class reporting was added, and landed in
the same place — mucinous 0.449 on colon, 0.506 on rectal. Quote the later run,
below; the agreement between the two is itself reassuring.)*

**→ goes in:** Methods (validation) — this table replaces the Phase 8 one.

---

### Per-class reporting, and the three things it exposed

The Phase 8 audit asked for per-class recall with counts, because balanced
accuracy gives every class an equal share of the average however few patients
stand behind it. `evaluate()` now records per-class recall and support, plus a
second balanced accuracy over classes with at least `MIN_CLASS_N = 5` cases,
carrying its own chance baseline of 1/(classes kept) — dropping a class changes
what guessing scores, and reporting 3 of 4 pT classes against 0.25 would quietly
flatter the model. The headline metric is unchanged. Pinned down by
`stage1/test_per_class.py` (18 checks, no torch needed).

The real run was then repeated so the results file carries the detail (finished
21:54, five seeds, best epochs [6, 2, 6, 6, 15]). **These are the numbers to
quote.**

| Field | COAD test | per-class recall (n) | READ holdout | per-class recall (n) |
|---|---|---|---|---|
| mucinous | 0.766 ± 0.039 | no 0.881 (69) · **yes 0.650 (12)** | 0.647 ± 0.016 | no 0.872 (133) · **yes 0.422 (18)** |
| node_positive | 0.617 ± 0.029 | neg 0.448 (25) · pos 0.785 (41) | 0.608 ± 0.024 | neg 0.494 (32) · pos 0.722 (87) |
| grade | 0.400 ± 0.007 | **G1 0.000 (6)** · G2 0.756 (63) · G3 0.444 (9) | 0.415 ± 0.033 | **G1 0.040 (5)** · G2 0.784 (115) · G3 0.421 (19) |
| pt_stage | 0.327 ± 0.024 | **pT1 0.000 (1)** · pT2 0.260 (20) · pT3 0.649 (41) · pT4 0.400 (10) | 0.311 ± 0.029 | **pT1 0.000 (5)** · pT2 0.458 (24) · pT3 0.562 (90) · pT4 0.225 (8) |

**1. The model never predicts the rarest class.** G1 recall is 0.000 on colon
and 0.040 on rectal; pT1 recall is 0.000 on both. This is not noise — the sd on
G1 is 0.000 across five seeds. Inverse-frequency class weighting was supposed to
prevent exactly this, and on 347 training cases it does not: 22 G1 cases and 15
pT1 cases in the whole dataset are too few to learn from. It also explains why
grade sits so immovably at ~0.41 in every run. A model that only ever said G2
would score 0.333, precisely chance; the margin above it is **entirely** G3
recall. So grade is not "weakly above chance at everything" — it is *G2 versus
G3, weakly, and G1 never*. Say that in Results rather than quoting 0.41.

**2. pT stage is not "not usable" — one patient was carrying that verdict.**
Phase 7 called pT a failure at 0.336 against chance 0.250. The COAD test split
holds exactly one pT1 case, and the model gets it wrong, which costs a full
quarter of the average. Excluding it: **0.436 ± 0.031 over three classes against
chance 0.333** — a wider margin than the headline figure showed, with pT3 at
0.649 and pT4 at 0.400. pT remains the weakest of the four and pT2 (0.260) is
genuinely poor, but "not usable" overstated it. On the rectal holdout pT1 has 5
cases so it is not excluded, and the model still scores 0.000 on it, which is
finding 1 again.

**3. The mucinous generalisation gap is entirely a positive-class gap.**
Negative recall barely moves between cohorts (0.881 → 0.872). Positive recall
falls from 0.650 to **0.422**. So on the unseen cohort the model misses more
than half of the mucinous and signet-ring cases, and the headline drop from
0.766 to 0.647 is that and nothing else. This is the honest form of the
project's best result: the model is far better at ruling mucinous *out* than
ruling it *in*, and worse at ruling it in on a cohort it has not seen. Report it
that way. node_positive is asymmetric in the same direction — positive recall
0.785 against negative 0.448 on colon — which fits a training set of 317
positive against 145 negative.

**→ goes in:** Results (the table), Discussion (all three findings), Limitations
(rare classes are unlearnable at this dataset size).

### Two identical runs, and what they say about the verdict column

The same five-seed configuration has now been run twice, an hour apart, on the
same machine. Patch subsampling is redrawn every epoch and is not seeded, so the
runs are independent samples of the same procedure. **No field moved by more
than 0.014** (mucinous colon 0.755 → 0.766; grade colon 0.414 → 0.400; the rest
under 0.010). That is a real reproducibility figure and worth stating in
Methods.

It also exposes something to be careful about. Two verdict labels flipped
between the runs: node_positive on colon went from "above chance" to
"borderline" (its interval moved from [0.500, 0.728] to [0.496, 0.724]), and
grade on rectal went from "borderline" to "above chance" (interval floor 0.337
against a chance of 0.3333). Both sit on the knife edge, and a word that changes
when nothing changed is not a finding. **For those two, report the interval and
the per-class breakdown, never the verdict word.** Phase 7 already flagged the
grade case — "technically above chance ... meaningless in practice" — and this
is the demonstration.

**→ goes in:** Methods (reproducibility), and a caution in Results.

---

### The control, rerun with per-class detail — and the baseline it provides

Rerun after the reporting change so both halves of the pair come from the same
code (finished 22:11, best epochs [1, 1, 9, 2, 2]). Config comparison against
the run it controls, field by field: the only difference is
`shuffle_labels: false → true`. **Every one of the eight figures reads "not above
chance."**

| | COAD test | READ holdout |
|---|---|---|
| mucinous | 0.449 ± 0.045 (chance 0.500) | 0.506 ± 0.012 |
| node_positive | 0.506 ± 0.058 (0.500) | 0.497 ± 0.084 |
| grade | 0.342 ± 0.046 (0.333) | 0.307 ± 0.019 |
| pt_stage | 0.258 ± 0.040 (0.250) | 0.224 ± 0.022 |

**The useful part is per-class.** Aggregate balanced accuracy tells you the
control sits at chance, which is all it was ever asked to do. But its *per-class*
recall is not uniform at all — it scores 0.730 on non-mucinous, 0.616 on G2,
0.522 on pT3, 0.707 on node-positive. With the image-label link broken there is
nothing to learn from the slide, so what remains is the class prior: the model
predicts whatever is common. That gives a per-class floor that "chance" does not,
and the distance above it is the honest measure of what the images contributed.

| Field | Class (n) | Real | Control | Learned |
|---|---|---|---|---|
| mucinous, COAD | yes (12) | 0.650 | 0.167 | **+0.483** |
| mucinous, COAD | no (69) | 0.881 | 0.730 | +0.151 |
| mucinous, READ | yes (18) | 0.422 | 0.311 | +0.111 |
| mucinous, READ | no (133) | 0.872 | 0.701 | +0.171 |
| node_positive, COAD | neg (25) | 0.448 | 0.304 | +0.144 |
| node_positive, COAD | pos (41) | 0.785 | 0.707 | +0.078 |
| node_positive, READ | neg (32) | 0.494 | 0.250 | **+0.244** |
| node_positive, READ | pos (87) | 0.722 | 0.745 | **−0.023** |
| grade, COAD | G2 (63) | 0.756 | 0.616 | +0.140 |
| grade, COAD | G3 (9) | 0.444 | 0.378 | +0.067 |
| grade, READ | G2 (115) | 0.784 | 0.637 | +0.148 |
| grade, READ | G3 (19) | 0.421 | 0.284 | +0.137 |
| grade, both | G1 (6, 5) | 0.000, 0.040 | 0.033, 0.000 | ~0 |
| pt_stage, COAD | pT3 (41) | 0.649 | 0.522 | +0.127 |
| pt_stage, COAD | pT4 (10) | 0.400 | 0.220 | +0.180 |
| pt_stage, COAD | pT2 (20) | 0.260 | 0.290 | −0.030 |
| pt_stage, READ | pT2 (24) | 0.458 | 0.283 | +0.175 |
| pt_stage, READ | pT4 (8) | 0.225 | 0.050 | +0.175 |
| pt_stage, READ | pT3 (90) | 0.562 | 0.564 | −0.002 |

Three things follow.

**1. The mucinous signal is exactly where it should be.** Positive-class recall
on colon is 0.483 above the prior-only baseline — by far the largest margin
anywhere in the project. The images are doing the work, and they are doing it on
the class that matters.

**2. node_positive on the rectal cohort is a node-*negative* detector.** Positive
recall (0.722) is *below* what the control gets from the prior alone (0.745); the
entire gain is on the negative class, +0.244. So the honest description is not
"the model detects nodal involvement in rectal cases" but "it identifies
node-negative rectal cases better than the prior does, and adds nothing to
positive detection." Phase 7 recorded node_positive as transferring perfectly
across cohorts on the aggregate number, and that is true, but the aggregate
concealed a change in *what* is being detected. Correct this in Results.

**3. pT carries real signal, unevenly.** pT3 and pT4 on colon and pT2 and pT4 on
rectal each sit 0.13–0.18 above the control. What sinks the aggregate is pT1,
which is never predicted, and pT2 on colon, which is at the control's level.
Together with the thin-class finding above, "pt_stage fails" is too blunt;
"pT1 is unlearnable at this dataset size and pT2 is not separable on colon, while
pT3 and pT4 carry signal" is what the data says.

**Method note worth keeping.** Reading per-class recall against nothing is
misleading, because a model that has learnt only the class prior already scores
well on common classes. The shuffled-label control supplies a per-class floor and
the delta from it is interpretable. This costs one extra training run and turns
the control from a box-ticking exercise into an analysis tool.

**→ goes in:** Methods (validation), Results (the delta table), Discussion
(findings 1–3). **Stage 1 is closed.**

---

# Phase 10 — Designing Stage 2: reasoning-guided generation with a step-count ablation

Decided 20 September, before any Stage 2 code was written, after reading around the
idea rather than assuming it would obviously help.

### The idea

Stage 2 takes Stage 1's four predicted findings and writes the narrative report from
them. The open question: does asking the generator to reason step-by-step before
writing the final report — a fourth condition alongside template / prompted / LoRA —
produce a better report than writing it directly? And if so, how many reasoning steps
is enough?

### What the literature actually says (this is not a free win)

- **Structured reasoning can reduce hallucination in medical report generation
  specifically.** CoMT (Chain-of-Medical-Thought, 2024) decomposes diagnostic
  reasoning into explicit steps that mirror how a clinician reasons through a case,
  and reports reduced hallucination and higher diagnostic accuracy versus direct
  generation. This is the positive case for trying it here.
- **But longer reasoning chains can *increase* hallucination in a grounded,
  evidence-conditioned setting** — which is exactly this thesis's setting. Work on
  multimodal reasoning models (2025) found that as reasoning gets longer, models pay
  measurably less attention to the actual evidence (there: the image; here: Stage 1's
  predicted fields) and drift toward hallucinated content generated from their own
  reasoning trace instead. This is a direct risk to the thesis's core claim
  (traceability), not just a performance detail, if the reasoning trace itself is not
  checked for faithfulness.
- **Reasoning length vs. correctness is not monotonic — it is an inverted U.**
  Independent work on chain-of-thought length shows performance rises with a small
  number of reasoning steps, peaks at a moderate depth, then falls as reasoning gets
  longer, because each extra step is a chance for a small error to compound. This is
  the actual justification for comparing a small number of step-counts (rather than
  assuming "more is better" and picking one large number).

**Conclusion:** worth doing, but the hypothesis is "there is a sweet spot, and past it
grounding degrades" — not "more reasoning is better." The experiment has to measure
*both* fluency/quality and faithfulness to Stage 1's predictions at each step count, or
it cannot detect the failure mode the literature warns about.

### Experimental design

A fourth Stage 2 condition, **Chain-of-Thought Prompting**, alongside the existing
template baseline, prompted-LLM condition, and LoRA fine-tuning:

- Compare **3, 6, and 9 reasoning steps**, each with a defined job rather than an
  arbitrary token budget — e.g. (1) restate the four predicted findings and their
  confidences, (2) reason about how the findings relate clinically (grade × stage ×
  nodal status), (3) draft the report — extended in the 6- and 9-step versions with
  explicit differential/contra-indication checks and a self-review pass against the
  stated findings before the final draft.
- Evaluate every step-count on **two axes, not one**: report quality (fluency,
  coverage of the four findings) and faithfulness (does the final report, and ideally
  the reasoning trace itself, ever state something Stage 1 did not predict). The
  faithfulness axis reuses the same checking logic planned for Stage 3's consistency
  metric, run early on Stage 2 output rather than waiting for Stage 3.
- Report the full curve across 3 / 6 / 9 steps, not just the best one — the inverted-U
  shape (or its absence) is itself a finding, consistent with how Stage 1's per-class
  analysis (Phase 9) treated a single aggregate number as something to interrogate,
  not trust outright.

### Sources
- Jiang, Y. et al. (2024) CoMT: Chain-of-Medical-Thought reduces hallucination in medical report generation — arXiv:2406.11451
- Xu, Z., Liu, C. et al. (2025) More thinking, less seeing? Assessing amplified hallucination in multimodal reasoning models — NeurIPS 2025, arXiv:2505.21523
- Wu, Y., Wang, Y., Ye, Z., Du, T., Jegelka, S. & Wang, Y. (2025) When more is less: understanding chain-of-thought length in LLMs — arXiv:2502.07266 (listed as ICLR 2026 on OpenReview; confirm). Inverted U: accuracy rises then falls with CoT length; the optimum grows with task difficulty and shrinks with model capability. *(Replaces the "Lacuna research notes", 27 Sep.)*
- Jin, M. et al. (2024) The impact of reasoning step length on large language models — Findings of ACL 2024, pp. 1830–1842. Counterpoint: longer steps help, mostly on complex tasks.
- Wei et al., "Chain-of-Thought Prompting Elicits Reasoning in Large Language Models" — arXiv:2201.11903

**→ goes in:** Methods (Stage 2 design), Results (the 3/6/9 curve on both quality and
faithfulness), Discussion (whether the inverted-U shows up here too).

*(24 September: this ablation is now a secondary experiment, and the first thing cut
if time runs short. The main Stage 2 experiment is grounded vs. ungrounded
generation — see Phase 11. Before citing, replace the "Lacuna research notes" source
with a peer-reviewed or arXiv paper, cite the "More Thinking, Less Seeing?" work by its
paper rather than its project page, and add the CoMT authors.)*
*(27 September: all three done — see Sources above.)*

---

# Phase 11 — Reframing Stage 2 as a comparison, and protecting Stage 3

Decided 24 September, before any Stage 2 code was written. The goal has widened from
the thesis to a **publishable paper**, and a paper needs a comparison with a
baseline, not a description of a system.

### Found while reviewing the uncommitted changes: a commit hash that lied

Both Phase 9 results files (`results_stage1.json`, finished 21:54, and
`results_shuffled.json`, 22:11) record `git_commit: 2c5a219`. But the code that
produced them included the per-class reporting in `train_stage1.py`, which was
still uncommitted at the time. So the hash points at code that *could not* have
written those files — 2c5a219 has no per-class output at all.

Nothing about the numbers is wrong: every figure in both files was checked against
the Phase 9 tables and matches, and `test_per_class.py` / `test_run_paths.py` pass.
What was wrong is the provenance claim. **The code that actually produced the Phase 9
results is 2c5a219 plus the `train_stage1.py` changes committed alongside those
results files** — say so in that commit's message.

**Fix.** `provenance()` now calls `git_state()`, which records `git_dirty_code`
(True whenever any `.py` differs from the commit) and `git_dirty_files` (every path
that does). A results file can no longer claim a commit without also saying whether
the code matched it. Pinned by a new check in `test_run_paths.py` against a
throwaway git repository.

**Lesson:** the same shape as Phase 9's "a timestamp is not provenance" — a commit
hash is not provenance either, unless the tree was clean.

**Still open:** `stage1_mil.pt` (seed 42 then; **seed 44 since the 24 Sep rerun**, Phase 12)
is git-ignored by design and exists **only on the Mac**. Back it up somewhere
off the laptop — Stage 2's predictions and Stage 3's heatmaps both come from it.

**→ goes in:** Methods footnote (reproducibility).

### The framing: grounded versus ungrounded generation

Phase 10 listed four generators (template / prompted / LoRA / chain-of-thought). All
four are *grounded* — they all write from Stage 1's findings — so the design had no
answer to the first question a reviewer will ask: **does grounding help, compared
with not grounding?** The main experiment now holds the generator fixed and changes
only what it is given:

| Input to the generator | What it measures |
|---|---|
| **Nothing** — same prompt, findings removed | Ungrounded baseline: what the LLM invents from its priors about colorectal cancer |
| **Retrieval** — the report of the nearest training case, by mean-pooled UNI2-h embedding | Ungrounded but image-conditioned; the standard baseline in report-generation work, and usually strong on BLEU/ROUGE |
| **Stage 1 predicted findings** | The method |
| **Extracted findings** (the weak labels) | Upper bound; separates generator error from Stage 1 error |

Generators: **template**, **one** primary prompted LLM, and **LoRA** on that same
LLM. A second LLM (MedGemma) and the 3 / 6 / 9-step chain-of-thought ablation from
Phase 10 become **secondary experiments on the grounded arm only** — they are
interesting, but they are not the comparison the paper stands on.

**Primary metrics:**
- **Per-field correctness** of the four findings stated in the report, scored against
  the extracted labels. This is what lets the ungrounded arms be scored at all —
  they have no predicted findings to be faithful to.
- **Unsupported-claim rate** — statements about anything the generator was not given
  (lymphovascular invasion, margins, node counts, tumour size…).
- **Faithfulness** to the input findings, for the grounded arms.
- BLEU / ROUGE / BERTScore reported as secondary. Fluency is not the claim.

`extract_fields.py` run over *generated* reports is the first version of the
consistency checker — the same code that made the labels. Stage 3 is where it is
validated against pathologists.

### Three design traps, fixed before they happen

1. **LoRA trained on Stage 1's training-set predictions would learn to trust them.**
   On its own training cases Stage 1 is overfit, so its predictions there are far
   more accurate than at test time (60–77% balanced accuracy). Train LoRA with the
   extracted findings as input (or out-of-fold predictions), and test on real
   predictions.
2. **LoRA will learn to write what it is never given.** The training reports mention
   margins, lymphovascular invasion and node counts, so a model fine-tuned on them
   will produce those claims with no evidence behind them. Measure it — this is
   likely one of the headline results, not a nuisance.
3. **Pretraining contamination.** TCGA-Reports has been public since 2024; Llama and
   Qwen may have seen these exact reports. The retrieval and ungrounded arms partly
   expose this; name it in Limitations regardless.

**Predictions come from `stage1_mil.pt`, i.e. one seed alone** (seed 44 since the
24 Sep rerun), whereas the Stage 1 results are means over five seeds. Report that seed's own test figures next to the
Stage 2 results so the reader knows which model fed the generator.

### Stage 3 is protected — explicitly

*(Same day, later: pathologists are not available, so the reader study below is
replaced — see Phase 12. The protection of Stage 3 stands; only how the metric is
validated changes.)*

**The consistency metric, its validation, and a pathologist reader study are
non-negotiable.** They are what make the paper publishable: without them Stage 2 is
a system description whose central claim (traceable, faithful reports) is asserted
rather than measured. This reverses the 20 September roadmap, which said to cut the
consistency metric *first* if the schedule slipped.

**Reader study (one study, two jobs):**
- **30–40 cases** from the COAD test split and the rectal holdout, chosen to include
  the rare-but-important classes (mucinous-positive, G3, pT4, node-negative), not
  sampled at random.
- **Three versions of each report, blinded and in random order:** grounded (predicted
  findings), ungrounded (no findings), and the original pathologist report as a
  reference.
- **Two pathologists**, rating per-field correctness, each unsupported claim, and
  overall acceptability. Report inter-rater agreement (Cohen's κ).
- **The same ratings validate the automated metric:** agreement between the
  consistency checker's verdicts and the pathologists' is the Stage 3 validation
  result. No separate annotation round is needed.
- About 90–120 reports per pathologist, ~2–4 hours each. **Recruit and book now** —
  pathologist time is the scarcest resource in the whole plan. Ask the supervisor
  whether an ethics sign-off is needed for expert raters, even on public data.

**→ goes in:** Methods (Stage 2 design, Stage 3 validation), Results (the input-arm
comparison and the reader study), Discussion (does grounding reduce unsupported
claims, and does the automated metric agree with pathologists?), Limitations
(contamination, single-seed predictions).

---

# Phase 12 — No pathologists, and what the slides cannot show

Two changes on 24 September, both decided before any Stage 2 code was written.

### No reader study: validating the metric without pathologists

Recruiting pathologists is not possible for this project. That removes one claim —
*"pathologists judge the reports acceptable"* — and nothing else. The paper's claim is
that **grounding reduces incorrect and unsupported statements**, and checking whether
a report says "G3" when its input says G3, or states lymphovascular invasion it was
never given, is a reading task, not a diagnosis. It does not need a pathologist.

The consistency metric is instead validated three ways:

1. **Planted errors (the main validation).** Take real and generated reports and
   plant known mistakes: wrong values (G2 → G3, pT3 → pT4, mucinous flipped, node
   status flipped), a missing field, an added unsupported claim (lymphovascular
   invasion, margins, node counts), a negation or hedge. Also make meaning-preserving
   rewordings, which must **not** be flagged. Report, per error type, how often the
   metric catches the error and how often it raises a false alarm. Ground truth is
   known for every example, and the whole test is automatic and reproducible.
2. **GDC clinical data as an independent human reference.** TCGA's clinical records
   carry `ajcc_pathologic_t`, `ajcc_pathologic_n` and `primary_diagnosis` (which names
   mucinous adenocarcinoma), abstracted from the same reports by trained curators,
   independently of `extract_fields.py`. This measures extractor accuracy on pT, N and
   mucinous across up to 590 cases rather than 50, and gives a second reference to
   score generated reports against. Grade is likely sparse there — check. **To do:**
   download the clinical TSV for TCGA-COAD and TCGA-READ from the GDC Data Portal on
   the Mac (the GDC API is not reachable from the Claude environments).
3. **Double annotation.** You and one other person (supervisor or a fellow student)
   independently label the ~50 gold cases plus ~60 generated reports (30 cases ×
   grounded and ungrounded), from a written rubric. Report Cohen's κ. Non-experts are
   acceptable here because the task is reading, not diagnosing — say so in Methods.

*Optional:* an LLM judge as a cross-check on the rule-based metric — convergent
evidence only, never the reference.

**What changes in the paper:** the claim is "grounding reduces incorrect and
unsupported claims, measured by a validated metric", not "reports are clinically
acceptable". An expert reader study goes in Limitations and Future Work, stated
plainly. Machine-learning and health-AI venues that accept automated evaluation remain
realistic; clinical journals would probably want expert readers.

**→ goes in:** Methods (metric validation), Results (detection rates per error type,
agreement with GDC, κ), Limitations (no expert readers).

### The slides are primary tumour — nodal status is not visible to the model

Raised by Dr Derek Magee (Leeds): TCGA diagnostic slides do not come with separate
lymph-node slides, so the tissue the model sees may not contain what the report
describes. **Checked against the data rather than assumed.** The TCGA sample-type code
in `metadata.csv`:

| Sample type | Slides |
|---|---|
| 01 — primary tumour | **599** |
| 06 — metastatic | 1 (TCGA-NH-A6GC, COAD test split, pooled with its primary-tumour slide) |

But `node_positive` comes from the report, written after the pathologist examined
**every lymph node removed at surgery**, on other slides. So for essentially every
case the model predicts nodal status from tissue that usually contains no node. A
slide may occasionally catch a node in the fat beside the tumour, but only by chance.

**What this does to Stage 1 — the results stand, the description changes:**

- The node task is **inferring nodal status from the primary tumour's morphology**,
  not detecting nodal metastasis. That is a real and published question, and reported
  performance on it is modest; 0.62 balanced accuracy fits. It also explains the
  Phase 9 finding that on the rectal cohort the model adds nothing over the class
  prior for node-positive cases.
- **pT stage is partly affected too.** It depends on the deepest point of invasion,
  which one slide may not include.
- **Performance tracks visibility.** Mucinous type (visible on a tumour slide) scores
  best, pT (sometimes visible) weaker, node status (not visible) just above chance.
  That is a coherent Discussion finding, not an embarrassment.
- **Sensitivity check to run:** Stage 1 test figures with TCGA-NH-A6GC excluded — it
  is node-positive, pT4 and mucinous, and the only bag containing metastatic tissue.

**What this does to Stages 2 and 3:**

- Every field carries a **visibility tag**: *visible* (histologic type, grade),
  *partly visible* (pT), *not visible* (node status).
- Grounded reports word node status as a **model inference with its confidence**,
  never as something observed. The consistency metric flags a confident nodal
  statement as **not supported by the slide**, and reports node status separately.
- **Heatmaps** are shown only for visible fields — attention cannot point at nodal
  involvement that is not on the slide.

This strengthens the traceability argument: the system is explicit about which claims
the slide can support at all.

**→ goes in:** Methods (sample types; visibility tags), Results (node task named
correctly; the A6GC sensitivity check), Discussion (performance tracks visibility),
Limitations (no nodal tissue; one slide per case for pT).

### GDC exposed two label bugs — node status and mucinous type

The GDC clinical file was downloaded the same day (`gdc_clinical_coad_read.tsv`, 633
TCGA COAD/READ cases, from the GDC API on the Mac — the command is in the git history
of this entry) and compared with the weak labels by `stage1/compare_gdc.py`. All 590
cases are in it; 5 have no colorectal diagnosis entry. **GDC has no histologic grade
for any of these cases**, so grade can only be checked by the gold set. Several cases
carry more than one GDC diagnosis (earlier prostate or breast cancers), so the
colorectal entry is chosen by site of origin, never by position.

**First comparison, before any fix:**

| Field | n | Agreement | κ |
|---|---|---|---|
| pT stage | 494 | 98.0% | 0.96 |
| mucinous | 550 | 91.8% | 0.67 |
| node status | 457 | **77.7%** | **0.56** |

**Bug 1 — node status: 96 false positives.** 96 cases were labelled node-positive
where both the report and GDC say N0 — about 30% of all positives. The extractor
tested positive patterns first and loosely, so negative phrasing containing
"metasta" read as positive:

- "Eleven lymph nodes are **negative for metastatic** tumor"
- "Lymph Nodes: Number with metastasis: **0**"
- "No regional lymph node metastasis"
- form headings: "Suspected Involved lymph Nodes … Distant Metastasis"
- "pNO", with OCR's letter O for zero, escaped the negative rule

This is the margin extractor's failure again (Phase 4), and **the 95.2% nodal
cross-check did not catch it**: 84 of the 96 reports never state a pN stage, so the
cross-check only ever covered the easy cases. It was never the lower bound on label
quality it was described as. The positive rate was the visible symptom — 317
positive vs 145 negative, where GDC is close to 50/50 — and nobody questioned it.

**Bug 2 — mucinous: a definition gap.** "Mucinous" anywhere in the text counted,
including "mucinous component (15%)", "focal mucinous differentiation" and a benign
appendiceal mucocele. WHO defines mucinous adenocarcinoma as >50% mucin; GDC's
curators mostly code the partial cases as adenocarcinoma.

**Fix.** `lymph_node_positive` rewritten so the most specific evidence decides: pN
stage (OCR-tolerant), then explicit counts ("3/17", "Number with metastasis: 0",
"one of thirty two", "Lymph nodes: 0/8 positive"), then negative statements, then
positive ones; the generic "metasta … lymph" window is gone. `histologic_type`
rewritten to the WHO definition: only a statement that the tumour *is* mucinous (or
signet-ring cell) carcinoma counts, allowing for OCR full stops and adjectives
between the words and for Latin ("et mucinosum" counts, "partim mucinosum" does not).
`pn_stage` now reads "pNO" as 0. Pinned by `stage1/test_extract_fields.py` — 26 checks
built from the real phrases that failed.

**How over-fitting to GDC was avoided.** Rules were changed only in response to
**training-split** disagreements; test and holdout disagreements were inspected to
classify them, never to write a rule. The test and holdout agreement figures below
are therefore held-out. (One bug — the count written after "Lymph nodes:" — was
found on a training case and also fixed a holdout case; one OCR error seen only in a
test case, "Number with metastases: U", was deliberately left unfixed.)

**After the fix:**

| Field | n | Agreement | κ | train | **test** | **holdout** |
|---|---|---|---|---|---|---|
| pT stage (unchanged) | 494 | 98.0% | 0.96 | 99.0% | 94.4% | 97.6% |
| node status | 514 | **97.5%** | **0.95** | 98.0% | 94.8% | 97.8% |
| mucinous | 550 | 93.3% | 0.63 | 93.2% | 91.2% | 94.6% |

Node coverage also rose, 78.3% → 88.1%, because negative reports are now recognised.
The pn_stage cross-check rises to 98.3% (403 / 410).

**What the remaining disagreements are.**
- *Node status (13):* reports that contradict themselves (TCGA-AA-A01Q states pN2
  and "tumour-free lymph nodes (0/16)"), GDC entries that contradict their own report
  (TCGA-CK-5916: "metastatic carcinoma in one of thirty-two lymph nodes", GDC N0;
  three cases where the report says pN0 and GDC says N1 or N2), tumour deposits coded
  N1c, and the one OCR error above.
- *Mucinous (37):* 25 are partial-mucinous wording, where **GDC is itself
  inconsistent** — it codes some "partially mucinous" cases as mucinous and most
  "component 15%" cases as not; 7 have no mention of mucin in the report text at all
  (GDC had another source); 2 are GDC errors (TCGA-AA-3555 and TCGA-AG-3583 both
  state "mucinous adenocarcinoma"); 2 are tick-box forms. **Essentially no clear
  extractor errors remain**, which is why κ for mucinous stays at 0.63 — the
  reference, not the extractor, sets the ceiling. The WHO rule stays.

**What changed in the labels.** Node status: 95 positive → negative, 63 unlabelled
→ negative, 16 unlabelled → positive, 21 others to or from unlabelled; now 227
positive / 293 negative. Histologic type: 51 cases changed; the mucinous head's
positive class shrinks from 94 to **44** (43 mucinous + 1 signet-ring — signet-ring
carcinoma proper is rarer than the 6 "signet ring" mentions suggested). No other
field changed.

**Stage 1 is reopened.** The node-positive and mucinous heads were trained and
scored on the old labels, and the heads share a trunk, so the whole model must be
retrained: the real five-seed run and the matched control, on the Mac, about an
hour each. **`results_stage1.json`, `results_shuffled.json` and `stage1_mil.pt` now
describe the old labels** — the Phase 9 tables are superseded once the rerun lands.
Expect mucinous to get harder (44 positives, of which only a handful in each test
split — per-class support will be thin) and node status to move, since a third of
its positive training labels were wrong. Either direction is a finding.

**Lesson:** checking labels against themselves (pN vs node status) cannot find an
error both share or one confined to cases where only one is stated. An independent
reference found in an afternoon what four phases of internal audit missed.

**→ goes in:** Methods (label validation against GDC; the WHO definition), Results
(agreement table, held-out columns), Limitations (GDC's own inconsistency on
partial-mucinous cases; no grade reference), and a Methods footnote on how the rules
were fixed without tuning to the held-out reference.

### Stage 1 rerun on the corrected labels — 24 September

Both runs on the Mac (`mps`, torch 2.14.0), stdin detached, chained in one command:
real five-seed run finished 14:49, matched control 15:03. The control's config differs
from the real run's only in `shuffle_labels` (and `match_config`, which records where
it was copied from). Best epochs: real [12, 10, 6, 6, 4], control [15, 1, 1, 4, 2].
The Phase 9 files and checkpoints are kept in `stage1/archive_phase9_oldlabels/`. *(Folder deleted 26 Sep in a clean-up: its two results files are identical to those in commit 59e0a0c — `git show 59e0a0c:stage1/results_stage1.json` — and the old-label checkpoints are not needed.)*

**Provenance, working as intended.** Both files record commit 2c5a219 **and**
`git_dirty_code: true`, listing `extract_fields.py`, `structured_labels.json` and
`train_stage1.py` among the uncommitted files. Exactly what the Phase 11 fix was for:
the hash alone would again have pointed at code and labels that did not produce
these numbers. Commit before the next run that matters.

**The checkpoint is now seed 44** (best validation score, 0.622), not seed 42.
Stage 2 predictions come from it.

**Balanced accuracy, mean ± sd over 5 seeds, 95% interval for the new run:**

| Field | Phase 9 COAD (old labels) | **Now COAD** | Phase 9 READ | **Now READ** | Control COAD / READ |
|---|---|---|---|---|---|
| mucinous | 0.766 ± 0.039 | **0.719 ± 0.060** [0.613, 0.805] | 0.647 ± 0.016 | **0.739 ± 0.024** [0.663, 0.802] | 0.474 ± 0.021 / 0.520 ± 0.050 |
| node status | 0.617 ± 0.029 | **0.595 ± 0.024** [0.484, 0.698] | 0.608 ± 0.024 | **0.526 ± 0.018** [0.444, 0.608] | 0.475 ± 0.028 / 0.516 ± 0.028 |
| grade | 0.400 ± 0.007 | **0.429 ± 0.025** [0.325, 0.540] | 0.415 ± 0.033 | **0.404 ± 0.023** [0.326, 0.487] | 0.355 ± 0.048 / 0.323 ± 0.020 |
| pT stage | 0.327 ± 0.024 | **0.325 ± 0.049** [0.228, 0.440] | 0.311 ± 0.029 | **0.304 ± 0.035** [0.231, 0.389] | 0.243 ± 0.026 / 0.252 ± 0.022 |

Every control figure is "not above chance". Verdict words for the real run: mucinous
**above chance** on both cohorts; the other six **borderline** — and Phase 9 already
showed that for figures this close, report the interval, not the word.

**Per-class recall against the prior-only control** (the Phase 9 method: the control
supplies a per-class floor, and the gap above it is what the images contributed):

| Field | Class (n) | Real | Control | Learned |
|---|---|---|---|---|
| mucinous, COAD | no (75) | 0.971 | 0.848 | +0.123 |
| mucinous, COAD | yes (6) | 0.467 | 0.100 | **+0.367** |
| node status, COAD | neg (41) | 0.590 | 0.595 | -0.005 |
| node status, COAD | pos (36) | 0.600 | 0.356 | **+0.244** |
| grade, COAD | G1 (6) | 0.033 | 0.033 | +0.000 |
| grade, COAD | G2 (63) | 0.765 | 0.698 | +0.067 |
| grade, COAD | G3 (9) | 0.489 | 0.333 | +0.156 |
| pT stage, COAD | pT1 (1) | 0.000 | 0.000 | +0.000 |
| pT stage, COAD | pT2 (20) | 0.340 | 0.340 | +0.000 |
| pT stage, COAD | pT3 (41) | 0.620 | 0.473 | +0.146 |
| pT stage, COAD | pT4 (10) | 0.340 | 0.160 | +0.180 |
| mucinous, READ | no (141) | 0.918 | 0.860 | +0.058 |
| mucinous, READ | yes (10) | 0.560 | 0.180 | **+0.380** |
| node status, READ | neg (73) | 0.501 | 0.649 | -0.148 |
| node status, READ | pos (66) | 0.552 | 0.382 | +0.170 |
| grade, READ | G1 (5) | 0.040 | 0.000 | +0.040 |
| grade, READ | G2 (115) | 0.793 | 0.685 | +0.108 |
| grade, READ | G3 (19) | 0.379 | 0.284 | +0.095 |
| pT stage, READ | pT1 (5) | 0.000 | 0.000 | +0.000 |
| pT stage, READ | pT2 (24) | 0.500 | 0.392 | +0.108 |
| pT stage, READ | pT3 (90) | 0.516 | 0.542 | -0.027 |
| pT stage, READ | pT4 (8) | 0.200 | 0.075 | +0.125 |

**What changed, and why.**

**1. Mucinous: the rectal "generalisation gap" was label noise.** Phase 9's headline
was a drop from 0.766 on colon to 0.647 on rectal, entirely in positive-class recall
(0.650 → 0.422). With WHO-defined labels, rectal is now **0.739 [0.663, 0.802]** —
level with colon, 0.719 [0.613, 0.805] — and positive recall is 0.467 on colon and
0.560 on rectal, each about **+0.37 over the control**. The model still recognises
mucinous tumours from the image, and it does so on the unseen cohort. The earlier gap
came from labelling tumours with a minor mucinous component as mucinous: those look
like ordinary adenocarcinoma, so the model "missed" them. **Caveat that must go with
this everywhere:** only 6 colon and 10 rectal test cases are positive, so each
positive-class recall moves in steps of 0.17 and 0.10. Read the direction, not the
decimal.

**2. Node status: most of the old signal was not nodal.** Colon 0.617 → **0.595
[0.484, 0.698]**; rectal 0.608 → **0.526 [0.444, 0.608]**, an interval containing chance.
Per class, colon still learns something about positives (+0.244 over the control); on
rectal, positive recall gains +0.170 but negative recall falls 0.148 *below* the prior,
so the model has no net discrimination there. This is what Phase 12's slide check
predicts — the slides are primary tumour, the nodes are not on them. A plausible reason
the old labels scored *higher*: the 95 false positives were concentrated by institution
(19 of 37 CM cases, 6 of 13 AD, 5 of 13 DC), and institution is visible in a slide
through staining and scanning, so the old model could partly predict the *labelling
error* from the slide. That is a hypothesis, not a finding, but it is the reason a
cleaner label can score lower and be the better result.

**3. Grade and pT: unchanged, as they should be.** Their labels did not change. Grade
0.400 → 0.429 on colon and 0.415 → 0.404 on rectal; pT 0.327 → 0.325 and 0.311 → 0.304
— all inside run-to-run spread (Phase 9: up to 0.014) or near it, with the shared
trunk now trained on different node and mucinous targets. G1 and pT1 are still never
predicted. pT on colon without its single pT1 case: 0.433 over 3 classes (chance 0.333).

**The picture now matches the visibility argument (Phase 12) cleanly:** the one field
fully visible on a tumour slide (mucinous type) is clearly learned and transfers; the
partly visible ones (grade, pT) are weakly learned; the invisible one (node status) is
near chance. Phase 9's picture, where node status looked as good as anything, was
partly an artifact of the label bug.

**→ goes in:** Results (these tables replace Phase 9's), Discussion (performance tracks
visibility; the mucinous gap was a label-definition effect; the institution hypothesis
for node status, labelled as such), Limitations (6 and 10 mucinous positives in the
test splits).

### Sensitivity check: TCGA-NH-A6GC, the one bag with metastatic tissue

`stage1/sensitivity_a6gc.py`, run on the Mac on 24 Sep. It uses the saved checkpoint
(seed 44) and scores every test bag with **all** its patches, no subsampling. So these
are one model's figures and **not comparable to the 5-seed means above** — do not quote
them as results. The case is in the colon test split, so it never influenced training;
the only questions are whether it moves the test figures and what drives its own
predictions.

**Colon test, with vs without the case:** mucinous 0.820 → 0.787 (−0.033), pT
0.359 → 0.348 (−0.011), node status 0.602 → 0.609 (+0.007), grade unchanged (0.397;
its grade is not labelled). Three of the four move by about 0.01 or less.

**The mucinous drop is the thin-class effect, not metastatic tissue.** The case is
one of only 6 mucinous positives in the colon test split, and the model gets it right —
so removing it takes a correct case out of a class of six. What matters is *why* it
gets it right: **the primary-tumour slide alone gives mucinous = 1.000**, the same as
the pooled bag (0.999). The metastatic slide adds nothing the primary did not already
supply.

**Its own predictions, by slide:**

| | Both slides | Primary (01Z) only | Metastasis (06Z) only | Gold |
|---|---|---|---|---|
| mucinous | yes 0.999 | yes 1.000 | yes 0.999 | yes |
| pT stage | pT4 0.514 | **pT4 0.563** | pT3 0.528 | pT4 |
| node status | neg (pos 0.422) | neg (pos 0.325) | **pos 0.514** | positive |

- **Attention follows tissue quantity, not metastasis.** The metastatic slide gets
  54.7% of the attention and supplies 55.7% of the patches (10,974 of 19,717), so the
  model does not seek it out.
- **pT is best from the primary tumour alone**, as it should be — pT describes the
  primary.
- **Metastatic tissue pushes node status towards positive** (0.325 → 0.514), the only
  time in this project the model has seen tissue that is actually metastatic. One
  case is an anecdote, not evidence, but it is the direction Phase 12's visibility
  argument predicts: nodal status becomes more readable when metastatic tissue is on
  the slide.

**Decision: keep the case in all splits and report this check in a Methods footnote.**
For Stage 2, export this case's predictions from the pooled bag like every other
case (so the method is uniform), and note in the case's record that one slide is
metastatic.

### Found on the way: the evaluation subsample was never fixed across runs

`wsi_dataset.py` seeded the evaluation subsample with `hash(case_id)`, commented as
"fixed view at eval so metrics repeat". Python salts string hashes per process, so each
run drew a **different** "fixed" subsample. Within a run every seed saw the same view,
so no reported comparison is invalid. But part of the run-to-run drift in Phase 9 (up
to 0.014) came from evaluation sampling, not training. Now seeded with `zlib.crc32`,
which is stable across runs. The sensitivity check above avoids the question entirely by
using full bags.

**→ goes in:** Methods footnotes (the A6GC check; evaluation sampling). Limitations:
nodal status is readable only when metastatic tissue is on the slide — shown here for
one case only.

### Stage 3 consistency checker, first version — 24 September

Built while the gold labels are being done (nothing here uses them; the 50 gold cases
are excluded from every test).

- `stage2/findings.py` — the input contract every Stage 2 generator and the checker
  share: the four Stage 1 fields with value and probability, plus the source
  (`predicted`, `extracted`, or `none` for the ungrounded arm), and the visibility tag
  for each field (type and grade *visible*, pT *partly visible*, node status *not
  visible*).
- `stage2/template_report.py` — the deterministic template baseline, in three styles.
  It words pT as possibly unrepresentative and node status as an inference.
- `stage3/consistency.py` — the checker. Per field: correct / contradicted / omitted /
  unsupported (stated though not in the input) / absent. Separately: **unsupported
  claims** (lymphovascular invasion, margins, node counts, pN category, site, size,
  distant metastasis, MSI/MMR, perineural invasion, budding, other staging systems,
  treatment history) and **overclaims** (node status stated as observed, with no hedge).
  Sentences that abstain ("cannot be assessed") are removed first, so declining to answer
  is never a claim. `against_reference()` scores the ungrounded arm against the labels,
  since it had no input to be faithful to. Rule-based on purpose: every verdict traces to
  a pattern. 15 hand-written checks in `test_consistency.py`.

**Planted errors** (`stage3/planted_errors.py`, 150 non-gold cases). One known change per
report, scored for detection and for false alarms:

| Test | Result |
|---|---|
| Wrong value, each of 4 fields (template reports) | 100% detected, 0% false alarms |
| Omitted field, each of 4 | 100% / 0% |
| Unsupported claim inserted, 10 types | 100% / 0% |
| Node status stated without hedge | 100% / 0% |
| Controls: abstention; paraphrases of type, grade, T, node (15 kinds) | 100% left unflagged |
| **Real reports**, grade swapped in the text | **100.0%** (n=463) / 0% |
| **Real reports**, pT swapped | **100.0%** (n=460) / 0% |
| **Real reports**, adenocarcinoma → mucinous | **95.4%** (n=458) / 0% |

**Those template figures are development numbers, not validation.** The first run found
four real gaps — node overclaims caught 0% (the hedge window took in a neighbouring pT
sentence's "may"), node counts in words 0%, "grade 2" / "grade II" unread, and several
node phrasings unread — and the checker was fixed against this same suite. The real-report
swaps are the more honest half: messy multi-institution OCR text the checker was not
written against.

**Frozen held-out set** (`stage3/heldout_check.py`): 12 reports in free, LLM-like wording,
written *after* the tuning, with a careful reader's verdicts, run once and recorded as-is.
**65 / 72 verdicts right (90.3%); 7 / 12 reports fully right.** The misses:
"Nodes: negative (0/12)" not read as a node claim (no "lymph"); "invasive carcinoma with
mucinous features" gives no type (no "adeno"); "N0" counted both as the node answer and as
an extra pN claim; depth in words ("invades through the muscularis propria") not read as
pT3 — the checker reads codes only; "N-negative" unread, and tumour deposits not a claim
type. **These stay unfixed in this version.** Any fix is tested on a new held-out set, never
re-scored on this one. The real validation of the checker on LLM output is the double
annotation of ~60 generated reports.

**What real pathologists write beyond the four fields** (540 non-gold
reports; share that mention each):
pn category 78% · lymphovascular invasion 74% · tumour site 72% · tumour size 71% · margins 69% · node count 66% · perineural invasion 25% · other staging 9% · msi mmr 9% · distant metastasis 7% · tumour budding 6% · treatment history 4%.
This is what a model fine-tuned on these reports will learn to write, with nothing behind
it — the concrete prediction for the LoRA arm (Phase 11, trap 2).

**Found on the way: the lymphovascular-invasion extractor has the node bug's shape.**
`lymphovascular_invasion()` tests "lymphovascular invasion" before "no lymphovascular
invasion", so a negative statement reads as present — very likely why the field looked
80% positive and was excluded (Phase 4). It is not trained on, so nothing is rerun; the
gold labels will measure it, and the checker uses its own negatives-first rules instead.

**→ goes in:** Methods (the checker; planted-error validation, with the development vs
held-out distinction stated plainly), Results (the held-out figure and its failure
modes; the real-report claim profile), Limitations (a rule-based checker reads codes,
not descriptions — the LLM-judge cross-check and double annotation cover that).

### Stage 1 predictions exported for Stage 2 — 25 September

`stage2/export_predictions.py`, run on the Mac (seed-44 checkpoint, full bags): every case's
predicted class and class probabilities for the four fields (`stage2/inputs/predictions.json`)
and its nearest training case by mean-pooled UNI2-h embedding (`retrieval.json`). Stage 2 no
longer needs the feature files. Checked after the run:

- **Test figures match the sensitivity check exactly** (same checkpoint, same full bags):
  colon mucinous 0.820, grade 0.397, pT 0.359, node 0.602; rectal 0.754 / 0.442 / 0.338 /
  0.513. One model, not the 5-seed means — quote the means as Stage 1's result.
- **Training cases score 0.86–0.96** on the same fields — the overfitting Phase 11 warned
  about, now measured. Those predictions are flagged `in_training_set` and must never be a
  test input.
- **Retrieval is clean:** no case retrieves itself, every neighbour is from `train_coad`,
  cosine similarity 0.33–0.96.
- **pT4 is over-predicted.** On the colon test split, 12 of 41 labelled-pT3 cases are
  predicted pT4 (26 pT4 predictions against 10 true pT4); G3 likewise (32 predicted, 9 true).
  Inverse-frequency class weighting pushes rare classes up. So grounded reports will often
  state a wrong pT4 or G3 *with low confidence* — which is exactly what the confidence-aware
  wording and the consistency metric are for, and a concrete reason calibration belongs in
  Stage 3.
- Recorded provenance shows the export script itself uncommitted at run time (the dirty-file
  list also mis-cut the first entry, ".gitignore" → "gitignore"; fixed).

**→ goes in:** Methods (Stage 2 inputs), Results (the pT4/G3 over-prediction, next to the
per-class tables), Discussion (why grounding on imperfect predictions still needs hedging).

### Overfitting: cross-validation, calibration and a regularisation test — planned 26 Sep

The seed-44 model scores 0.86–0.96 on its own training cases against 0.40–0.82 held out.
Reporting only held-out figures is already correct; three things address the gap itself.
Written down **before** running, so the rules cannot drift to fit the results:

1. **Regularisation test** (`stage1/reg_sweep.py`): baseline vs dropout 0.6 vs trunk width 128
   vs weight decay 0.05, 3 seeds each, on the training pool only. **The test split and the
   rectal holdout are never evaluated** (`run_one_seed` is given empty lists; new in
   `train_stage1.py`). Records validation and training-set balanced accuracy, i.e. the gap.
   **Decision rule:** a candidate replaces the baseline only if its mean paired validation
   gain (same seed = same validation split) is ≥ 0.03 **and** it wins on all 3 seeds; the
   largest qualifying gain wins; otherwise the baseline stays. If it changes, Stage 1 and its
   matched control are rerun with the new setting before anything else (old files archived).
2. **5-fold cross-validation** (`stage1/crossval.py`) over all 434 colon cases, stratified by
   the mucinous label, with the sweep's setting. Every colon case is predicted by a model
   that never trained on it; the rectal holdout by the mean of the 5 fold models. Output
   `stage2/inputs/predictions_cv.json` **replaces `predictions.json` as the Stage 2 input**
   (434 honest colon cases instead of 87). The fixed-split result stays Stage 1's headline.
3. **Calibration** on the folds' validation logits (never trained on), applied to the
   out-of-fold and rectal predictions: temperature scaling (confidence only) and per-class
   bias (can change the answer, and targets the pT4 / G3 over-prediction). Report both,
   with calibration error and balanced accuracy before and after.

`stage1/run_overnight.sh` chains 1 → (rerun if needed) → 2, with a smoke mode that proves
every step runs first. `train_stage1.py` gains `--hidden` (default 512, unchanged behaviour)
and the empty-list guard; `test_run_paths.py` covers an old results file without `hidden`.

### Overfitting: what the regularisation test, cross-validation and calibration found — 26 Sep

**Run.** `stage1/run_overnight.sh`, on the Mac. The first attempt crashed at run 11 of 12 with
"Too many open files": the new training-set evaluation loader was never shut down, so each
run leaked worker file handles (the Phase 7 failure by a new route). Fixed (the loader is
now shut down with the others; `file_system` sharing strategy; open-file limit raised to
10,240 in the script; feature files closed explicitly in `crossval.py`; the sweep now saves
after every run and resumes). The 10 finished runs were **recovered from the crashed log**
(`overnight_crashed_26sep.log`, 3 decimals) and marked as such in `reg_sweep.json`; only
the 2 missing runs were trained again.

**1. Regularisation test — the baseline stays.** Mean validation balanced accuracy (train −
validation gap): baseline 0.591 (0.364) · dropout 0.6 0.580 (0.383) · width 128 0.601 (0.292) ·
weight decay 0.05 0.580 (0.375). No candidate beat the baseline on all 3 seeds, so by the rule
fixed in advance nothing changes and Stage 1 is not rerun. Width 128 narrows the gap a little
but does not generalise better. **The gap is a data-size effect, not a tuning problem** — which
is the honest reading for the thesis, and what the learning curve would test directly.

**2. 5-fold cross-validation (434 colon cases, all out-of-fold) and 3. calibration.**

| Task | CV colon (434) bal. acc | Rectal (5-fold ensemble) | Calibration error, colon: raw → temperature | Rectal: raw → temperature | Bal. acc with temp + bias |
|---|---|---|---|---|---|
| mucinous | 0.690 | 0.686 | 0.032 → **0.028** | 0.011 → 0.028 | 0.640 |
| grade | 0.469 | 0.462 | 0.133 → **0.043** | 0.071 → 0.111 | 0.399 |
| pt_stage | 0.349 | 0.332 | 0.187 → **0.082** | 0.089 → 0.047 | 0.259 |
| node_positive | 0.605 | 0.535 | 0.156 → **0.066** | 0.168 → 0.082 | 0.588 |

- **Cross-validation agrees with the fixed split** (fixed-split 5-seed means: mucinous 0.719,
  grade 0.429, pT 0.325, node 0.595) and rests on far more cases: the mucinous positive class
  now has **34** cases instead of 6, with positive recall 0.41 — a tighter and slightly more
  modest figure than 0.47 on 6. Quote both; the CV figure is the more reliable estimate of
  positive recall.
- **Temperature scaling works and changes no answer:** calibration error falls sharply for
  grade, pT and node status (mean confidence on pT 0.68 → 0.51 — the model had been sure far
  more often than it was right). Mucinous was already calibrated.
- **Per-class bias correction is rejected.** It lowers calibration error further but does so by
  nearly always predicting the majority class (pT3 for 356 of 369 cases, never G1), and
  balanced accuracy falls (pT 0.349 → 0.259, grade 0.469 → 0.399). It trades a visible
  over-prediction for a hidden collapse onto the common class.
- **The pT4 over-prediction was one model's quirk.** Across the 5 CV models pT4 is predicted
  43 times against 46 true; the saved seed-44 model's 26 against 10 on the test split was
  specific to that seed. The CV models over-predict pT2 instead (123 against 74).
- **Calibration transfers only partly to the rectal cohort:** better for pT and node status,
  worse for grade (0.071 → 0.111). A different case mix needs its own calibration — a
  Limitations point.

**Decision: Stage 2 uses `stage2/inputs/predictions_cv_calibrated.json`, temperature-scaled
values.** Every case has a prediction from a model that never trained on it, the answers are the
model's own, and the confidences quoted in the reports mean what they say.
`predictions.json` (seed-44, overfit on training cases) is kept for the record only.

**→ goes in:** Methods (cross-validation; temperature scaling fitted on validation logits,
cross-fitted to avoid leakage), Results (the CV table; calibration before/after), Discussion
(the gap is data size; why bias correction was rejected), Limitations (calibration across cohorts).

---

# Phase 13 — Comparisons: an external cohort and a published baseline

Decided 26 September, after a literature check on what else exists and what others compare
against.

### What was considered and why it was not the comparison

- **REG2025 (MICCAI 2025 challenge)** — ~10,500 WSI–report pairs from 5 countries, 7 organs,
  1,051 colon cases, CAP-style short reports (organ, procedure, type, grade), 20× TIFF.
  **Not used as the comparison:** its leaderboard scores all 7 organs together, so colon-only
  numbers cannot sit beside it; many colon cases are likely biopsies with no pT or node
  status, so two of the four fields do not exist; and ~2.1 TB would not fit fairly on a server
  shared by 11 people (8 TB). Cited as related work — its benchmark paper (arXiv 2609.00866)
  reports numeric hallucination (tumour proportions 80% vs 5%) and "failure to preserve
  uncertainty" as the main failure modes, which is exactly what the consistency metric and
  the confidence wording target.
- **REG2026 — "Pathologist Reasoning-Guided Report Generation"** (MICCAI 2026, results 27 Sep
  2026): report generation with chain-of-thought reasoning annotations. **Overlaps this
  thesis's title and the Phase 10 chain-of-thought idea.** Consequences: the CoT ablation
  stays secondary (and first to cut); the paper's distinct contribution is **grounded vs.
  ungrounded generation, the visibility tags, and the validated consistency metric**, not
  step-by-step reasoning. Read and cite the winning methods once published.
- **TITAN** (slide foundation model) — needs CONCH v1.5 patch features, not UNI2-h, and its
  report decoder is not publicly released. Not used.

### Decision 1 — CPTAC-COAD is the external test set (not optional)

CPTAC-COAD (TCIA; CC BY 4.0): 106 patients, 373 slides, SVS, **66.7 GB** — fits the shared
server; after feature extraction the slides can be deleted (features ~2–3 GB). An independent
colon cohort, never seen in any training. Used to test **Stage 1** (does the model and its
calibration transfer?) and **Stage 2** (do the grounded vs. ungrounded differences hold on
another cohort?). No report texts, so no report-generation paper uses it; it is an established
external set for predicting findings from TCGA-trained models (e.g. Lancet Digital Health 2022).

**Open questions to settle before downloading:**
1. **How the existing UNI2-h features were made** — tool (CLAM/TRIDENT/other), magnification,
   patch size, tissue segmentation. CPTAC features must be extracted **the same way**, or any
   drop in performance could be preprocessing rather than cohort. Ask whoever extracted them.
2. **Tumour vs. normal slides** — CPTAC collected normal adjacent tissue too; only tumour slides
   belong in a bag. Needs the slide metadata.
3. **Labels** — from GDC clinical data for the CPTAC colon cases (pathologic T, N, histologic
   type; grade if present), mapped exactly as `compare_gdc.py` does for TCGA. No report text,
   so labels are curator-abstracted from the start — a cleaner reference than TCGA's weak
   labels, but different in kind; state it.
4. UNI2-h access on the server (gated on Hugging Face) and GPU time for ~373 slides.

### Decision 2 — HistGen is a Stage 2 baseline

HistGen (MICCAI 2024; Apache-2.0; code public; cleaned TCGA reports on Hugging Face) is an
end-to-end slide → text model trained on TCGA WSI–report pairs — the kind of model the paper
argues against. It takes pre-computed patch features, so it is **re-trained on this thesis's
own split with the existing UNI2-h features** (no slides needed). Its published numbers are
**not** quoted as a comparison: its test set is pan-cancer and its colon/rectal test cases may
be in this thesis's training set. Re-running on the same split is the only fair comparison.

Stage 2 arms, all scored by the consistency checker plus BLEU/ROUGE/METEOR (the metrics
HistGen reports):

| Arm | Input |
|---|---|
| HistGen (published method, re-trained on this split) | slide features → text |
| LLM, no findings | nothing (ungrounded) |
| Retrieval | nearest training case's report |
| Template / LLM / LoRA with **predicted** findings | Stage 1 (CV, calibrated) — the method |
| LLM with **extracted** findings | upper bound |

WsiCaption (MICCAI 2024) was the alternative; it expects ResNet-50 features, so HistGen is the
practical choice.

**→ goes in:** Methods (external cohort; baselines), Results (external-test table; the full
Stage 2 arm table), Related work (REG2025, REG2026, HistGen, WsiCaption), Discussion (why
leaderboard numbers are not comparable).

---

### Literature review, lymph-node decision and scope freeze — 26 September

**Literature check** (full table in the "Thesis Journey" doc): PathReportEval (arXiv 2607.18448,
Jul 2026) proposes CRQS — fact coverage, key-finding recall, hallucination rate, contradictions —
on TCGA with HistGen and UNI2-h, and down-weights node status as "not visually inferable"; not
validated numerically against humans, no per-organ results. A decomposition paper (arXiv
2608.15353, Aug 2026) predicts diagnostic answers then generates text, beating free-form
generation. So two-stage generation alone is not new; the contribution is the controlled
grounded-vs-ungrounded comparison, visibility-aware abstention, and a checker validated with
numbers, on colorectal cancer in depth with an external cohort. Kiehl et al. (Eur J Cancer 2021):
node status from primary-tumour slides, 582 TCGA patients, AUROC 0.61 — matches ~0.60 here.

**Decision — lymph nodes:** reports **abstain** on node status ("cannot be assessed from the
submitted tissue") instead of a hedged estimate; node status stays in Stage 1 results and in the
evaluation (it is where ungrounded generators are expected to invent claims). Template and prompts
change accordingly. Open: whether a hedged-estimate variant is kept as a small side comparison.

**Added tasks:** (1) run PathReportEval's CRQS alongside the checker (code: PathBench) — two
independent metrics; (2) an LLM cross-check of the regex labels on the server (Llama 3 70B-class
models extract TNM/grade at ~97%, Comm Med 2025).

**Scope frozen as of 26 Sep:** nothing new is added. Cut order if late: chain-of-thought →
second/third LLM → LoRA → LLM label cross-check → CRQS → learning curve / heatmaps → HistGen.
Full draft to supervisor 3 Dec; submission 20 Dec.

---

### CPTAC-COAD features downloaded and checked — 26 September

`hf download MahmoodLab/UNI2-h-features CPTAC/cptac_coad.tar.gz` (15.6 GB), unpacked to
`UNI2_h_features/CPTAC/CPTAC-COAD/`: **372 slides from 178 patients** (TCIA lists 373 slides;
one is absent from MahmoodLab's set).

**Different extraction toolkit, same patch size.** The CPTAC files were made with **CLAM**
(512 px patches at level 0, `custom_downsample 2`, CLAM tissue segmentation), not TRIDENT as for
TCGA. Whether that matches depended on the scan resolution, and the evidence first conflicted:
similar patch counts per slide (CPTAC median 3,955 vs TCGA 3,488) but half the pixel dimensions
(CPTAC long side median 59,520 px vs ~113,000). **Settled from the NCI Imaging Data Commons
slide index (`idc-index`, sm_index v24):** all 372 CPTAC-COAD slides are 40×, 0.25 µm/px.
So 512 px × ½ = **256 px at 20× (128 µm), the same physical patch as TCGA**; the CPTAC
tissue pieces are just physically smaller. Remaining difference: CLAM vs TRIDENT tissue
segmentation — state it in Methods.

**Tumour vs. normal slides.** IDC's slide metadata labels 82 slides "Neoplasm, Primary", 114
"Normal", 176 unlabelled, and every patient's *labelled* slides share one type (corrected in the next
entry: 23 patients mix labelled and unlabelled slides): **47 patients have labelled
tumour slides (82 slides)**, 43 have only normal tissue, 88 are unlabelled. Saved as
`external/cptac_coad_slides_idc.csv`. The external test uses the 47 labelled-tumour patients;
the 88 unlabelled are added only if another source (GDC sample types) resolves them. Normal-only
patients are excluded.

**Next:** CPTAC clinical labels from GDC (T, N, histologic type, grade) for these patients,
mapped exactly as `compare_gdc.py` does; then Stage 1 inference with the CV fold models and
the seed-44 model.

### CPTAC-COAD labels and the external-test plan — fixed before any model is run, 26 September

**Labels come from cBioPortal, not GDC.** GDC's CPTAC-2 clinical file has stage only. The
cBioPortal study `coad_cptac_2019` (Vasaikar et al., *Cell* 2019) has, for **110 patients**:
HISTOLOGY (21 mucinous, 88 not, 1 missing), PATHOLOGY_T_STAGE (T2 16, T3 80, T4a 12, T4b 2 — no
T1), PATHOLOGY_N_STAGE (N0 56, N+ 54), plus stage, site, MSI. **No grade**, so grade is not
externally tested. All 110 have feature files; the other 68 IDC patients have no labels and are
not used. Saved as `external/cbio_cptac_coad_{patient,sample}.json`.

**Mapping (`external/cptac_labels.py` → `cptac_labels.json`).** Mucinous: "Mucinous" → True.
pT: T2/T3 → 2/3, T4a/T4b → 4. Node: N0 → False, any N1/N2 → True. No value failed to map.

**The slide-type problem.** Among the 110: **47 have a slide IDC calls "Neoplasm, Primary"**
(82 slides; 10 of them also have unlabelled slides), **56 have only "Normal" and unlabelled
slides**, 7 only unlabelled. That cannot all be right: 01CO001 is a mucinous T4a tumour in
cBioPortal, but its only slide is "Normal". Low-resolution stitch thumbnails
(`external/thumbs_check/`, deleted 26 Sep; regenerable from each H5 file's `stitch` array) were too coarse to settle tumour vs. normal by eye; the `annots`
field in the H5 files is all zeros (no patch annotation), in TCGA as well.

**Decision, made before running anything (pre-registered):**

| | slides in the bag | patients | role |
|---|---|---|---|
| `tumour_slides` | only the "Neoplasm, Primary" slides | 47 | **primary** — like-for-like with TCGA diagnostic (tumour) slides |
| `all_slides` | every slide of the patient (bag = case, as in TCGA) | 110 | sensitivity — more power; broken down by slide group |

If the normal-only group scores as well as the tumour group, either the "Normal" labels are
wrong or the model is not reading tumour — both worth reporting. Small numbers: the primary set
has only 10 mucinous and 5 pT2 cases, so every figure carries a bootstrap 95% CI.

**Models (`stage1/external_test.py`).** Primary: the 5 cross-validation fold models, averaged,
temperature-calibrated with `calibration.json` — the same recipe as the rectal holdout. Also
the seed-44 fixed-split model and the shuffled-label control (the empirical floor). The TCGA
reference is recomputed the same way with pT restricted to T2–T4 so the numbers line up.
Metrics: balanced accuracy + 95% CI, per-class recall, AUROC (mucinous, node), ECE. A feature-
shift check (mean patch norm, centroid cosine, TCGA vs CPTAC) describes the domain gap.

**Known differences, reported and not corrected:** different hospitals; CLAM vs TRIDENT
patching (same 128 µm field); **cBioPortal lists the CPTAC specimens as frozen tissue** (104 of
110) while TCGA diagnostic slides are FFPE — if the slides are frozen sections, a drop in
performance mixes site shift and preparation shift and they cannot be separated. IDC's slide
metadata has no embedding/fixative field for CPTAC, so this is not yet confirmed.

**Rule:** this is a test set. Run once. Nothing (model, temperature, mapping, slide selection)
changes after seeing the numbers; a bug found afterwards is fixed and logged, with both runs kept.

Plumbing checked with `--smoke` on 5 patients in a scratch copy (all three models load, both
selections score, outputs written); the smoke numbers mean nothing.

**Done:** ran `python3 stage1/external_test.py < /dev/null` on the Mac (~10–20 min).

### CPTAC-COAD external test — results, 26 September

Run once on the Mac (MPS), 26 Sep 02:26 IST, from commit 0263217 with `external_test.py`,
`cptac_labels.py` uncommitted (`git_dirty_code: true`, files listed in the results file).
`stage1/external_cptac_results.json`. Balanced accuracy (95% bootstrap CI) and AUROC; pT over
T2–T4 on both cohorts; temperature-calibrated.

| | mucinous bal. acc | mucinous AUROC | pT bal. acc | node bal. acc | node AUROC |
|---|---|---|---|---|---|
| TCGA COAD, out-of-fold (434) | 0.690 [0.61–0.78] | **0.84** [0.77–0.91] | 0.465 [0.40–0.53] | 0.605 [0.56–0.65] | 0.64 |
| TCGA READ holdout (151) | 0.686 [0.53–0.84] | 0.75 [0.53–0.94] | 0.432 | 0.535 | 0.56 |
| **CPTAC primary: tumour slides, CV ensemble (47)** | **0.500** [0.50–0.50] | **0.78** [0.56–0.95] | 0.359 [0.16–0.58] | 0.500 | 0.45 [0.28–0.62] |
| CPTAC all slides, CV ensemble (110) | 0.554 [0.48–0.65] | 0.75 [0.60–0.87] | 0.333 [0.22–0.45] | 0.519 | 0.59 [0.49–0.70] |
| CPTAC tumour slides, seed-44 model | 0.536 | 0.69 [0.48–0.87] | 0.135 | 0.500 | 0.49 |
| CPTAC tumour slides, shuffled control | 0.517 | 0.47 [0.27–0.68] | 0.333 | 0.500 | 0.45 |

**What it says, in plain words**

1. **Mucinous: the signal transfers, the decision threshold does not.** The model still ranks
   mucinous tumours above the others (AUROC 0.78 vs 0.84 on TCGA, control 0.47), but on the
   primary set it called **none** of the 10 mucinous cases mucinous (46/46 predicted "not"), so
   balanced accuracy is exactly chance. The probabilities moved as a block when the hospital
   changed. A threshold fitted on TCGA is wrong on CPTAC.
2. **pT: chance.** Predictions pile onto T2 (29 of 47 predicted T2; 5 are). CPTAC tissue pieces
   were cut for proteomics and are small; depth of invasion — which *is* pT — needs a
   full-thickness section. The model cannot see it, and guesses "shallow".
3. **Node status: chance (AUROC 0.45).** All 47 predicted negative. The TCGA 0.60 came from
   indirect clues that did not survive the move. This backs the decision to make reports
   abstain on node status rather than give a hedged estimate.
4. **Calibration breaks under shift.** ECE rises from 0.03–0.09 (TCGA) to 0.12 (mucinous),
   0.13 (pT), **0.29 (node)** — the model is confidently wrong. Calibration fitted on TCGA
   does not carry over.
5. **The feature spaces are far apart.** Cosine between the TCGA and CPTAC mean UNI2-h vectors
   is 0.48 (1.0 = same centre); mean patch-feature norm 15.5 vs 19.3. Hospital, CLAM vs TRIDENT
   patching and (probably) frozen vs FFPE all contribute; they cannot be separated here.
6. **The "Normal" labels look unreliable.** Patients whose slides are all "Normal"/unlabelled
   give mucinous AUROC 0.78 — as high as the tumour-slide group (0.80). Either those slides do
   contain tumour (as 01CO001 suggests) or normal mucosa carries a mucin signal. Not resolvable
   without looking at the slides at full resolution.

**Why this is a result, not a failure.** It is the reason the thesis has a consistency checker:
a grounded report built from these predictions would state "not mucinous" for all 10 mucinous
CPTAC cases and "node-negative" for 24 node-positive ones, fluently and confidently. The
external test shows *where* grounding on a slide model is safe (a ranking signal for the one
visible field) and where it is not (thresholds, pT from small pieces, anything nodal).

**Pre-registered rule kept:** nothing was changed after seeing these numbers. Anything that now
adapts to CPTAC — e.g. re-centring CPTAC features on their own mean, which uses no labels — is
**exploratory, post hoc**, and must be reported as such, next to these numbers, never instead
of them.

**Thesis wording:** "On an external cohort (CPTAC-COAD, 47 patients), the mucinous signal
transferred (AUROC 0.78, 95% CI 0.56–0.95; TCGA 0.84) but the TCGA-fitted decision threshold did
not (balanced accuracy 0.50); pT and nodal status were at chance and calibration degraded
(ECE up to 0.29)."


### Stage 2 running on the GPU server — first test, 26 September

**Server set-up** (details in `SERVER_SETUP.md`): 2 × RTX PRO 5000 Blackwell (48 GB each), no
SLURM, no admin rights. Worked around: no `python3-venv` (→ `uv`), GitHub blocked (→ uv from its
PyPI wheel), no Python headers for Triton (→ `libpython3.12-dev` unpacked into `~/pydev` with
`apt download` + `dpkg -x`), NCCL hang at start-up with two GPUs (→ `NCCL_P2P_DISABLE=1` and no
custom all-reduce). vLLM 0.30.0, PyTorch 2.13.0+cu130. Hugging Face account re-created
(`labiba26`) after the college email changed; model access re-requested.

**`stage2/generate.py`** — one script, five input arms, three generators (LLM via vLLM, template,
copy-the-neighbour). Prompt v1 frozen in the file and saved with every run. Greedy decoding,
seed 0, repetition penalty 1.1 (without it MedGemma 4B looped until the length limit on the
ungrounded arms — a strawman a reviewer would reject). Every output scored by the Stage 3
checker on the spot: faithfulness to the input and correctness against the extracted labels.
Code travels to the server as `stage2_bundle.tar.gz` (`stage2/make_bundle.sh`), which records the
git commit it was packed from.

**Smoke test, 10 cases (5 COAD test + 5 READ), MedGemma 27B text, bf16 on both GPUs:**

| arm | fields vs input: correct / omitted | unsupported fields | extra claims | node abstained | vs labels: correct / incorrect |
|---|---|---|---|---|---|
| none (strict prompt) | – | 20 | 0 | 10/10 | 16 / 3 |
| none_free | – | 30 | **40** (all 10 reports) | 0 | 21 / 8 |
| retrieval | – | 16 | 4 | 6/10 | 10 / 5 |
| **predicted** | **30 / 0** | **0** | **0** | **10/10** | 18 / 11 |
| extracted | 34 / 5 | 0 | 0 | – | 34 / 0 |

- **Grounded generation is faithful:** with predicted findings the 27B model stated every finding,
  added nothing, abstained on nodes every time and flagged low-confidence findings as uncertain.
  Its 11 errors against the labels are Stage 1's errors, carried through — which is the point of
  the design: an error is traceable to a field.
- **Unconstrained, it invents a full report:** tumour size, lymphovascular invasion, "3 of 18"
  nodes, margins — 40 unsupported claims in 10 reports.
- **The strict ungrounded arm guesses the common answer** (moderately differentiated, pT3) and
  scored 16 correct against the labels in 10 cases. So raw correctness rewards majority-class
  guessing, exactly as raw accuracy did in Stage 1. **Stage 2 correctness must be reported per
  class (balanced), not as a raw count** — to add to the scoring before the full run is analysed.
- MedGemma 4B (same test) omitted 11/30 input findings, never wrote the abstention sentence and
  looped without the repetition penalty. **Decision: MedGemma 27B is the primary LLM**; 4B and
  Llama 3.1 8B are secondary.
- Found for the double annotation: one extracted-arm report said "invades through the muscularis
  propria (pT2)" — internally contradictory (through = pT3). The checker read pT2 and scored it
  correct. Rule-based checking cannot see this; the human double annotation must look for it.

**Next:** commit, rebuild the bundle, then the full core run (MedGemma 27B, all five arms,
test_coad + holdout_read; template and copy baselines; the CPTAC predicted/none arms).


### A checker gap found in the first full Stage 2 run — written down BEFORE the fix, 26 September

Scoring the full run showed every ungrounded report scoring 0 on pT. Reading the reports:
they describe depth in words ("invades through the muscularis propria into the pericolic
fat" = pT3; "invades the submucosa" = pT1), and the checker reads pT only as a code
("pT3"). The grounded arm writes the code because its input contains it. **Left alone, this
gap would inflate the grounded-vs-ungrounded difference** — a bias in our favour, which is
exactly the kind a reviewer would find.

Before writing any fix, a second frozen held-out set was written: `stage3/heldout2_depth.py`,
15 sentences with the expected pT from the AJCC 8th edition definitions, including traps
(node sentences, negations, an intact muscularis propria, a bladder invasion the rule may
miss). SHA-256 of the file before the fix:
`a4410a71df6bd139a8502b5ab271503f3cffc74855d59f7579b47ee8bd4ee244`.
Checker v1 on it: **5/15** (only the code and the no-depth sentences).

The fix, the rerun of all checker tests and the held-out-2 result follow in the next entry.


### Checker v1.1 (depth in words) and the first full Stage 2 results — 26 September

**The fix.** `consistency.py` now reads depth of invasion written in words when no pT code is
present (AJCC 8th edition wording; node sentences and negated sentences skipped; deepest level
in the report taken). Results, each run once:

| check | v1 | v1.1 |
|---|---|---|
| unit tests (`test_consistency.py`) | pass | pass |
| planted-error suites | — | **identical** results file (no change) |
| held-out set 1 (frozen 24 Sep) | 65/72 = **90.3%** (the quoted figure) | 66/72 = 91.7% (saved separately as `heldout_results_v1.1.json`; the fix was not made for this set) |
| held-out set 2, depth in words (frozen before the fix) | 5/15 | **14/15** — the miss: "directly invades the urinary bladder" (pT4b, an organ name the rule does not list) |

Checked on the real outputs: "invades through the muscularis propria into the pericolic fat"
→ pT3, "invades the submucosa" → pT1. One copied real report ("Invades other organs (specify)")
was read as pT4 from a tick-box form line — the Phase 4 form problem again, limited to the
copy baseline.

**Full core run** (commit 286ea35; MedGemma 27B text, bf16, 2 GPUs; prompt v1; greedy, seed 0,
repetition penalty 1.1; 1,215 TCGA + 188 CPTAC generations; template and copy baselines;
0 reports truncated). Scored by `stage3/score_stage2.py` (checker v1.1) →
`stage3/stage2_scores.json`. Balanced correctness over the visible fields (type, grade, pT);
chance = mean of 1/K = **0.36** on TCGA, **0.42** on CPTAC (no grade; pT has 3 classes there).

| arm | COAD test (87) | READ holdout (156) | CPTAC (47) | reports with invented extra claims |
|---|---|---|---|---|
| **MedGemma, predicted findings** | **0.55** [0.45–0.68] | **0.50** [0.42–0.58] | 0.43 [0.33–0.54] | **0%** |
| Template, predicted findings | 0.55 | 0.50 | – | 0% |
| MedGemma, no findings, plain prompt | 0.36 (= chance) | 0.36 | 0.42 (= chance) | **100%** (LVI, margins, node count, size in every report) |
| MedGemma, no findings, strict prompt | 0.19 | 0.20 | 0.25 | 0% |
| MedGemma, similar case's report | 0.20 | 0.21 | – | 5–9% |
| Copy of the similar case's report | 0.36 | 0.38 | – | 93–97% (≈4.5 claims per report) |
| MedGemma, extracted findings (upper bound) | 1.00 | 1.00 | 1.00 | 0% |

Faithfulness of the grounded arm: every given field stated correctly in all 243 TCGA reports
(0 contradicted, 0 omitted), node status never stated, the abstention sentence in 100%.

Paired differences, same cases (bootstrap 95% CI), predicted minus plain-prompt ungrounded:
COAD **+0.19 [+0.09, +0.31]**, READ **+0.14 [+0.06, +0.22]**, CPTAC +0.01 [−0.09, +0.12].

**What this says, and what it does not:**

1. **Grounding removes invented content.** Without findings the model writes one confident
   report for every patient — only 3 distinct texts across 243 cases, because decoding is
   deterministic and the input carries no patient information — each with lymphovascular
   invasion, margins, a node count and a size that nothing supports. With findings: none.
2. **Grounding makes reports more correct than chance, but only as far as Stage 1 is.** The
   gain over the ungrounded report (+0.14 to +0.19) is exactly Stage 1's own balanced accuracy
   carried through: the LLM's per-field numbers match Stage 1's own cross-validated balanced accuracy (COAD test: type 0.75, grade 0.50, pT 0.40 vs Stage 1 0.75 / 0.50 / 0.40; READ within 0.02) and equal the template's. On CPTAC,
   where Stage 1 fails (threshold shift), the grounded report is no better than chance either.
   The report is as good as the evidence under it — which is the argument for grounding and
   for abstaining where the evidence is absent.
3. **The LLM adds nothing over the template on these metrics.** Same correctness, same
   faithfulness. Its possible value is readability, which is not measured yet (BLEU/ROUGE and
   CRQS are next). This must be said plainly in the thesis.
4. **The strict ungrounded prompt is not a fair correctness baseline.** It mostly declines to
   state grade and pT (scored "not stated" = wrong), so it sits below chance; yet it still
   invented "invades the submucosa" (pT1) in 52 of 243 reports. The fair correctness contrast
   is against the plain-prompt arm (= a constant guess, = chance); the strict arm is the
   instruction-following contrast.
5. **Retrieval** (the standard baseline in report-generation work): copying the neighbour's
   report is at chance on the four fields and carries ~4.5 claims about a different patient per
   report; the LLM given that report mostly declines.

**Checker caveat in the numbers:** correctness is read by the rule-based checker; held-out
accuracy 90–92% per verdict. The double annotation of ~60 generated reports is what validates
these specific numbers.

**Next:** BLEU/ROUGE/BERTScore and CRQS against the real reports (secondary); MedGemma 4B and
Llama 3.1 8B on the same arms; select the ~60 reports for double annotation (stratified by arm
and by the rare classes); HistGen.


### Gold labelling: annotators read the original PDFs — 27 September

Labiba found the `.txt` reports unreadable: they are OCR transcriptions, and tick-box forms
come out garbled. The original scanned PDFs (from GDC, already in `reports/`) were copied to
`gold_labels/reports_pdf/` for all 50 gold and 5 practice cases, named like the sheet rows, and
`GUIDE.md` now says: read the PDF; a filled circle is the ticked answer; the PDF wins over the
text. Both annotators get the same PDFs and the same note, so the two sheets stay comparable.

**Why this is better, not just easier:** the gold standard should record what the report
actually says. The weak labels were extracted from the OCR text, so any disagreement between
the extractor and a PDF-based gold label now measures OCR + extractor error together — which is
the honest measure of label quality. Record in Methods: "gold labels were assigned from the
original scanned reports".


### Gold labelling changed: one human annotator + an LLM annotator — 28 September

The second human annotator withdrew (**corrected 4 Oct: he has not; see the 4 Oct entry**). The design was then:

- **Human annotator:** Labiba, `gold_labels_A.xlsx`, from the original PDFs.
- **LLM annotator:** Claude, labelling the same 50 reports **blind** — the original PDFs only,
  under the same written rules (`GUIDE.md` + the 27 Sep PDF note), never opening
  `structured_labels.json`, GDC data or the .txt transcriptions. Five parallel readers, one
  review fix before locking (G50 node count read as 0/10 from the Polish Roman-numeral form
  "(No X)", consistent with G10 and G27). Locked file:
  `gold_labels/llm_annotator/labels_llm.json`,
  SHA-256 `773fe33845693662ee1ee4303de90f8af146cff7eba2dcc11a8c0a8afe4515ce`.
  19 of 50 marked "unsure", each with the reason and the key phrase quoted.
- **Adjudication:** Labiba resolves every disagreement by re-reading the PDF. The adjudicated
  labels are the gold standard.

**What this can and cannot claim (for Methods and Limitations):** this is one human annotator
cross-checked by an independent LLM reading, not two human annotators. Human-LLM agreement is
reported, but it is not inter-human agreement. The LLM annotator is the same model family that
helped write the rule-based extractor, so a shared blind spot is possible; the human reads
every disagreement, which is the safeguard. This is also the "LLM label cross-check" already in
the plan (Phase 13) — now done on the gold set.

**Blind order kept:** Labiba does not open the LLM file until her sheet is finished.


### Gold labelling: reports with more than one tumour — 29 September

Labiba noticed that some reports describe two tumours, each with its own type, pT and pN; the
sheet had one set of columns. Rule added to `GUIDE.md` (28 Sep update), following the **AJCC 8th
edition rule for multiple synchronous primaries**: the main sheet holds the **index tumour** — the
highest pT; ties → higher grade → larger; a tumour the report names as main; or the report's own
combined stage when it gives one for both. Not a second tumour: mixed histology, adenomas without
carcinoma, other organs, metastases, history. An intramucosal carcinoma in an adenoma elsewhere
counts (pTis). Nodes: one count for the specimen goes with the index tumour.

The other tumour goes in a new companion sheet, `gold_labels_A_multiple_tumours.xlsx` (same
drop-down values, "Rules" tab). A separate file, because 22 rows of the main sheet were already
filled and rewriting that workbook with openpyxl would have removed its drop-down lists.

LLM annotator, blind, all 50 PDFs re-read for multiplicity only (main labels unchanged): **3 of 50**
have more than one carcinoma — G04 (bifocal, one combined stage pT3 pN0), G22 (two specimens:
cecum pT3 pN2 index; second colon segment pT1 pN0, 0/6), G44 (rectal pT2 index; intramucosal
carcinoma in a separate adenoma, pTis). In all three the index tumour already in
`labels_llm.json` follows the new rule. Locked file:
`gold_labels/llm_annotator/labels_llm_multiple_tumours.json`,
SHA-256 `5d25f5e2e6a07fd93441f152a6f513de33ca0620d0ce23946405a4600f651d33`.

**Why it matters for the model:** the slide is from one tumour, and the weak labels and Stage 1
targets carry one value per case. For multi-tumour cases the thesis uses the index tumour, and
names the (small) risk that the TCGA slide was cut from the other one as a limitation.


### Secondary LLMs run; a second checker gap found — written down BEFORE the fix, 29 September

Llama 3.1 8B and MedGemma 1.5 4B ran on all arms (commit d1754c4, clean; same prompt v1 and
settings as MedGemma 27B; 1,215 TCGA + 188 CPTAC reports each). Scoring showed MedGemma 4B
"omitting" the grade in 44/87 and 90/156 predicted-arm reports. Reading them: it writes grade as
a noun ("adenocarcinoma with **moderate differentiation**": 112 of 243 predicted-arm reports, 149
of 243 extracted-arm) and margins verb-first ("the tumour **involves the lateral margin**": 18
reports). Checker v1.1 reads neither — a checker gap that would unfairly penalise the 4B, and
under-count its invented margin claims. MedGemma 27B and Llama are barely affected (0 predicted-arm
reports; 1–11 in other arms).

Before any fix, a third frozen held-out set was written: `stage3/heldout3_wording.py`, 10 grade and
8 margin sentences with expected answers (traps: a negated grade, "moderate lymphocytic
infiltration", "margins cannot be assessed"). SHA-256 before the fix:
`6653ed0d8a609215bd4ea3ecb128e67b17eba44998d10a27d984e7d348c7ee68`. Checker v1.1 on it: **9/18**.


### Checker v1.2 and the three-LLM comparison — 29 September

**The fix.** Grade as a noun ("moderate differentiation", "Differentiation: poor") and margins
verb-first ("involves / reaches / extends to the … margin"), read only when v1.1 finds nothing.
Each check run once:

| check | v1.1 | v1.2 |
|---|---|---|
| unit tests | pass | pass |
| planted-error suites | — | detection identical; one more real report counted as mentioning margins (69.1% → 69.3%) |
| held-out 1 (quoted 90.3%) | 66/72 | 66/72 (v1.2 re-score kept as `heldout_results_v1.2.json`) |
| held-out 2, depth in words | 14/15 | 14/15 |
| held-out 3, grade/margin wording (frozen before the fix) | 9/18 | **17/18** — the miss, "There is no poorly differentiated component" → G3, is in the original report extractor (`extract_fields.py`), left unchanged because the training labels come from it |

MedGemma 27B's scores are **unchanged** under v1.2 (the gap never touched its outputs).

**Three LLMs, same prompt and settings** (visible-field balanced correctness, 95% CI; chance 0.36
TCGA / 0.42 CPTAC):

| | COAD test (87) | READ (156) | CPTAC (47) | faithful to given fields | invented-claim reports (grounded) | node abstention | cut off |
|---|---|---|---|---|---|---|---|
| **MedGemma 27B**, predicted | 0.55 [0.46–0.68] | 0.50 [0.41–0.59] | 0.43 | 100% | 0% | 100% | 0 |
| **Llama 3.1 8B**, predicted | 0.55 [0.46–0.68] | 0.50 [0.41–0.59] | 0.43 | 100% | 0–1% | 100% | 0 |
| **MedGemma 1.5 4B**, predicted | 0.48 [0.38–0.60] | 0.47 [0.38–0.56] | 0.32 | 81–93% | 8–17% | 69–81% | 8–12 |
| any model, no findings, plain prompt | 0.25–0.36 | 0.25–0.36 | 0.42 | – | 100% | 0% | 0 |

Paired gain of the grounded report over the plain ungrounded one: MedGemma 27B +0.19 / +0.14;
Llama +0.19 / +0.14; MedGemma 4B +0.23 / +0.22 (its ungrounded reports sit below chance, 0.25).
CPTAC: +0.01, +0.01, −0.09 — no gain anywhere, because Stage 1 fails there.

**What it says:**
1. **The result is not specific to one LLM.** Two capable models (a medical 27B and a general 8B)
   give identical correctness, 100% faithfulness and full node abstention. Grounding, not the
   model, sets the correctness.
2. **Model size matters for faithfulness, not for the principle.** MedGemma 4B drops or garbles
   7–19% of the given fields, adds claims in 8–17% of grounded reports, skips the node sentence in
   a fifth to a third of reports, and runs past the length limit in ~5%. Still far fewer invented
   claims than any ungrounded arm (100%).
3. **Retrieval differs by model:** Llama copies the neighbour's findings (0.34–0.35 correctness,
   32–36% of reports carry the other patient's claims); MedGemma 27B mostly declines (0.20). Both
   are at or below chance.
4. **A checker gap favoured nobody this time but would have penalised one model**: found by reading
   reports behind a surprising number, fixed with a frozen test first — the same procedure as v1.1.


### Honest self-assessment and the improvement plan, from a literature check — 29 September

Known weaknesses (stated to Labiba as a brutal review): the grounded-vs-ungrounded headline is close
to true by construction; Stage 1 is weak (grade/pT near chance, node at chance, mucinous on 6/10
positives); the reports are thin (three findings); the plain-prompt ungrounded arm is partly a straw
man; evidence rests on one human plus an LLM; one organ, small n. Recent literature (summaries read,
not full texts — open each before citing) suggests these fixes:

| Weakness | Fix | Precedent | Effort |
|---|---|---|---|
| Headline "by construction" | Make the contribution **uncertainty-aware reporting**: state a finding only above a confidence threshold, else abstain; risk-coverage curve on TCGA and CPTAC | Wang et al. (arXiv:2412.04606): abstaining on the top 20% most uncertain reports gains 9-10% factuality; Lee et al. NeurIPS 2024 (selective generation, guaranteed error rate) | Medium. Uses existing calibrated probabilities |
| Also "by construction" | **Error-injection test**: edit one finding (wrong grade, wrong pT), measure whether the report repeats it or flags it | Bhowal et al. (arXiv:2607.27304), same design on MedGemma | Low-medium |
| Stage 1 weak | Predict what slides show: **MSI status** (well validated from H&E; TCGA labels; CPTAC cBioPortal has MSI_STATUS 81 MSS / 24 MSI-H already downloaded; SurGen has mismatch-repair labels) plus mucin %, necrosis, differentiation | Aswolinskiy et al. 2025 (medRxiv): abstention gives 59-78% coverage at over 97% sensitivity. Caution: CPTAC is in THEIR training set | Medium. New head, same features |
| Reports thin | Extend the findings set (MSI, mucin %, budding-type fields) so the reports carry more; report the checker's coverage of what real reports say | PathReportEval (TCGA hallucination rate ~0.5) | Medium |
| Straw-man baseline | Keep the plain arm but add stronger ones: retrieval already; add HistGen (published) and a slide-level VLM (SlideChat); report per-field, not only totals | HistGen; SlideChat (CVPR 2025); Simple Token-Efficient VLM (arXiv:2605.30716) | Medium-high (server) |
| Standard metrics | **Show BLEU/ROUGE/BERTScore do not separate grounded from invented reports** | PathReportEval states this weakly, without a controlled test; RadEval/GREEN in radiology | Low. Needs only files on the Mac |
| Single-person evidence | Human double-check of ~60 reports; checker vs CRQS vs an LLM judge, agreement reported; release the frozen tests | PathReportEval does NOT validate CRQS against human raters (a gap we can fill) | Medium |
| One organ, small | External cohort with reports: HISTAI (colorectal subsets, conclusions and microscopic descriptions, CC BY-NC 4.0); SurGen (843 CRC cases) for molecular fields | HISTAI, SurGen | Medium-high |

**Novelty check from this search:** PathReportEval (July 2026) already benchmarks four report models
with CRQS, but does not test abstention, calibration, field visibility, external cohorts, or human
validation of its metric. Those gaps are exactly where this thesis can sit.

**Priority order:** (1) fluency metrics vs faithfulness; (2) selective/abstaining reports with
risk-coverage; (3) checker validated against humans, CRQS and an LLM judge; (4) error injection;
(5) MSI as a new visible field; (6) HISTAI as a second cohort; (7) HistGen / SlideChat baselines.


### Improvement item 1: do BLEU/ROUGE tell faithful reports from invented ones? — 29 September

`stage3/score_fluency.py` → `stage3/fluency_scores.json`. BLEU-4 and ROUGE-1/2/L (own implementation)
of every generated TCGA report (243 test cases, three LLMs plus template and copy) against the
patient's real report, next to what the checker says about the same reports. Bootstrap 95% CIs over
cases; paired differences on the same cases. Reference = real report, unedited (median ~900 words;
generated ~50), so absolute scores are low for every arm. BERTScore not run (needs a model download).

MedGemma 27B (paired difference in ROUGE-1 / ROUGE-L / ROUGE-L precision, 95% CI):

| contrast | ROUGE-1 | ROUGE-L | ROUGE-L precision |
|---|---|---|---|
| **grounded** (predicted) − **invented** (no findings, plain prompt) | +0.004 [−0.001, +0.008] | −0.002 [−0.006, +0.001] | **−0.078** [−0.088, −0.068] |
| **all fields right** (extracted) − invented | −0.003 [−0.007, +0.001] | −0.004 [−0.008, −0.000] | −0.009 [−0.018, −0.001] |
| grounded − **copied neighbour report** (another patient's real report) | **−0.275** [−0.302, −0.249] | **−0.210** [−0.234, −0.187] | −0.110 [−0.140, −0.082] |

**What it says**
1. **Overlap metrics cannot tell the grounded report from the invented one.** ROUGE-1 and ROUGE-L
   show no difference; the precision-based versions (BLEU-4 without brevity penalty, ROUGE-L
   precision) rate the invented report *higher*. The same pattern holds for Llama 3.1 8B.
2. **A report with every field right scores no better than one that invents margins, LVI and a
   node count** (differences of −0.003 to −0.009).
3. **Copying another patient's real report wins on every metric** (ROUGE-L 0.32 vs 0.11; still
   ahead on precision, 0.35 vs 0.24), although 95% of those copies carry that other patient's
   claims and correctness is at chance. This is the standard "retrieval" baseline in the literature.
4. **Overlap metrics do carry a weak signal about correctness** (Spearman 0.11–0.37 with the number
   of correct fields, pooled per model) and almost none about invention (−0.32 to +0.22, mixed sign).
   So "useless" would be wrong; "cannot see invention" is right.

**Caveats to state:** length differs ~20-fold between generated and real reports; the real reports are
OCR text with form boilerplate; "correct fields" comes from the checker; PathReportEval (July 2026)
already argues overlap metrics overestimate quality, so the contribution here is the *controlled*
version — same generator, same cases, grounding as the only change, with the perfect-findings
upper bound — not the general observation.


### Improvement item 2: selective (abstaining) reporting — plan fixed BEFORE running, 29 September

Rule: a report states a finding only if Stage 1's calibrated confidence for it is at least a
threshold; otherwise it says the finding cannot be determined. Node status is always abstained
(visibility rule), so this is about type (mucinous), grade and pT.

Fixed in advance (`stage3/selective_reporting.py`):
- **Thresholds are chosen on validation data only**: the cross-validation early-stopping splits
  (260 cases, 52 per fold). For each COAD held-out fold k, temperature and threshold are refitted
  on validation cases *excluding* fold k (cross-fitting, as in `calibrate.py`); READ and CPTAC use
  all validation cases. Test sets are never used to pick anything.
- **Two operating points per field**: the lowest threshold whose validation selective accuracy
  (accuracy among stated findings, at least 10 stated) reaches **0.90**, and the same for **0.80**.
- **Reported on COAD out-of-fold (434), READ (156), CPTAC tumour slides (47)**: coverage,
  selective accuracy, **balanced** selective accuracy, **per-class coverage** (does abstention
  silently drop the rare classes — mucinous, G1/G3, pT1/pT4?), full risk–coverage curve, AURC against
  a random-abstention baseline, and the report-level share of cases with any wrong stated finding.
- Main risk stated in advance: accuracy-based thresholds favour the majority class. If abstention
  mostly removes minority-class cases, that is the finding, and it will be reported as such.

### Improvement item 2: results — 29 September (`stage3/selective_reporting.json`)

Run once, with the plan above unchanged. Numbers are against the weak labels.

**1. Confidence is informative: it beats random abstention everywhere.** Area under the
risk–coverage curve (AURC, lower is better) against random abstention:

| Field | COAD (out-of-fold) | READ | CPTAC |
|---|---|---|---|
| Mucinous | 0.037 vs 0.079 | 0.030 vs 0.066 | 0.110 vs 0.217 |
| Grade | 0.235 vs 0.359 | 0.168 vs 0.259 | — (no CPTAC grade) |
| pT | 0.434 vs 0.485 | 0.376 vs 0.465 | 0.667 vs 0.745 |

The cases Stage 1 is unsure about really are the ones it gets wrong more often, including on
the external cohort. The pT gain is small.

**2. But the pre-registered rule mostly keeps the majority class, as the stated risk warned.**

- **Mucinous — no abstention at all.** Accuracy is already above 0.90 with every case stated
  (COAD 0.92, READ 0.93), so the chosen threshold (0.30) never removes anything. Balanced
  accuracy stays 0.69. **Of the 34 mucinous tumours in COAD, only 41% are called mucinous**;
  READ 4/10. On CPTAC, accuracy 0.78 but balanced 0.50: **all 10 mucinous tumours are called
  non-mucinous**, and no abstention catches them. The risk–coverage curve shows that a lower
  coverage would have helped (COAD risk about 2% at 30–45% coverage, versus 8% at full
  coverage). The *accuracy* target simply never asks for it.
- **Grade.**
  - COAD at 0.90: 14% of cases stated, accuracy 0.88 but balanced 0.59. Stated: G1 2/17
    (both wrong), G2 39/276 (95% right), G3 11/91 (82% right).
  - COAD at 0.80: 51% stated, accuracy 0.75, balanced 0.47 (G1 7 stated, all wrong).
  - READ at 0.90: nothing stated (threshold 0.89). At 0.80: 39% stated, accuracy 0.91,
    balanced 0.52, 46 of the 54 stated are G2.
  - So a confident grade is almost always "moderately differentiated". G1 is never stated
    correctly.
- **pT — never stated.** No threshold reaches even 0.80 on validation, so every report says
  depth cannot be determined (COAD, READ, CPTAC).

**3. Report level.** "Wrong" means the report states at least one finding that disagrees
with the label:

| | COAD 0.90 | COAD 0.80 | READ 0.90 | READ 0.80 | CPTAC 0.90 / 0.80 |
|---|---|---|---|---|---|
| Fields stated per report (of 3) | 1.07 | 1.40 | 0.97 | 1.32 | 0.98 |
| Reports with a wrong finding | 8.9% | 17.8% | 6.5% | 9.0% | 21.3% |
| Reports stating nothing | 4.9% | 4.0% | 2.6% | 1.9% | 2.1% |

On CPTAC, the 21.3% is exactly the 10 missed mucinous tumours (10/47).

**What this means.**

- Abstention makes the reports safer but thinner: about one finding per report, usually
  "not mucinous".
- The errors that remain are concentrated in the rare, clinically interesting cases
  (mucinous, G1).
- An *overall-accuracy* target is the wrong target for imbalanced findings.
- This is reported as a negative result for this rule, not hidden. It matches the
  selective-prediction literature on class imbalance.

**Next, if kept:** a class-aware rule, to be pre-registered before running:

- For each *predicted* class, state it only if that class's validation precision reaches
  the target (for example Mondrian / class-conditional conformal).
- Report per-class recall alongside.

Not run yet.

### Improvement item 2b: per-answer (class-aware) abstention — plan fixed BEFORE running, 29 September

Why: item 2's overall-accuracy target was met by the majority class, so rare classes were never
protected. Rule here (`stage3/selective_per_class.py`):

- Each **answer** (class) gets its own threshold. A predicted class c is stated only if its calibrated
  confidence is at least t_c. t_c is the lowest grid value (0.30–1.00) at which validation cases
  *predicted as c* with confidence at least t_c are right at least the target share of the time
  (precision per answer), with at least **5** such cases. If no value qualifies, c is never stated.
  Below threshold, the report abstains; it never falls back to the second-best class.
- Same data discipline as item 2: validation logits only, cross-fitted per COAD fold, temperature
  from `calibrate.py`. Targets **0.95, 0.90, 0.80**. The 0.95 target is added now, before running.
- Reported as for item 2, plus **per-class recall** (share of each true class stated *and* correct)
  and the report-level share of reports with a wrong finding, side by side with item 2's rule.
- Expectation stated in advance: this rule can stop a common answer from being stated when that
  answer is unreliable, but it **cannot create** rare-class calls the model never makes. On CPTAC,
  Stage 1 predicts no case as mucinous, so no rule of this kind can fix the 10 missed tumours. If
  "not mucinous" is already at least 90% precise, the 0.90 target changes nothing for type; 0.95
  may.

### Improvement item 2b: results — 29 September (`stage3/selective_per_class.json`)

Run once, with the plan above unchanged. The overall-rule rows reproduce item 2 exactly (a check
that the two scripts agree).

**Mucinous — the per-answer rule makes type worse.** Validation "mucinous" calls never reach even
80% precision with at least 5 cases, so the answer "mucinous" is never stated at any target.
"Not mucinous" keeps threshold 0.30, so it is always stated.

| COAD out-of-fold (34 mucinous, 371 not) | Mucinous called correctly | Mucinous called "not mucinous" | Balanced |
|---|---|---|---|
| No abstention / overall rule | 14 | 20 | 0.69 |
| Per-answer, 0.95 or 0.90 | 0 | 20 | 0.50 |

- The 20 mucinous tumours that Stage 1 calls "not mucinous" are called **confidently**, so no
  threshold removes them.
- The rule only removes the correct *and* false "mucinous" calls. READ is the same (4 → 0 of 10).
  CPTAC is unchanged: Stage 1 never predicts mucinous there.

**Grade and pT.**

- Grade at 0.90: about the same as the overall rule (COAD 15% stated, accuracy 0.86, balanced
  0.58). G1 is never stated correctly.
- pT at 0.80 is now sometimes stated: COAD 18% of cases, accuracy 0.75, almost all pT3; READ 10%,
  accuracy 0.92. CPTAC none.

**Report level (share of reports with a wrong finding).**

| Rule | COAD | READ | CPTAC |
|---|---|---|---|
| Overall 0.90 (item 2) | 8.9% | 6.5% | 21.3% |
| Per-answer 0.90 | 6.5% | 4.5% | 21.3% |
| Per-answer 0.95 | 5.6% | 3.9% | 21.3% |

The per-answer rule cuts wrong reports a little further, but by saying less: 11% of COAD reports
state nothing at 0.95.

**What this means (the finding of items 2 + 2b together).**

- Abstention can only remove *unsure* errors. Stage 1's worst errors are **confident misses of the
  rare class** (mucinous called "not mucinous"), and no threshold rule, overall or per answer, can
  catch them.
- A safe report therefore needs a better Stage 1 for rare classes, not a better threshold. This
  is a direct argument for improvement item 5.
- A report could say "mucinous cannot be excluded" instead of "not mucinous" when the rare-class
  probability is above its base rate. Not tested; noted for Future Work.

### Improvement item 4: error injection — plan fixed BEFORE running, 29 September

**Correction first.** On 29 Sep I described item 4 to Labiba as "plant mistakes in reports and see if
the checker catches them". That was wrong: `planted_errors.py` (Phase 12) already does that. Item 4,
as in the improvement table, changes the LLM's **input** and asks what the report does with it.

Question: when Stage 1 hands Stage 2 a wrong finding, does the LLM
- (a) **repeat** it (faithful to its input, so the error stays traceable to Stage 1),
- (b) **silently correct** it to the true value (unfaithful; could only come from guessing), or
- (c) drop it?

And when the wrong finding carries a low confidence, does the report **hedge** it as the prompt
requires?

Design (`stage2/generate.py`, new arms `injected` and `injected_low`, not part of `--arms all`):
- Start from the **extracted** findings (the weak labels: correct as far as we know).
- Change exactly **one** field to a wrong value. The field is chosen per case by a fixed hash of the
  case ID, rotating grade → pT → type, skipping fields the case lacks.
- Wrong values are the neighbouring class: grade 1→2, 2→3, 3→2; pT 1→2, 2→3, 3→4, 4→3;
  adenocarcinoma ↔ mucinous. Node status is left as extracted.
- `injected`: the wrong value with no confidence. `injected_low`: the same wrong value at "model
  confidence 40%", below the prompt's 60% hedge line.
- Same prompt (v1), same 243 TCGA test cases (test_coad + holdout_read), greedy decoding. Generators:
  template (sanity check: must repeat 100%), MedGemma 27B, Llama 3.1 8B, MedGemma 4B (server).
- Scored by `stage3/score_injection.py`, per generator and arm: share repeated / corrected / dropped /
  other value for the injected field, using the frozen checker (v1.2).
- For `injected_low`: share of reports where the sentence stating that field contains a hedge word.
  This uses the checker's existing hedge pattern, but at sentence level. **This hedge measure is new
  and not validated on frozen tests**; it is reported as approximate, with examples.
- Expectation stated in advance: near-100% repetition for all LLMs, which is what grounding means.
  The value of the test is showing that Stage 2 does not hide or "fix" Stage 1 errors, and that the
  checker attributes them correctly (faithful to the input, wrong against the label). Silent
  correction above a few percent would be a problem for the method and will be reported as one.

**Checker bug found by the template sanity check (before any LLM run).** The template writes
"mucinous adenocarcinoma (model confidence 40%)", and checker v1.2 read it as *not* mucinous in 75
of 83 such reports. The type rule (from `extract_fields.py`, WHO >50% mucin) takes any percentage
of 50 or less within 60 characters as the mucin share, so a model confidence under 50% flips it.
Following the rule, a frozen test was written before the fix: `stage3/heldout4_confidence.py` (14
sentences: 8 traps, 6 controls where a real mucin share must still decide), SHA-256
a8f785dc8e59d9e9feeb44724b18cc7ed55f7dd4db873c889493220b6b627b6b. A `VERSION` constant was added to
`consistency.py` (no behaviour change) so results are keyed by checker version.

**Before the fix, v1.2: 5/14** (`heldout4_results.json`). All 8 traps failed, and so did one
control: "Adenocarcinoma, not of mucinous type" was read as mucinous (a second gap, negation).

**Fix → checker v1.3** (`consistency.py` only; the label extractor is untouched, because real
reports carry no model confidences):
- confidence/probability percentages are masked before the type is read;
- "not (of) mucinous (type)" / "non-mucinous" is read as adenocarcinoma.

**After, v1.3: 14/14.** The other frozen sets are unchanged:
- held-out 2: 14/15;
- held-out 3: 17/18;
- held-out 1: 66/72, the same as v1.1 and v1.2. 65/72 stays the quoted frozen first result.
  Its results file was overwritten by the re-run; restored from git, and the new run was saved
  as `heldout_results_v1.3.json`.
- Unit tests pass.

**Effect on earlier results: none.** All Stage 2 reports were re-scored with v1.3, and
`stage2_scores.json` is byte-identical to v1.2. The bug only fires when "mucinous" sits near a
percentage of 50 or less. Stage 1's mucinous calls always carry at least 50% confidence (binary
argmax), and no generated report is read differently by v1.3.

`score_stage2.py` now skips `*_injection` runs. The first re-run included the new folder, which
shifted the shared bootstrap seed and moved CI bounds by up to about 0.01; point estimates were
unchanged.

**Template sanity check (v1.3), `stage3/score_injection.py`:**
- 242 of 243 cases injected (one case has none of the three fields).
- The injected value is repeated in 100% of reports in both arms, as it must be.
- Hedging in `injected_low`: 100% by the checker's pattern, 0% strict. The template prints "model
  confidence 40%" but never says "uncertain", so the strict measure is the informative one.

**LLM runs: DROPPED, 29 Sep (Labiba's decision).** The expected result, that the LLM repeats the wrong
finding, is predictable and would add little. The server time and write-up are better spent on the
checker validation and Stage 1. What stays: the template sanity run and the checker v1.3 fix it led to.
The `injected` arms in `generate.py` and `score_injection.py` are kept, unused, for anyone who wants
to run it later.
`generate.py` has new arms `injected` / `injected_low` (`inject()`); `--arms all` is unchanged.

### Improvement item 3: is the checker right about generated reports? — plan fixed BEFORE building, 29 September

The checker has been tested on templates, real reports and frozen sentences, but never against an
independent reader on the **LLM-written** reports it actually scores. Plan
(`stage3/make_checker_sheet.py`, `stage3/score_checker_validation.py`):

- **Sample: 60 generated TCGA reports** (test_coad + holdout_read).
  - 3 LLMs (MedGemma 27B, Llama 3.1 8B, MedGemma 4B) × 4 arms (predicted, extracted, none_free,
    retrieval) × 5 reports, drawn at random (seed 29) from the checker v1.3 outputs.
  - 60 **different** cases; the 50 gold-label cases are excluded, so this cannot prime the gold
    labelling. Shuffled as C01–C60.
- **The reader sees only the report text**: no model, arm, input findings or checker output. So the
  reader records *what the report says*, and faithfulness and correctness follow mechanically, the
  same way the checker's do.
- Per report, dropdowns:
  - type (not stated / adenocarcinoma / mucinous / signet-ring);
  - grade (not stated / G1–G4);
  - pT (not stated / pT1–pT4);
  - node (not stated / cannot be assessed / negative / positive), and node hedged (yes / no);
  - one yes-column per extra-claim kind the checker knows: LVI, margins, node count, pN, size,
    distant metastasis, MSI/MMR, perineural, budding, other staging, treatment; plus "other claim
    beyond these" (free text).
- **Readers:**
  - (1) Labiba, after her gold labels. About 45–60 minutes: reports average 29–97 words.
  - (2) An LLM judge (Claude, in this Cowork session), blind, same guide, one pass. Its output is
    frozen with a SHA-256 before any comparison.
  - Stated limitation: the judge is the same model family that wrote the checker, so it is not
    fully independent. It is not a human.
- **Metrics:**
  - per field, % agreement and Cohen's kappa, checker vs each reader and reader vs reader;
  - for extra claims, report-level presence (kappa) and per-kind agreement;
  - every disagreement listed for adjudication.
  - The checker's own stated values are computed with v1.3 and frozen (in the key) before any
    reader output is seen.
- **Not in this item yet:** CRQS (PathReportEval). It needs their code and an LLM scorer; kept as
  the next step.

### Improvement item 3: first results — checker vs a blind LLM judge, 29 September

**Built** (`stage3/make_checker_sheet.py`):
- `checker_validation/checker_sheet_A.xlsx`, GUIDE.md and reports/;
- `key/key.json` (checker v1.3 readings, frozen), SHA-256
  08c922bd2e820291a65b8722e20fc8bd442ce0312109afbe73aab579d3c0f993.
- 60 reports but only **47 distinct texts**: plain-prompt reports of one model are often
  word-for-word identical (C06/C18/C21/C23/C29 are one Llama text).

**Deviation, fixed before any human reading:** the first sheet had 11 extra-claim columns copied
from the checker's `UNSUPPORTED` table. The checker also flags **tumour site** (detected in a
different place), so a **Site** column was added and the sheet rebuilt. The key was unchanged
(same SHA).

**The judge.** Claude subagent, blind: guide plus report texts only, no tools.
- `llm_judge/judge_claude_raw.json`, SHA-256
  a3fb53e50f4541024619e2ad5b8655add0b75a0edb9c5914408ec65bdfc4d8fd.
- Site was asked afterwards as a separate blind question: `judge_claude_site.json`, SHA-256
  f994f81d17151b4f8b60e58193181482e31222d286bb744f8a734615622f48cc.
- Both frozen before comparison.

**Checker v1.3 vs judge** (`stage3/checker_validation_results.json`):

| | n | Agreement | Kappa |
|---|---|---|---|
| Type | 60 | 1.00 | 1.00 |
| Grade | 60 | 0.98 | 0.96 |
| pT | 60 | 0.77 | 0.66 |
| Node | 60 | 0.82 | 0.75 |
| Node hedged (both say stated) | 20 | 1.00 | — |
| Any extra claim in the report | 60 | 1.00 | 1.00 |

- **By arm**, reports with any disagreement: **predicted 0/15**, extracted 7/15, retrieval 10/15,
  none_free 10/15. The method's own reports are read the same way by both readers.
- **Node (11 reports).**
  - In 7, the judge sees a node claim the checker misses: "Lymph node status is positive" (C48),
    "A positive lymph node status was identified" (C31), "No malignant lymph nodes are
    identified" (C05, C32), "involvement of 14 regional lymph nodes" (C36), "(17/20)" (C30),
    "No metastatic disease in the examined lymph nodes" (C10).
  - In 3, "No lymph nodes are identified": checker "not stated", judge "cannot be assessed". This
    is harmless: neither is a node claim.
  - C49 contradicts itself.
- **pT (14 reports, 5 distinct texts plus singles).**
  - "invade ... into the submucosa, but do not extend beyond the muscularis propria" (one text ×5):
    checker pT2, judge pT1. The text is ambiguous.
  - "involves the serosa and pericolic fat" (×5 near-identical) and "penetration into the serosa":
    checker pT3, judge pT4. Serosal involvement is usually pT4a, so the judge is probably right.
  - Missed by the checker: "penetrates all wall layers" (C17), "through the whole thickness ... and
    the small intestine wall" (C46, adjacent organ, pT4), "limited to the muscularis propria"
    (C55, pT2).
- **Extra claims.** Presence agreed in all 60 reports. The judge sees a few more kinds, never
  fewer: M/distant metastasis 3, Site 2, LVI/margins/node count/pN 1 each.

**What this means (provisional until Labiba's reading).**

- The **unsupported-claims** result (any extra claim: agreement 1.00) and all readings of the
  **predicted arm** hold up.
- The checker under-reads node statements and serosal pT4 in freely written text. So on the
  ungrounded and extracted arms it can:
  - undercount node claims (fewer node overclaims flagged for ungrounded arms, which makes them
    look *better* than they are);
  - lower the extracted arm's faithfulness (node "omitted" when it was stated);
  - misjudge pT correctness.
- These affect secondary numbers, not the grounded-vs-ungrounded headline on invented claims.
  Their size is not yet known.

**Decision: no checker fix now.** Tuning v1.3 on these 60 reports before Labiba reads them would
make her comparison measure a checker fitted to the same reports. Order:
1. her reading;
2. the full three-way comparison, reported for v1.3 as is;
3. then a v1.4 fix with a NEW frozen test (new sentences, not these reports), re-scoring Stage 2,
   and reporting both.

The judge is the same model family that wrote the checker, and it is not a human: stated as a
limitation. CRQS is still to do.

### Decision, 29 September: no new analyses

Labiba decided not to add more work: no Stage 1 changes (**item 5, MSI, dropped**), and **items 6
(HISTAI) and 7 (HistGen/SlideChat baselines) dropped**. Stage 2 has already been run on the current
Stage 1, and redoing Stage 1 would mean redoing Stage 2. The thesis goes ahead with the results
already in hand. Items 1, 2 and 2b stand as done; item 4 was dropped earlier the same day. Item 3
(her reading of the 60 reports) and the gold labels are still open (see the chat of 29 Sep).

### Checker v1.4: node statements and serosal pT4 — test frozen BEFORE the fix, 29 September

Labiba agreed (29 Sep): keep the gold labels and the 60-report reading, and fix the checker now. No
Stage 2 re-run is needed: the checker is only re-run over the existing reports.

**Bias guard.**
- The primary item-3 result stays **checker v1.3 vs the readers**: v1.3's readings were frozen in
  `key.json` before any reader.
- v1.4 is reported beside it as a secondary row.
- The fix is tested only on NEW sentences, never on the 60 reports: `stage3/heldout5_node_serosa.py`
  (12 node + 11 pT sentences, traps included), SHA-256
  ec16bec1f67a02e2c84e1fdd8e5a983a791c5589b9e9b95af93030c05b02cc7b.

**Before the fix, v1.3: 11/23** (`heldout5_results.json`). The misses:
- node statements in the form "lymph node status ... positive", "involvement of ... lymph nodes",
  "no malignant cells ... lymph nodes", "none of the ... lymph nodes";
- pT4 via the serosa or a named adjacent organ;
- pT2 written as "limited/confined to the muscularis propria".

**Fix → checker v1.4** (`consistency.py`):
- four node-negative and two node-positive patterns;
- level-4 depth patterns for the serosa itself (never "subserosa") and named adjacent organs
  (small bowel, bladder, uterus, vagina, prostate, seminal vesicle, ovary, abdominal wall; the liver
  is deliberately excluded, because liver spread is M1, not pT4);
- "limited/confined/restricted to the muscularis propria" as pT2;
- negated clauses ("does not reach the serosa") removed before depth is read.

**After, v1.4: 23/23.** All other tests hold:
- held-out 4: 14/14; held-out 3: 17/18; held-out 1: 66/72 (verdicts identical to v1.3);
- planted-errors results identical; unit tests pass;
- held-out 2 rises 14/15 → **15/15**. **Disclosure:** one "new" heldout5 sentence ("The carcinoma
  directly invades the urinary bladder.") is word-for-word the held-out 2 sentence v1.1 missed, so
  that +1 is not independent evidence.
- Overwritten results files were restored from git; the v1.4 runs are saved as
  `heldout_results_v1.4.json` and `heldout2_results_v1.4.json`.

**Re-scoring Stage 2 with v1.4** (`stage2_scores.json`; v1.3 copy compared line by line):

- **MedGemma 27B (the headline model), template and copy: no change at all**, including every CI.
- **MedGemma 4B.** The predicted arm's pT is now read as 100% faithful: v1.3 had called 11 reports
  contradicted or omitted across TCGA and 7 on CPTAC, all misreadings. Visible balanced correctness
  on predicted test_coad: 0.48 → 0.51.
  - Extracted-arm node faithfulness 0.13 → 0.32. The 4B still leaves node status out in most
    reports.
  - Retrieval node overclaims 0.517 → 0.529.
- **Llama 3.1 8B, extracted arm:** node faithfulness 0.86 → 0.96 (test_coad), 0.91 → 0.98 (READ),
  0.57 → 0.89 (CPTAC). These were missed node statements.
- **Llama 3.1 8B, plain-prompt (none_free) arm: an artefact to flag, not a gain to claim.**
  - Every Llama plain report contains one boilerplate, self-contradictory sentence: "invade ...
    into the submucosa, but do not extend beyond the muscularis propria".
  - v1.3 read it as pT2 (from the negated clause), v1.4 reads "not stated", and the judge reads pT1.
  - The Llama "predicted − none_free" contrasts therefore jump: test_coad +0.19 → +0.27, READ
    +0.14 → +0.22, and **CPTAC +0.01 (not significant) → +0.18**. This comes entirely from reading
    one ambiguous sentence.
  - **Quote the v1.3 values (the conservative ones) for Llama none_free**, with this note. The
    Llama "predicted − none" (strict prompt) contrasts are unchanged.

**Item 3 with v1.4 as an extra reader** (secondary; the primary result stays frozen v1.3 vs readers):

| v1.4 vs judge | Agreement | Kappa |
|---|---|---|
| Type / Grade | 1.00 / 0.98 | 1.00 / 0.96 |
| pT | 0.85 (v1.3: 0.77) | 0.79 (0.66) |
| Node | 0.88 (v1.3: 0.82) | 0.84 (0.75) |
| Any extra claim | 1.00 | 1.00 |

The remaining pT disagreements are mostly the Llama sentence above (×5 in the sample). The v1.4
patterns were motivated by the judge's disagreements but written and tested only on new sentences,
so this row is not an unbiased estimate: Labiba's reading, compared with frozen v1.3, is.

### Chain-of-thought (Phase 10 design, back in scope) — plan fixed BEFORE running, 2 October

Labiba decided (2 Oct) to run the chain-of-thought (CoT) ablation after all; her proposal was
"reasoning-guided". Kept small: grounded arm only, existing Stage 1 predictions, existing checker
(v1.4). Nothing earlier is re-run.

**Design** (`stage2/generate.py`, new arms `cot3`, `cot6`, `cot9`; not part of `--arms all`):
- **Input.** Exactly the `predicted` arm's: Stage 1 calibrated predictions, node withheld, same
  strict prompt (v1). Added to it: reason in exactly N numbered steps, then write the report
  after a line `REPORT:`. The steps follow Phase 10, each with a defined job:
  - **3 steps:** (1) list the findings and confidences; (2) decide each finding's wording (plain if
    at least 60%, "uncertain" if below, the fixed node sentence); (3) write the report.
  - **6 steps:** (1)–(2) as above; (3) how the findings fit together, without adding any; (4) draft;
    (5) check the draft sentence by sentence against the findings and remove anything not listed;
    (6) final report.
  - **9 steps:** (1)–(3) as for 6; (4) other possible histologic types, and why the given one is
    used; (5) neighbouring grade and depth categories, and why the given ones are used; (6) draft;
    (7) check against the findings; (8) check against the rules; (9) final report.
- **Baseline: 0 steps** is the existing `predicted` arm of the same model, on the same cases.
- **Models:** MedGemma 27B (main), Llama 3.1 8B, MedGemma 1.5 4B. TCGA test_coad + holdout_read
  (243 cases). Greedy decoding, repetition penalty 1.1, max_tokens raised to 1500 for CoT arms.
- **Parsing.** The report is the text after the last `REPORT:`. If that line is missing, the
  whole output is scored as the report (conservative) and counted as a format failure.

**Metrics** (`stage3/score_cot.py`), per model and step count, with paired bootstrap differences
against 0 steps (same cases, seed 2026, as in `score_stage2.py`):
1. Final report, **faithfulness**: share of given fields stated correctly, contradicted, omitted;
   reports with any extra claim; node overclaims; node abstention.
2. Final report, **correctness**: visible balanced correctness against the labels.
3. **Hedging**: of given findings below 60% confidence, the share whose sentence carries an
   explicit uncertainty word. Same heuristic as `score_injection.py`, not validated on frozen
   tests, so reported as approximate.
4. **Reasoning trace**: share of traces with an extra claim (checker patterns), and share of traces
   that state a value for a field that differs from the input. Approximate, because a trace can
   *name* a topic it then rules out. Examples are read before any conclusion.
5. Length (tokens), truncation, format failures.

**Expectations stated in advance:**
- Grounded reports without CoT are already near the ceiling on faithfulness (MedGemma 27B: 100%
  faithful, 0% extra claims), so CoT has little room to help the final report.
- The literature (Xu et al. 2025; Wu et al. 2025) predicts that longer reasoning drifts from the
  input. Steps (4)–(5) of the 9-step version explicitly invite alternatives, so the trace measures
  should rise with the number of steps.
- The likely result is "no gain in the final report, more unsupported content in the reasoning".
  That would be reported as the finding. If CoT *improves* hedging or correctness, that is
  reported too.

**Built, 2 Oct.**
- `generate.py`: arms `cot3`/`cot6`/`cot9`; `split_cot()` keeps the raw output, the trace and the
  report. The predicted-arm prompt is unchanged: rebuilt for all 243 cases and compared with the
  saved MedGemma 27B run, 0 differ.
- `score_cot.py`: scorer. `score_stage2.py` now skips `*_cot` runs, so the main table and its
  bootstrap stay identical.
- Server commands: `SERVER_SETUP.md`, "Chain-of-thought run". LLM runs pending.

**Found while testing the scorer, on the EXISTING 0-step reports (approximate hedging measure).**
Of given findings below 60% confidence, the share whose sentence says it is uncertain:
- MedGemma 27B **0.64**;
- Llama 8B **0.16**: it prints "(model confidence 32%)" but rarely says "uncertain", which the
  prompt requires;
- MedGemma 4B **0.00**: it often drops the confidence altogether.

Checked by reading examples. This is a rule-following gap in the grounded reports and goes into the
results as a secondary finding. The 4B 0-step run also has 20 truncated reports (repetition into
long invented margin lists), which the scores already count.

**Correction (2 Oct): truncation.** The Thesis Journey doc said "cut-off reports counted (0 in the
full run)". That was true for MedGemma 27B and is also true for Llama 8B. The MedGemma 4B, run
later, has reports cut off at the 400-token limit after repetition: 20/243 predicted, 23/243
extracted, 35/243 retrieval, 9/47 CPTAC predicted. These are already counted in its scores (the
cut-off text is scored as written).

### Correction, 4 October: the second human annotator has NOT withdrawn

The 28 Sep entry ("The second human annotator withdrew") was wrong, or at least premature.
Labiba confirmed on 4 Oct that he has not dropped out and has said he will help. The design is
therefore back to **two human annotators, with the LLM as a third, independent reader**:

- **Gold labels:** Labiba fills `gold_labels_A.xlsx`; the second annotator fills
  `gold_labels_B.xlsx` (built 24 Sep, identical, same GUIDE.md and PDFs; the multiple-tumour
  companion sheet applies to both). The LLM labels (`llm_annotator/`, frozen 28 Sep) stay as a
  third reading.
- **Checker validation (item 3):** `checker_validation/checker_sheet_B.xlsx`, an identical copy of
  sheet A, made 4 Oct, for the second annotator.
- **Rules for both humans:** blind to each other, to the key and to the LLM outputs; no
  discussing answers until both sheets are done.
- **What this restores:** human–human agreement (Cohen's kappa), plus human–LLM and checker–human.
  The 28 Sep Limitations wording ("one human cross-checked by an LLM") applies only if he does not
  finish.
- `score_checker_validation.py` reads sheet B too once filled (to be added when it arrives).

---

# Where things stand

| Stage | State |
|---|---|
| Data assembled and verified | **done** |
| Labels extracted and audited | **done** — and validated against GDC clinical data, 24 Sep (Phase 12): pT 98.0%, node 97.5%, mucinous 93.3% |
| Stage 1 — predict findings from images | **done, rerun on corrected labels 24 Sep** (Phase 12); **external test on CPTAC-COAD 26 Sep: mucinous AUROC 0.78 transfers, thresholds/pT/node do not** — mucinous above chance on both cohorts (0.719 / 0.739); node status near chance; control at chance. These numbers supersede Phase 9 |
| Stage 2 — generate report text: **grounded vs. ungrounded** | **core run done 26 Sep** (MedGemma 27B, 5 arms, template + copy baselines, TCGA + CPTAC): grounded 0.55 / 0.50 balanced correctness vs 0.36 chance, 0% vs 100% reports with invented claims. Secondary LLMs (Llama 3.1 8B, MedGemma 4B), readability metrics, HistGen, LoRA: to do |
| Stage 3 — **consistency metric + its validation — protected, never cut** | checker built and validated: planted errors, held-out set 1 (90.3%), held-out set 2 depth-in-words (14/15, v1.1), held-out 3 (17/18, v1.2), held-out 4 confidence % (14/14, v1.3), held-out 5 node/serosa (23/23, v1.4; 27B scores unchanged), GDC; scoring script done. **29 Sep: 60-report sheet built; blind LLM judge agrees on type/grade/extra claims, not on node and pT in free text. Still to do: Labiba's reading of the 60 reports** and gold labels, CRQS; error injection dropped 29 Sep · CoT ablation back in scope 2 Oct (code ready, server run pending) |

### Roadmap against the December deadline

Submission: **December 2026** — **confirmed by the supervisor, 24 Sep** (planned date
20 December; moved from 30 Nov, Phase 10). GPU server details received from the supervisor
the same day.

| Weeks | Dates | Planned | Status |
|---|---|---|---|
| 1–2 | 7–20 Sep | Stage 1 trained, audited, closed | **done** |
| 3–4 | 21 Sep – 4 Oct | GDC clinical data downloaded and matched; gold labels (~50 cases); consistency checker built, with visibility tags, and tested on the *real* reports; Stage 1 predictions + retrieval neighbours exported (Mac); A6GC sensitivity check; GPU server and Hugging Face access requested | next |
| 5–7 | 5–25 Oct | Stage 2 core: template + one LLM × {none, retrieval, predicted, extracted} (GPU server). Planted-error test set built in parallel | |
| 8 | 26 Oct – 1 Nov | LoRA. Second annotator labels the ~60 generated reports | |
| 9–10 | 2–15 Nov | **Stage 3: metric validation** (planted errors, GDC agreement, κ); calibration; heatmaps for visible fields. Secondary Stage 2 (CoT, second LLM) only in spare GPU time | |
| 11–13 | 13 Nov – 3 Dec | Results and Discussion; **full draft to supervisor by 3 Dec** | |
| 14 | 4–20 Dec | Revisions, formatting, submit | |

Writing Methods runs alongside all of this — not left to November.

**Immediately next, in order:**

0. ~~**Rerun Stage 1 and its matched control on the fixed labels.**~~ **Done, 24 Sep**
   (Phase 12), and the TCGA-NH-A6GC sensitivity check — no effect beyond one
   correct case in a class of six. Original command, on the
   Mac, stdin detached (Phase 9):
   `nohup caffeinate -is python3 -u train_stage1.py --seeds 5 < /dev/null > run_main.log 2>&1 &`
   then `--shuffle_labels --match_config results_stage1.json` the same way. Also
   the TCGA-NH-A6GC sensitivity check. Everything in Stage 2 waits on the new
   checkpoint.
1. ~~**Download GDC clinical data.**~~ **Done, 24 Sep** — and it found two label bugs.
2. **Find the second annotator** (supervisor or a fellow student) and write the
   annotation rubric.
3. **Gold labels** — the set is **built** (24 Sep): `gold_labels/`, made by
   `stage1/make_gold_sheet.py`. 50 reports = 30 drawn at random from all 590 (for
   unbiased accuracy) + 20 enriched for rare or hard cases (6 mucinous, 5 G1, 4 pT1,
   5 where the extractor found no type or node status), shuffled together as G01–G50
   so no annotator can tell which is which. Two identical sheets (A = you, B = the second
   annotator), drop-down answers, a labelling guide (`GUIDE.md`, also the first tab), and
   each report as a text file. Labelled blind to the extractor and to GDC.
   `stage1/score_gold.py` then gives agreement (Cohen's kappa) per field, writes an
   adjudication sheet for the disagreements, and after adjudication scores the extractor
   and GDC against the result — including grade, which GDC does not carry.
   **Still to do: the labelling itself (~2–3 hours each).**
4. ~~**Consistency checker.**~~ **First version done, 24 Sep** (Phase 12): planted errors,
   real-report swaps, frozen held-out set at 90.3%. Known gaps listed there.
5. ~~**Export Stage 1 predictions.**~~ **Done, 25 Sep** (Phase 12): `stage2/inputs/`.
6. **External test + published baseline (Phase 13):** find out how the UNI2-h features were
   extracted (tool, magnification, patch size); download CPTAC-COAD (66.7 GB) to the server,
   keep tumour slides, extract UNI2-h features the same way; fetch CPTAC clinical labels from
   GDC. Set up HistGen on the server with the existing features.
7. **Server + model access** — GPU model and memory, disk quota, SLURM, whether
   compute nodes reach Hugging Face; request gated Llama 3.1 / MedGemma access now. Also
   request **UNI2-h** access (gated) — needed for the CPTAC-COAD features.
8. ~~Back up `stage1_mil.pt` off the laptop.~~ **Done, 26 Sep** (Google Drive).
9. Still open from Phase 8: stratify the split, or document plainly that it is
   random at case level, with class distributions per split.

**If the schedule slips — Stage 3 is protected.**

**Never cut:** the ungrounded baseline · the consistency metric · its validation
(planted errors, GDC agreement, double annotation) · the rectal holdout · the
gold-label audit · **the CPTAC-COAD external test** (decided 26 Sep, Phase 13). These are what make the work publishable; without them the
central claim is asserted, not measured.

**Cut in this order instead:**
1. Chain-of-thought 3 / 6 / 9-step ablation
2. Second and third LLMs (MedGemma, Llama / Qwen — keep one)
3. LoRA (the prompted LLM + template still give a complete comparison)
4. Learning curve
5. Heatmap polish (keep a few illustrative ones)

The minimum publishable core is: **template + one LLM, grounded vs. ungrounded →
consistency metric → its validation.** Everything else is optional.

### Deliberately not done

- **Adding breast or gynaecological cancers.** The method is organ-agnostic and the
  report text already exists in the corpus, but there is not enough time before the
  December deadline. → Future Work.
- **Endometriosis / PCOS.** PCOS is not diagnosed from tissue at all (ultrasound and
  bloods), so this pipeline does not apply. Endometriosis is diagnosed from tissue, but
  no public whole-slide dataset exists — it would need hospital data and ethics
  approval, which takes longer than a semester. → Future Work.

---

# Things to remember when writing up

- **Always report balanced accuracy against chance**, and say what chance is.
- **Always report the rectal holdout separately.** The gap is the finding.
- **Say "weak labels"** and cite the GDC agreement (pT 98.0%, node 97.5%, mucinous
  93.3%, held-out columns included). Never imply the labels are ground truth, and do
  **not** cite the old 95.2% cross-check — Phase 12 shows it missed a 30% error.
- **Name the excluded fields and why.** Margin status and lymphovascular invasion were
  dropped on evidence — that is a strength, not an omission.
- **The before/after overfitting comparison is worth its own short section.**
- **Every number here is reproducible** from the scripts in this repository.
- **Stage 2 is a comparison, not a system description.** Lead with grounded vs.
  ungrounded on per-field correctness and unsupported claims; fluency metrics second.
- **Stage 3's consistency metric and its validation are the paper's evidence** —
  never present Stage 2 results without them. No expert reader study: say so in
  Limitations rather than hoping nobody asks.
- **Node status is inferred from the primary tumour, not seen.** 599 of 600 slides
  are primary-tumour samples. Never write "detects nodal metastasis".

### Gold-label sheets rebuilt (v2), 4 October

**Why:** Labiba found report G22 describes two tumours with different pT and grade, and the old
layout had no clear place for them (a separate multiple-tumours file) or for "cannot find it".
**What changed:** `gold_labels/make_gold_sheets_v2.py` builds `gold_labels_A.xlsx` and
`gold_labels_B.xlsx` (same 50 reports). One sheet; T1 (index tumour) and T2 (other tumour)
columns; whole-case columns for nodes, LVI, margins, treatment. New rule: every cell filled;
"not stated" = report silent, "unreadable in the scan" = cannot read; only node counts, mucinous %
and T2 may be empty. Links now open the PDF. New guide: `GUIDE.md`.
**Her 22 filled rows were kept:** copied into the T1 columns of sheet A (old unreadable option renamed).
Old sheets moved to `gold_labels/_old_sheets/` (not deleted). The separate multiple-tumours file
was retired (it was empty). Blank cells in sheet A mean "not yet done".
**Known follow-up:** `stage1/score_gold.py` reads the OLD column layout and must be updated before
the gold labels are scored (not run yet). Option renamed "form: answer unreadable" -> "unreadable in the scan".

---

### Proposal: add CAMELYON17 as a lymph-node module — 15 October

**Why.** 599 of 600 TCGA slides are primary tumour, so node status is inferred, not seen
(Derek Magee's point; Stage 1 node results near chance on CPTAC). Supervisor suggested finding
a dataset that contains lymph nodes. CAMELYON17 (CC0; AWS Open Data bucket `camelyon-dataset`)
has H&E lymph-node slides with patient pN stage for 100 training patients (5 nodes each).

**What it is for — and not for.** It tests whether the same UNI2-h + gated-attention MIL can
detect tumour in node tissue. It is breast cancer, different patients: it cannot supply pN for
TCGA reports, and it does not help rare colorectal classes (that would need more colorectal
data, e.g. SurGen).

**Obstacles found before downloading.**
- No pre-extracted features: MahmoodLab/UNI2-h-features holds only CPTAC, PANDA, TCGA. All
  features so far were downloaded ready-made; this would be the first own extraction
  (must match TCGA: TRIDENT, 256 px at 20×).
- Size: Academic Torrents lists CAMELYON17 at **2.48 TB** (train + test); per-patient zips
  2–20 GB. Too big for the shared server in one go → plan is batches: download → extract →
  delete raw slides, keeping only features.
- Scope was frozen on 26 Sep (draft 3 Dec, submission 20 Dec). Adding this is a deliberate
  scope change, within the 3–3.5 weeks the supervisor allowed.

**Step 0 (no download):** `camelyon/00_check_size.sh` lists the bucket and real training size;
`camelyon/01_get_labels.sh` fetches only `stage_labels.csv` (< 1 MB). Nothing downloaded yet.

**Decision (same day): CAMELYON17 dropped.** Too large (≈2.5 TB raw), first-ever own
feature extraction, uncertain payoff, and scope was frozen on 26 Sep. Node status stays a
stated limitation (primary-tumour slides do not show nodes). Effort goes instead to making
the existing results more trustworthy: human gold labels (A + B annotators), checker
validation, and a small clinician review. `camelyon/` scripts kept for reference, never run.

### Change of deliverable — 15 October

The thesis has been converted into a project: no thesis draft is required (the 3 Dec draft /
20 Dec submission dates no longer apply). The deliverable is **one focused paper**. Working
claim: fluent generated pathology reports can contradict the slide-level findings, and a
validated consistency checker catches this; grounded vs. ungrounded generation compared.
Candidate venues: MIUA 2027 (Warwick; call not yet out) or MIDL 2027 (Porto, 14–16 July;
deadlines not yet out). Check both calls when published.
