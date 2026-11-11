# Grounded, Not Just Fluent: Verifiable Report Generation from Colorectal Cancer Whole-Slide Images

*Formerly "Reasoning-Guided Pathology Report Generation". TCGA COAD/READ, external test on CPTAC-COAD.*

> **Note:** `THESIS_LOG.md` is the full, dated record of every decision, mistake and result. Where this README and the log differ, the log is correct.

Master's project: generating colorectal cancer pathology reports from
whole-slide images, in a way that makes each generated claim checkable rather than
merely fluent.

The pipeline predicts **structured clinical findings** from slide features first, then
writes the narrative report from those findings. That separation is the point: a claim in
the generated report can be traced back to a predicted field, a confidence score, and the
tissue region that produced it.

---

## Status

| Stage | State |
|---|---|
| Dataset assembled and split | **done** |
| Report text recovered and paired | **done** — 592 / 594 (99.7%) |
| Structured findings extracted + audited | **done** — validated against GDC clinical data (pT 98.0%, node 97.5%, mucinous 93.3% agreement) |
| Stage 1: findings prediction model | **done** — rerun 24 Sep on GDC-validated labels, 5 seeds + matched control (`THESIS_LOG.md`, Phase 12). Mucinous 0.719 colon / 0.739 rectal; node status near chance, as expected from primary-tumour slides. External test on CPTAC-COAD (26 Sep): mucinous AUROC 0.78, threshold does not transfer |
| Stage 2: report generation — grounded vs. ungrounded comparison | **core run done 26 Sep** on the GPU server (`stage2/generate.py`, MedGemma 27B; `SERVER_SETUP.md`). Grounded reports: every given finding stated, no invented claims; 0.55 / 0.50 balanced correctness vs 0.36 chance. Secondary models and readability metrics next |
| Stage 3: consistency metric + its validation (**protected**) | checker built and validated (planted errors; held-out 90.3%; depth-in-words held-out 14/15); `stage3/score_stage2.py` scores every run. Double annotation of generated reports still to do |

---

## Dataset

Built from TCGA COAD + READ. Slide features are **UNI2-h patch embeddings**, pre-extracted
and used frozen — no feature extraction is repeated in this work.

| | |
|---|---|
| Cases (features **and** report text) | **590** (434 COAD, 156 READ) |
| Slides | 599 |
| Patches per slide | 328 – 31,521 (mean 6,360) |
| Feature array | `(1, N, 1536)` float32, plus level-0 patch coordinates at 512 px spacing |
| Report length | median 1,115 chars (~280 tokens), max 12,801 |

**Splits are case-level**, so no patient appears on both sides of a split. All 156 READ
cases are held out entirely as an unseen-cohort generalisation test.

| Split | Cases |
|---|---|
| `train_coad` | 347 |
| `test_coad` | 87 |
| `holdout_read` | 156 (never trained on) |

One case (TCGA-G5-6572) is excluded: its only document is a *TCGA Missing Pathology
Report Form*, a placeholder stating no report was available.

### Report text

GDC ships pathology reports as PDFs; the metadata only gives file names. Text was
recovered by exact report-UUID match against the published TCGA-Reports corpus
(Kefeli et al., *Patterns*, 2024) rather than by OCR-ing the PDFs locally.

---

## Structured findings (weak labels)

Findings are extracted from report text by pattern matching (`stage1/extract_fields.py`).
These are **weak labels**, not ground truth: the source text is OCR'd, multi-institutional,
and partly Latin/Polish. Every field may be absent, and absent is not the same as negative —
the training loss masks missing fields rather than treating them as a class.

| Field | Coverage | Distribution | Used |
|---|---|---|---|
| `histologic_type` | 94.2% | adeno 512 · mucinous 43 · signet-ring 1 (WHO definition, >50%) | yes |
| `tumour_site` | 92.9% | colon NOS 107 · sigmoid 99 · cecum 94 · rectosigmoid 86 … | yes |
| `histologic_grade` | 88.6% | G2 391 · G3 110 · G1 22 | yes |
| `pt_stage` | 84.1% | pT3 329 · pT2 98 · pT4 54 · pT1 15 | yes |
| `lymph_node_positive` | 88.1% | positive 227 · negative 293 | yes |
| `pn_stage` | 70.5% | pN0 209 · pN1 115 · pN2 91 · pN3 1 | cross-check only |
| `lymphovascular_invasion` | 50.2% | present 242 · absent 54 | **excluded** |
| `margins_involved` | 75.3% | clear 442 · involved 2 | **excluded** |

### Recovering the 51 unmatched reports

The published corpus covered 543 of the 594 GDC reports. All 51 remaining PDFs turned
out to carry a **text layer**, so `pdftotext` extracts them directly — cleaner than the
Textract OCR behind the other 543, and no OCR was needed. Two were *TCGA Missing
Pathology Report Forms* (placeholders stating no report was available) and were
discarded; the other 49 are genuine reports, adding **47 cases (543 → 590)**.

**These recovered documents exposed a labelling trap.** Many are printed forms rather
than prose:

```
Signet Ring Feature :  ( ) No   ( ) Yes   ( ) Yes (Focal)   ( ) Unknown
6. Mucinous Adenocarcinoma   7. Signet ring cell type Adenocarcinoma
```

The pathologist's answer is a *mark on paper*. The text layer carries the question and
every option but not the mark, so a naive pattern reads a printed option as a positive
finding. Before the guard, signet-ring carcinoma jumped from 7 to 35 cases — 6% of the
cohort against roughly 1% in reality, i.e. 28 false positives. `extract_fields.py` now
detects option runs (`Yes`/`No` following a field label) and printed menus (a document
naming four or more mutually exclusive tumour types), and returns `None` for those
fields rather than guessing. Signet-ring fell back to 6 cases (1.0%), matching the
published incidence. (Later tightened to the WHO definition — signet-ring *cell
carcinoma*, not signet-ring features — which leaves 1 case; see Label quality.) Grade survives the guard because "Grade: Moderately Differentiated"
states its value after the label.

### Label quality

- **Validated against GDC clinical data** (`stage1/compare_gdc.py`). GDC's pathologic T,
  N and morphology were abstracted from the same reports by trained curators,
  independently of the extractor:

  | Field | n | Agreement | κ | test split | rectal holdout |
  |---|---|---|---|---|---|
  | pT stage | 494 | 98.0% | 0.96 | 94.4% | 97.6% |
  | node status | 514 | 97.5% | 0.95 | 94.8% | 97.8% |
  | mucinous | 550 | 93.3% | 0.63 | 91.2% | 94.6% |

  Rules were fixed only from training-split disagreements, so the last two columns are
  held out. GDC has no grade for these cases. **This comparison found two bugs** the
  internal cross-check below had missed: negative node phrasing ("lymph nodes negative
  for metastatic tumour") read as positive in 96 cases, and "mucinous" anywhere —
  including a 15% component — counted as mucinous adenocarcinoma. Both are fixed and
  pinned by `stage1/test_extract_fields.py` (`THESIS_LOG.md`, Phase 12).
- **Nodal cross-check: 98.3% agreement** (`stage1/qc_labels.py`) between `pn_stage` and
  `lymph_node_positive`. It covers only reports that state both, which is why it missed
  the error above.
- 84% of cases carry at least 5 of 8 fields.
- **Two fields were excluded on evidence.** Hand-auditing showed the first margin extractor
  produced false positives — OCR drops sentence boundaries, so an unrelated clause
  ("…5 cm from the surgical margin there is a circular, ulcerated tumour… infiltrated")
  satisfied a "margin…infiltrated" pattern. Tightening the rule collapsed it to 432 clear
  vs 1 involved, i.e. recall far too low, so margin status is not reliably extractable from
  this corpus by pattern matching. `lymphovascular_invasion` is excluded for the mirror
  reason: 80% positive is well above the 30–50% reported for colorectal cancer.

**Open task:** hand-label ~50 cases as a gold subset and report extractor precision against it.

---

## Stage 1 — findings prediction

Gated-attention multiple-instance learning (Ilse et al., 2018) over frozen UNI2-h features.

- **The bag is the case, not the slide.** A case may have several slides but one report, so
  patches from all its slides are pooled into a single bag.
- **Attention rather than mean pooling.** A tumour can occupy a small fraction of a
  6,000-patch slide; averaging drowns it in normal mucosa and fat. The attention weights,
  mapped through the stored patch coordinates, also serve as the explanation heatmap.
- **Four heads on a shared trunk:** `mucinous`, `grade`, `pt_stage`, `node_positive`.
  Sharing one representation is far more sample-efficient than four separate models on
  347 training cases. (`sidedness` was dropped — see `THESIS_LOG.md`, Phase 6: it is
  unanswerable across these cohorts, since READ is ~88% "rectal" by definition.)
- **Masked, class-balanced loss.** Fields a report does not state contribute no loss.
  Class weights are inverse-frequency, and balanced accuracy is the headline metric,
  compared against **chance** (1 ÷ number of classes), *not* the majority-class rate —
  see `THESIS_LOG.md`, Phase 6. The majority rate is reported alongside for reference
  only; pT3 alone is 329 of 496 labelled cases.

---

## Stage 2 — report generation (planned)

Writes the narrative report from Stage 1's predicted findings, not from raw slide
features, so every generated claim has a specific, checkable prediction behind it.

**The main experiment is a comparison: grounded versus ungrounded generation.** The
generator is held fixed and only its input changes:

| Input | Role |
|---|---|
| Nothing (same prompt, findings removed) | Ungrounded baseline — what the LLM invents from its priors |
| Retrieved report of the nearest training case (UNI2-h embedding) | Ungrounded, image-conditioned baseline |
| **Stage 1 predicted findings** | The method |
| Findings extracted from the real report | Upper bound — separates generator error from Stage 1 error |

Generators: a deterministic **template** (the floor), **one prompted LLM**, and
**LoRA** fine-tuning of that LLM. Primary metrics are per-field correctness and the
rate of **unsupported claims** (anything stated that the generator was not given);
BLEU/ROUGE are secondary.

**Secondary experiments, on the grounded arm only:** a second LLM (MedGemma-4B), and
chain-of-thought prompting with 3 / 6 / 9 reasoning steps. The literature suggests
structured reasoning can reduce hallucination in medical report generation, but also
that longer chains can pull attention away from the evidence, with an inverted-U
between reasoning length and accuracy (`THESIS_LOG.md`, Phase 10). These are the first
things cut if time runs short.

### What the slides can and cannot show

599 of the 600 slides are TCGA primary-tumour samples (sample type 01); one is a
metastasis sample (TCGA-NH-A6GC). Lymph nodes are examined on other slides that TCGA
does not provide, so **`node_positive` is inferred from the primary tumour's
morphology, not detected** — the model almost never sees nodal tissue. pT stage is
partly affected (the deepest point of invasion may not be on the slide); histologic
type and grade are directly visible. Each field therefore carries a visibility tag —
*visible*, *partly visible*, *not visible* — which Stage 2 wording and the Stage 3
metric both respect (`THESIS_LOG.md`, Phase 12).

## Stage 3 — validation (planned, protected)

The consistency metric checks each claim in a generated report against the findings:
is it correct, is it stated at all, is anything stated without support, and is
anything stated as *observed* that the slide cannot show. There is no pathologist
reader study, so the metric is validated three ways:

1. **Planted errors** — known mistakes (wrong values, omissions, unsupported
   additions, negations) inserted into reports, alongside meaning-preserving
   rewordings; detection and false-alarm rates are reported per error type.
2. **GDC clinical data** — curator-abstracted pT, N and histologic type as an
   independent reference for the extractor and for scoring generated reports.
3. **Double annotation** — two annotators, a written rubric, Cohen's κ.

**This is not cut under any schedule** — it is what turns the traceability claim from
assertion into evidence. The claim is that grounding reduces incorrect and unsupported
statements, not that the reports are clinically acceptable; an expert reader study is
future work. Calibration and attention heatmaps (for visible fields only) complete
Stage 3.

---

## Layout

```
build_metadata.py              case ↔ slide ↔ report metadata join
map_tcga_cases.py              GDC case mapping
get_tcga_reports.py            GDC pathology-report file metadata
download_tcga_reports.py       report PDF retrieval
extract_report_text.py         report PDFs → text via TCGA-Reports corpus (UUID match)
build_multimodal_dataset.py    case-level pairing, validation, train/test/holdout splits

dataset_manifests_final/       dataset_index.json + the three split manifests
metadata.csv                   flat slide-level index

stage1/
  extract_fields.py            report text → structured findings (weak labels)
  qc_labels.py                 label quality cross-check
  wsi_dataset.py               case-level MIL dataset over the H5 features
  models.py                    gated-attention MIL
  train_stage1.py              masked multi-task training + evaluation
  structured_labels.json       extracted findings for all 590 cases
```

## Reproducing

Requires TCGA COAD/READ UNI2-h features and GDC pathology reports (not redistributed here —
see *Data availability*).

```bash
pip install torch h5py scikit-learn

python3 build_metadata.py
python3 extract_report_text.py \
    --report_metadata pathology_report_metadata.json \
    --tcga_reports_csv TCGA_Reports.csv \
    --out_dir ./report_text
python3 build_multimodal_dataset.py \
    --h5_dir UNI2_h_features/TCGA \
    --reports_dir tcga_report_text/reports_txt \
    --out_dir dataset_manifests_final

cd stage1
python3 extract_fields.py --sample 15   # weak labels + hand-audit sample
python3 qc_labels.py                    # label quality check

python3 train_stage1.py --seeds 5       # the real run
python3 train_stage1.py --shuffle_labels --match_config results_stage1.json
```

### Run outputs

Output filenames are derived from the run, so no run can overwrite another's
results or weights:

| Run | Command | Writes |
|---|---|---|
| real | `train_stage1.py --seeds 5` | `results_stage1.json`, `stage1_mil.pt` |
| shuffled control | `--shuffle_labels --match_config results_stage1.json` | `results_shuffled.json`, `stage1_mil_shuffled.pt` |
| plumbing check | `--smoke` | `results_smoke.json`, `stage1_mil_smoke.pt` |
| anything else | `--run_tag NAME` | `results_NAME.json`, `stage1_mil_NAME.pt` |

A run with `--shuffle_labels` cannot write the real run's filenames at all. Passing
`--match_config` copies the reference run's training settings, so the control differs
from the run it controls in one thing only: whether the labels correspond to the
images. Each results file records the time, host and git commit that produced it.

## Data availability

This repository contains code, dataset manifests and derived labels only. It does **not**
contain UNI2-h feature files (~42 GB), pathology report PDFs, or extracted report text.
TCGA data is obtained from the GDC Data Portal; report text comes from the TCGA-Reports
corpus.

## Citation

> Kefeli J, Tatonetti N. TCGA-Reports: A machine-readable pathology report resource for
> benchmarking text-based AI models. *Patterns*, 2024.

> Ilse M, Tomczak JM, Welling M. Attention-based Deep Multiple Instance Learning. *ICML*, 2018.

> Wei J, et al. Chain-of-Thought Prompting Elicits Reasoning in Large Language Models. *NeurIPS*, 2022. (arXiv:2201.11903)

> Chain-of-Medical-Thought (CoMT): Reduces Hallucination in Medical Report Generation. 2024. (arXiv:2406.11451)

