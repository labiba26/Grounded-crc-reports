# Running on a GPU server

Stage 1 (below) needs the features. **Stage 2 does not** — see
[Stage 2](#stage-2--report-generation) at the end.

# Stage 1

## What actually needs to travel

Stage-1 training reads **only** the H5 features, the dataset manifests and the
pre-computed labels. It does **not** need the report text, the PDFs or the
TCGA-Reports corpus — those were only used to *produce* `structured_labels.json`,
which is already computed and is 190 KB.

| Send | Size | Why |
|---|---|---|
| `UNI2_h_features/TCGA/TCGA-COAD/` + `TCGA-READ/` | 18 GB + 4.7 GB | the 600 feature files |
| `dataset_manifests_final/*.json` | ~0.5 MB | which cases, which slides, which split |
| `stage1/*.py` + `structured_labels.json` | ~0.2 MB | code and training targets |
| `requirements.txt`, `run_train.slurm` | tiny | environment and job script |

**Do not send:** `reports/` (PDFs), `tcga_report_text/`, `TCGA_Reports.csv`,
`report_text/`, `*.tar.gz`, `.venv/`. None are used by training.

The manifests store **relative** paths (`UNI2_h_features/TCGA/...`), so as long as
you keep the same folder layout under one parent directory, nothing needs editing.

## 1. Copy it over

From your Mac's Terminal. `rsync` resumes if the connection drops, which matters
for a 23 GB transfer — do not use `scp` for this.

```bash
# adjust user@server and the destination path
rsync -avhP --partial \
  --include='UNI2_h_features/' --include='UNI2_h_features/TCGA/' \
  --include='UNI2_h_features/TCGA/TCGA-COAD/***' \
  --include='UNI2_h_features/TCGA/TCGA-READ/***' \
  --include='dataset_manifests_final/***' \
  --include='stage1/***' \
  --include='requirements.txt' --include='run_train.slurm' \
  --exclude='*' \
  ~/TCGA_thesis/ user@server:~/tcga_thesis/
```

Faster alternative: if the feature archives are still downloadable from wherever
you originally got them, `wget` them **directly on the server** and extract there.
Pulling 21 GB over the university network beats pushing it from a laptop.

Check it arrived intact:

```bash
ssh user@server 'ls ~/tcga_thesis/UNI2_h_features/TCGA/TCGA-COAD/*.h5 | wc -l'   # expect 442
ssh user@server 'ls ~/tcga_thesis/UNI2_h_features/TCGA/TCGA-READ/*.h5 | wc -l'   # expect 158
```

## 2. Set up the environment

```bash
ssh user@server
cd ~/tcga_thesis

module avail python          # see what your cluster provides
module load python/3.11 cuda # names vary between clusters

python3 -m venv ~/tcga-env
source ~/tcga-env/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

python3 -c "import torch; print(torch.__version__, 'CUDA:', torch.cuda.is_available())"
```

That last line must print `CUDA: True`. If it prints `False` you are on a login
node without a GPU — that is normal; it will be `True` inside the job.

## 3. Smoke test before the real run

Never queue a long job without checking the plumbing first. On an interactive GPU
session (`srun --gres=gpu:1 --pty bash`) or the login node:

```bash
cd ~/tcga_thesis/stage1
python3 train_stage1.py --smoke
```

This runs 6 cases for 1 epoch. If it completes, paths and data are correct.

## 4. Submit the real run

```bash
cd ~/tcga_thesis/stage1
cp ../run_train.slurm .
# edit --partition and --account first (see the comments in the file)
sbatch run_train.slurm
squeue -u $USER          # watch the queue
tail -f logs/stage1_*.out
```

No SLURM on your cluster? Run it directly instead:

```bash
python3 train_stage1.py --epochs 30 --max_patches 2048 --batch_size 8 --num_workers 8
```

## 5. What you get

- `results_stage1.json` — accuracy and **balanced accuracy** per field, on COAD test
  and on the READ holdout separately, each next to the majority-class baseline
- `stage1_mil.pt` — trained weights

Read balanced accuracy, not accuracy, and always compare it to the majority column.
pT3 is 329 of 496 labelled cases, so a model that predicts pT3 every time scores
about 0.66 accuracy while having learned nothing — balanced accuracy would sit near
0.25 and expose that immediately.

## Tuning notes

- `--num_workers 8` matters. Each case reads its features from disk, so with
  single-threaded loading the GPU sits idle waiting for data.
- `--max_patches 2048` is a sampled view of each slide, re-drawn every epoch, which
  acts as free augmentation. Raise it if GPU memory allows; the largest slide has
  31,521 patches (~190 MB at full size), which is why sampling exists.
- If you hit out-of-memory, lower `--batch_size` before lowering `--max_patches`.
- 347 training cases is small, so results will vary between runs. Run 3–5 seeds
  (`--seed`) and report mean ± spread rather than a single number.

---

# Stage 2 — report generation

Design: `THESIS_LOG.md`, Phase 11. Stage 2 is **text only** — it reads Stage 1's
predictions and the report text, never the slide features — so the 23 GB transfer
above is not needed.

## 0. The server (checked 26 Sep 2026)

**2 × NVIDIA RTX PRO 5000 Blackwell, 48 GB each (96 GB total)**, driver 595.84, CUDA 13.2.
Ubuntu, Python 3.12.3, 64 CPU cores, 125 GB RAM, 1.5 TB free on `/` (home is on the same
disk, shared by everyone — keep model caches tidy). **No SLURM** (`which sbatch` empty): jobs run
directly, so use `tmux` to keep them alive after logging out. `curl` is not installed (use
`wget` or Python). Shared by ~11 people:
check `nvidia-smi` before starting a job and use one GPU unless the run needs both.

What fits:
- Llama 3.1-8B / MedGemma 1.5-4B in bf16 — one GPU, with room to spare.
- **MedGemma 27B in bf16 (~55 GB) needs both GPUs** (vLLM `--tensor-parallel-size 2`), or one
  GPU in FP8 (~28 GB; Blackwell supports FP8). Prefer bf16 on two GPUs for the main runs
  when both are free; record which was used.
- LoRA on an 8B model fits on one GPU without quantisation.
- Blackwell needs a recent PyTorch built for CUDA 12.8 or newer (sm_120). Older wheels
  install fine and then fail with "no kernel image is available" — check with
  `python3 -c "import torch; print(torch.cuda.get_device_capability())"` → `(12, 0)` and a tiny matmul.
- The server clock read **31 Aug** on 26 Sep. Provenance timestamps from it are wrong; the git
  commit in each results file is the reliable record. Mention to the admin.

**Environment (set up 26 Sep):** `python3-venv` is missing and there is no admin access, so the
environment uses **uv**. GitHub downloads return 403 from this network; uv was installed from its
PyPI wheel into `~/.local/bin` (on PATH via `~/.bashrc`). Environment: `~/tcga-env`
(`uv venv ~/tcga-env --python 3.12`), then `uv pip install vllm huggingface_hub`.
Result: **vLLM 0.30.0, PyTorch 2.13.0+cu130, transformers 5.17.0**; both GPUs visible,
compute capability (12, 0), GPU matmul OK. Every login: `source ~/tcga-env/bin/activate`.

**Two GPUs (tensor parallel):** NCCL hangs at start-up unless run with `NCCL_P2P_DISABLE=1`
(the GPUs cannot talk directly on this workstation); `generate.py` also turns off vLLM's custom
all-reduce when `--tp > 1`. Triton needs Python headers: `libpython3.12-dev` unpacked into
`~/pydev` (`apt download` + `dpkg -x`), found via `C_INCLUDE_PATH` set in `~/tcga-env/bin/activate`.

    NCCL_P2P_DISABLE=1 CUDA_VISIBLE_DEVICES=0,1 python stage2/generate.py \
        --model google/medgemma-27b-text-it --tp 2          # add --limit 5 for a smoke test

Was still to check (answered above):

- GPU model and memory. A 7–8B model needs ~16 GB for bf16 inference; LoRA fits in
  24 GB with 4-bit quantisation (QLoRA), comfortably in 40–80 GB without it.
- Disk quota — each model is ~15 GB, plus a cache.
- SLURM or direct access; the partition and account names.
- Whether **compute nodes** can reach huggingface.co. If not, download models on the
  login node into a shared cache first.

Gated model access (26 Sep): **MedGemma 27B text and MedGemma 1.5 4B granted**;
**Llama 3.1-8B-Instruct granted** (26 Sep). Qwen2.5-7B-Instruct is ungated.

## 1. Produce the inputs on the Mac — done

Stage 1 inference runs on the Mac. The inputs Stage 2 uses:

- **`stage2/inputs/predictions_cv_calibrated.json`** — the main input: out-of-fold
  predictions for all 434 colon cases and the 5-fold ensemble for the 151 rectal cases,
  temperature-calibrated (Phase 12). Use the `temperature` block, not the raw values.
- **`stage2/inputs/predictions_cptac.json`** — the CPTAC-COAD external cohort (47 + 110
  patients), same recipe. No reference reports exist for CPTAC; score against the
  cBioPortal labels stored in each record.

- `stage2/inputs/predictions.json` — the seed-44 fixed-split model; kept for comparison
  only (its training-set predictions are overfit, so it is not a Stage 2 input)
- **`stage2/inputs/retrieval.json`** — still used (the retrieval arm) — per test/holdout case: nearest *training* case by
  mean-pooled UNI2-h embedding (never a case from the same split)

## 2. What travels

| Send | Size | Why |
|---|---|---|
| `stage2/` (code + `inputs/`) | < 5 MB | generation, evaluation, predictions, neighbours |
| `stage1/structured_labels.json` | 0.2 MB | extracted findings — the upper-bound arm and the scoring reference |
| `stage1/extract_fields.py` | tiny | the consistency checker's first version |
| `dataset_manifests_final/*.json` | ~0.5 MB | splits |
| `tcga_report_text/reports_txt/` | a few MB | **needed now** — LoRA targets and reference reports (Stage 1 did not need it) |

**Still do not send:** `UNI2_h_features/`, `reports/` (PDFs), `TCGA_Reports.csv`, `*.pt`.

```bash
rsync -avhP \
  --include='stage2/***' \
  --include='stage1/' --include='stage1/structured_labels.json' --include='stage1/extract_fields.py' \
  --include='dataset_manifests_final/***' \
  --include='tcga_report_text/' --include='tcga_report_text/reports_txt/***' \
  --exclude='*' \
  ~/TCGA_thesis/ user@server:~/tcga_thesis/
```

The report text is TCGA open-access data, but it is patient pathology text: keep it
in your own home directory on the server, not a shared scratch space.

## 3. Order of runs

1. **Smoke test** — 5 cases, one input arm, one model: checks model loading, prompts
   and output parsing.
2. **Core matrix** — template + one LLM × {none, retrieval, predicted, extracted},
   on `test_coad` and `holdout_read`. Batch generation (e.g. vLLM) makes this hours,
   not days. Greedy decoding, fixed seed, prompts saved alongside the outputs.
3. **LoRA** — trained on `train_coad` with the *extracted* findings as input (not
   Stage 1's training-set predictions, which are overfit), evaluated on predictions.
4. **Secondary, only if on schedule** — chain-of-thought 3 / 6 / 9 steps; a second LLM.

Every output file records model name and revision, prompt version, decoding
settings, input arm, host and git state — the same provenance rule as Stage 1.

**Stage 3 depends on this finishing:** the core matrix must be done by the end of
October so the second annotator can label its outputs. If Stage 2 runs late, cut from
step 4 upward — never the ungrounded arm, which the whole comparison rests on.

**Node status: reports abstain.** Every arm states that nodal status cannot be assessed
from the submitted tissue. Decided 26 Sep: the slides are primary tumour only (Phase 12),
and on CPTAC the node prediction fell to chance (AUROC 0.45) with the worst calibration
(ECE 0.29) — `THESIS_LOG.md`, CPTAC results. The extracted-findings upper-bound arm may
still state node status, since it comes from the report, not the slide.

## Error-injection run (improvement item 4, added 29 Sep)

**Dropped on 29 Sep: not to be run.** Kept here only as a record (see THESIS_LOG.md).

One wrong finding is put into the extracted findings of each of the 243 TCGA test cases, and each
LLM writes a report from it (arms `injected` and `injected_low`; plan in `THESIS_LOG.md`). About
490 reports per model, far smaller than the core run.

On the Mac, from the thesis folder:

    sh stage2/make_bundle.sh
    scp stage2_bundle.tar.gz labiba@172.25.0.189:~/tcga_thesis/

On the server:

    cd ~/tcga_thesis && tar xzf stage2_bundle.tar.gz
    source ~/tcga-env/bin/activate
    NCCL_P2P_DISABLE=1 CUDA_VISIBLE_DEVICES=0,1 python stage2/generate.py \
        --model google/medgemma-27b-text-it --tp 2 --arms injected injected_low --tag injection > inj_27b.log 2>&1
    CUDA_VISIBLE_DEVICES=0 python stage2/generate.py \
        --model meta-llama/Llama-3.1-8B-Instruct --arms injected injected_low --tag injection > inj_llama.log 2>&1
    CUDA_VISIBLE_DEVICES=0 python stage2/generate.py \
        --model google/medgemma-1.5-4b-it --arms injected injected_low --tag injection > inj_4b.log 2>&1

Back on the Mac (copies only the three new folders):

    scp -r 'labiba@172.25.0.189:~/tcga_thesis/stage2/outputs/*_injection' stage2/outputs/
    python3 stage3/score_injection.py

## Chain-of-thought run (Phase 10 ablation, added 2 Oct)

Grounded reports written after 3, 6 or 9 reasoning steps (arms `cot3`, `cot6`, `cot9`; plan in
`THESIS_LOG.md`, 2 Oct). 243 TCGA test cases × 3 arms per model; output length up to 1500 tokens
is set automatically.

On the Mac, from the thesis folder (commit first, so the run records a clean commit):

    sh stage2/make_bundle.sh
    scp stage2_bundle.tar.gz labiba@172.25.0.189:~/tcga_thesis/

On the server:

    cd ~/tcga_thesis && tar xzf stage2_bundle.tar.gz
    source ~/tcga-env/bin/activate
    NCCL_P2P_DISABLE=1 CUDA_VISIBLE_DEVICES=0,1 python stage2/generate.py \
        --model google/medgemma-27b-text-it --tp 2 --arms cot3 cot6 cot9 --tag cot > cot_27b.log 2>&1
    CUDA_VISIBLE_DEVICES=0 python stage2/generate.py \
        --model meta-llama/Llama-3.1-8B-Instruct --arms cot3 cot6 cot9 --tag cot > cot_llama.log 2>&1
    CUDA_VISIBLE_DEVICES=0 python stage2/generate.py \
        --model google/medgemma-1.5-4b-it --arms cot3 cot6 cot9 --tag cot > cot_4b.log 2>&1

Optional first: add `--limit 5` to the 27B command for a 5-case smoke test (folder ends in `_smoke`).

Back on the Mac (copies only the three new folders):

    scp -r 'labiba@172.25.0.189:~/tcga_thesis/stage2/outputs/*_cot' stage2/outputs/
    python3 stage3/score_cot.py
