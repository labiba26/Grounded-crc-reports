"""generate.py - Stage 2: write pathology reports from findings, one input arm at a time.

THESIS_LOG.md Phase 11: the generator is held fixed and only its INPUT changes.

  arm         what the generator is given                          role
  none        the same strict prompt, no findings                  ungrounded (instruction-following)
  none_free   a plain "write a report" prompt, no rules            ungrounded (what the LLM invents)
  retrieval   the report of the nearest TRAINING case (UNI2-h)     image-conditioned, ungrounded
  predicted   Stage 1's calibrated predictions (node: abstain)     THE METHOD
  extracted   the weak labels from the real report                 upper bound

Generators: an LLM through vLLM (any local Hugging Face model), the deterministic
template (predicted / extracted only), and `copy` (retrieval: the neighbour's report
verbatim - the classic retrieval baseline). Greedy decoding, fixed seed; the exact
prompt, model revision, sampling settings and git state are saved with every run.

Node status: the slides are primary tumour only and Stage 1's node prediction is at
chance externally, so the predicted arm never receives node status and the prompt asks
for a fixed abstention sentence instead (findings.NODE_ABSTAIN_TEXT). The extracted arm
keeps node status - it came from the real report.

Stage 3 is protected: every output file is scored by stage3/consistency.py (--score).

    python3 stage2/generate.py --generator template --arms predicted extracted
    python3 stage2/generate.py --model google/medgemma-1.5-4b-it --arms all --limit 5   # smoke
    CUDA_VISIBLE_DEVICES=0,1 python3 stage2/generate.py --model google/medgemma-27b-text-it --tp 2 --arms all
"""
from __future__ import annotations

import argparse
import datetime
import json
import socket
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(BASE / "stage3"))
import findings as F            # noqa: E402
import template_report as TR    # noqa: E402

PROMPT_VERSION = "v1"
ALL_ARMS = ["none", "none_free", "retrieval", "predicted", "extracted"]
# improvement item 4 (THESIS_LOG 29 Sep): error injection. Not part of --arms all.
INJECT_ARMS = ["injected", "injected_low"]
INJECT_ORDER = ("grade", "pt_stage", "histologic_type")
WRONG = {"grade": {1: 2, 2: 3, 3: 2}, "pt_stage": {1: 2, 2: 3, 3: 4, 4: 3},
         "histologic_type": {"adenocarcinoma": "mucinous", "mucinous": "adenocarcinoma"}}
INJECT_PROB = 0.40            # below HEDGE_BELOW: the prompt requires "uncertain"

# Phase 10 chain-of-thought ablation (plan: THESIS_LOG.md, 2 Oct). Same input as `predicted`;
# the model reasons in exactly N numbered steps, then writes the report after "REPORT:".
# Not part of --arms all.
COT_ARMS = ["cot3", "cot6", "cot9"]
COT_MAX_TOKENS = 1500
_S_LIST = "List each finding given above with its model confidence."
_S_WORD = ("Decide how to word each finding: state it plainly if its confidence is {hedge}% or more, "
           "state it and say it is uncertain if below {hedge}%, and use the required sentence for lymph node status.")
_S_FIT = "Consider how the findings fit together (for example grade and depth of invasion), without adding any new finding."
_S_TYPE = "Consider which other histologic type this tumour could be, and why the given finding is used."
_S_NEIGH = "Consider what the neighbouring grade and depth-of-invasion categories would look like, and why the given findings are used."
_S_DRAFT = "Write a draft of the report."
_S_CHECKF = "Check the draft sentence by sentence against the findings list and remove anything that is not in the list."
_S_CHECKR = "Check the draft against the rules above: uncertainty wording, the lymph node sentence, and no extra topics."
_S_FINAL = "Write the final report after a line that says REPORT:"
COT_STEPS = {
    "cot3": [_S_LIST, _S_WORD, _S_FINAL],
    "cot6": [_S_LIST, _S_WORD, _S_FIT, _S_DRAFT, _S_CHECKF, _S_FINAL],
    "cot9": [_S_LIST, _S_WORD, _S_FIT, _S_TYPE, _S_NEIGH, _S_DRAFT, _S_CHECKF, _S_CHECKR, _S_FINAL],
}
COT_SUFFIX = """

Before writing, reason in exactly {n} numbered steps:
{steps}

Answer in this format:
REASONING:
Step 1: ...
...
Step {n}: ...
REPORT:
<the report text only>"""


def split_cot(text):
    """(reasoning, report, ok): the report is the text after the LAST 'REPORT:' line marker.
    Missing marker -> the whole output is scored as the report (conservative) and ok=False."""
    import re
    ms = list(re.finditer(r"(?im)^\W*report\W*:\W*", text))
    if not ms:
        return text, text, False
    m = ms[-1]
    return text[:m.start()].strip(), text[m.end():].strip(), True
HEDGE_BELOW = 0.60            # confidence under which the report must say "uncertain"
MAX_REF_CHARS = 6000

SYSTEM = ("You write the diagnosis section of surgical pathology reports for colorectal "
          "cancer resections. You are precise and never add information you were not given.")

STRICT = """Write the diagnosis section of a pathology report (3 to 6 sentences, plain prose) for this colorectal carcinoma resection.

Rules:
1. Use only the information given below. Do not mention anything else: no margins, lymphovascular or perineural invasion, tumour size or site, lymph node counts, pN or M category, stage group, microsatellite or mismatch-repair status, tumour budding, or treatment.
2. If a finding has a model confidence below {hedge}%, state it and say that it is uncertain.
3. Lymph node status: if it is listed under FINDINGS, state it. If it is not listed, write exactly this sentence: "{abstain}"
4. If a finding is not listed, do not guess it.

FINDINGS:
{findings}
{reference}
Write only the report text."""

FREE = ("Write the diagnosis section of a pathology report (3 to 6 sentences, plain prose) "
        "for a colorectal carcinoma resection specimen. Write only the report text.")

REFERENCE = """
REFERENCE - the report of a DIFFERENT patient whose slide looks similar. It is not this patient's report and may not apply:
---
{text}
---
"""


# ------------------------------------------------------------------ inputs
def git_state():
    def run(*c):
        return subprocess.run(["git", *c], cwd=BASE, capture_output=True, text=True).stdout
    try:   # never strip porcelain output: its first column may be a space
        files = [l[3:] for l in run("status", "--porcelain").splitlines() if l.strip()]
        head = run("rev-parse", "--short", "HEAD").strip()
        if head:
            return {"git_commit": head, "git_dirty_code": any(f.endswith(".py") for f in files),
                    "git_dirty_files": files}
    except Exception:
        pass
    info = HERE / "BUNDLE_INFO.json"          # on the server there is no git repo: the bundle
    if info.exists():                          # records the commit it was packed from
        return json.loads(info.read_text())
    return {"git_commit": None}


def load_cases(cohort, splits, limit):
    """[(case_id, split, predicted_fs, extracted_fs)] - both FindingSets in findings.py form."""
    out = []
    if cohort == "tcga":
        P = json.loads((HERE / "inputs" / "predictions_cv_calibrated.json").read_text())["cases"]
        L = json.loads((BASE / "stage1" / "structured_labels.json").read_text())
        by = defaultdict(list)
        for cid, rec in sorted(P.items()):
            if rec["split"] in splits:
                by[rec["split"]].append(cid)
        for sp in splits:
            for cid in by[sp][:limit or None]:
                rec = P[cid]
                pred = {k: {"value": rec[k]["temperature"]["value"], "prob": rec[k]["temperature"]["prob"]}
                        for k in ("mucinous", "grade", "pt_stage", "node_positive")}
                out.append((cid, sp, F.from_predictions(pred), F.from_labels(L[cid]["labels"])))
    else:                                                  # cptac: primary selection only
        P = json.loads((HERE / "inputs" / "predictions_cptac.json").read_text())["cases"]
        keys = sorted(k for k in P if k.endswith("|tumour_slides"))[:limit or None]
        for k in keys:
            rec = P[k]
            pred = {t: {"value": rec[t]["value"], "prob": rec[t]["prob"]}
                    for t in ("mucinous", "grade", "pt_stage", "node_positive")}
            lab = rec["labels"]
            ext = {"source": "extracted", "findings": {
                "histologic_type": None if lab["mucinous"] is None else
                {"value": "mucinous" if lab["mucinous"] else "adenocarcinoma", "prob": None},
                "grade": None,                                     # not in CPTAC
                "pt_stage": None if lab["pt_stage"] is None else {"value": lab["pt_stage"], "prob": None},
                "node_status": None if lab["node_positive"] is None else {"value": lab["node_positive"], "prob": None}}}
            out.append((k.split("|")[0], "cptac_tumour_slides", F.from_predictions(pred), ext))
    return out


def local_model_path(repo):
    """The downloaded snapshot folder. snapshot_download(local_files_only=True) refuses a
    snapshot when files were deliberately skipped (Llama's duplicate "original/" weights,
    26 Sep), so read the cache directly: refs/main -> snapshots/<revision>."""
    from huggingface_hub.constants import HF_HUB_CACHE
    d = Path(HF_HUB_CACHE) / ("models--" + repo.replace("/", "--"))
    path = d / "snapshots" / (d / "refs" / "main").read_text().strip()
    missing = [f for f in ("config.json", "tokenizer_config.json") if not (path / f).exists()]
    if missing or not (list(path.glob("*.safetensors")) or list(path.glob("*.bin"))):
        sys.exit(f"{repo}: local snapshot {path} is incomplete (missing {missing or 'weights'}) - download it again")
    return str(path)


def retrieval_text(cid, R):
    rec = R.get(cid)
    if not rec:
        return None, None
    txt = " ".join((BASE / p).read_text(errors="replace") for p in rec["neighbour_report"])
    return rec["neighbour"], txt[:MAX_REF_CHARS]


def inject(cid, ext_fs, low):
    """Extracted findings with exactly ONE field changed to a neighbouring wrong value.
    Field: fixed hash of the case ID picks a start in INJECT_ORDER; fields the case lacks are skipped."""
    import copy
    import hashlib
    fs = copy.deepcopy(ext_fs)
    start = int(hashlib.md5(cid.encode()).hexdigest(), 16) % len(INJECT_ORDER)
    for i in range(len(INJECT_ORDER)):
        field = INJECT_ORDER[(start + i) % len(INJECT_ORDER)]
        cur = fs["findings"].get(field)
        if cur is not None and cur["value"] in WRONG[field]:
            wrong = WRONG[field][cur["value"]]
            fs["findings"][field] = {"value": wrong, "prob": INJECT_PROB if low else None}
            fs["source"] = "injected_low" if low else "injected"
            fs["injection"] = {"field": field, "original": cur["value"], "injected": wrong}
            return fs
    return None                                           # nothing to inject: case skipped


def arm_input(arm, pred_fs, ext_fs, cid=None):
    """The FindingSet the generator is given in this arm (None = no findings)."""
    if arm in INJECT_ARMS:
        return inject(cid, ext_fs, arm == "injected_low")
    if arm == "predicted" or arm in COT_ARMS:
        return F.abstain_node(pred_fs)
    if arm == "extracted":
        return ext_fs
    return F.empty()


def findings_block(fs):
    f = fs["findings"]
    lines = []
    t, g, pt, n = (f.get(k) for k in ("histologic_type", "grade", "pt_stage", "node_status"))
    conf = lambda x: "" if x.get("prob") is None else f" (model confidence {x['prob']:.0%})"
    if t: lines.append(f"- Histologic type: {TR.TYPE_WORDS[t['value']]}{conf(t)}")
    if g: lines.append(f"- Histologic grade: G{g['value']}, {TR.GRADE_WORDS[g['value']]}{conf(g)}")
    if pt: lines.append(f"- Depth of invasion: pT{pt['value']}, {TR.T_WORDS[pt['value']]}{conf(pt)}")
    if n: lines.append(f"- Lymph node status: {'positive' if n['value'] else 'negative'}{conf(n)}")
    return "\n".join(lines) or "None provided."


def build_messages(arm, fs, ref_text):
    if arm == "none_free":
        user = FREE
    else:
        user = STRICT.format(hedge=int(HEDGE_BELOW * 100), abstain=F.NODE_ABSTAIN_TEXT,
                             findings=findings_block(fs),
                             reference=REFERENCE.format(text=ref_text) if ref_text else "")
        if arm in COT_ARMS:
            steps = [s.format(hedge=int(HEDGE_BELOW * 100)) for s in COT_STEPS[arm]]
            user = user.replace("\nWrite only the report text.", "") + COT_SUFFIX.format(
                n=len(steps), steps="\n".join(f"{i}. {s}" for i, s in enumerate(steps, 1)))
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]


# ------------------------------------------------------------------ scoring (Stage 3)
def score_rows(rows):
    import consistency as C
    agg = defaultdict(Counter)
    for r in rows:
        a = agg[r["arm"]]
        a["n"] += 1
        chk = C.check(r["output"], r["input_findings"])
        ref = C.against_reference(r["output"], r["reference_findings"])
        r["check"], r["reference_check"] = chk["summary"], ref["fields"]
        for k, v in chk["summary"].items():
            a[k] += v
        # an unhedged node statement is an overclaim only when the input did NOT supply node
        # status (the extracted arm gets it from the real report, so stating it is correct)
        if r["input_findings"]["findings"].get("node_status") is not None:
            a["overclaims"] -= chk["summary"]["overclaims"]
        a["truncated"] += r.get("finish_reason") == "length"
        for f, v in ref["fields"].items():
            a[f"ref_{v}"] += 1
        a["reports_with_unsupported_claim"] += chk["summary"]["unsupported_claims"] > 0
        a["node_abstained"] += any("lymph node status cannot be assessed" in s.lower() for s in chk["abstentions"])
    return agg


def print_scores(agg):
    cols = ["n", "correct", "contradicted", "omitted", "unsupported", "unsupported_claims",
            "reports_with_unsupported_claim", "overclaims", "node_abstained", "truncated",
            "ref_correct", "ref_incorrect", "ref_not stated"]
    print("\n" + "arm".ljust(11) + "".join(c.replace("reports_with_unsupported_claim", "rep_w_unsup")[:12].rjust(13) for c in cols))
    for arm, a in agg.items():
        print(arm.ljust(11) + "".join(str(a.get(c, 0)).rjust(13) for c in cols))
    print("fields: correct/contradicted/omitted/unsupported vs the INPUT (faithfulness); "
          "ref_* vs the extracted labels (correctness).")


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--generator", default="llm", choices=["llm", "template", "copy"])
    ap.add_argument("--model", help="Hugging Face repo id (llm generator)")
    ap.add_argument("--tp", type=int, default=1, help="GPUs for tensor parallelism")
    ap.add_argument("--arms", nargs="+", default=["all"])
    ap.add_argument("--cohort", default="tcga", choices=["tcga", "cptac"])
    ap.add_argument("--splits", nargs="+", default=["test_coad", "holdout_read"])
    ap.add_argument("--limit", type=int, default=0, help="cases per split (0 = all)")
    ap.add_argument("--max_tokens", type=int, default=400)
    ap.add_argument("--repetition_penalty", type=float, default=1.1,
                    help="greedy decoding loops on small models; 1.0 = off")
    ap.add_argument("--tag", default="", help="extra label for the output folder")
    ap.add_argument("--eager", action="store_true", help="skip CUDA graphs / compilation (debugging)")
    ap.add_argument("--quantization", default=None, help="e.g. fp8 - fits the 27B model on ONE GPU")
    a = ap.parse_args()
    arms = ALL_ARMS if a.arms == ["all"] else a.arms
    if a.generator == "template":
        arms = [x for x in arms if x in ("predicted", "extracted", *INJECT_ARMS)]
    if a.generator == "copy":
        arms = ["retrieval"]
    if a.cohort == "cptac":
        arms = [x for x in arms if x != "retrieval"]   # no CPTAC reports to retrieve

    cases = load_cases(a.cohort, a.splits, a.limit)
    R = json.loads((HERE / "inputs" / "retrieval.json").read_text())["cases"]
    gen_name = a.model.split("/")[-1] if a.generator == "llm" else a.generator
    run = f"{gen_name}_{a.cohort}" + (f"_{a.tag}" if a.tag else "") + ("_smoke" if a.limit else "")
    if a.generator == "llm" and a.quantization:
        run += f"_{a.quantization}"
    if a.generator == "llm" and a.repetition_penalty != 1.1:
        run += f"_rp{a.repetition_penalty:g}"
    outdir = HERE / "outputs" / run
    outdir.mkdir(parents=True, exist_ok=True)
    print(f"{len(cases)} cases x {len(arms)} arms -> {outdir.relative_to(BASE)}", flush=True)

    jobs = []                     # (row, messages)
    for cid, sp, pred_fs, ext_fs in cases:
        for arm in arms:
            fs = arm_input(arm, pred_fs, ext_fs, cid)
            if arm in INJECT_ARMS and fs is None:
                continue
            nb, ref = retrieval_text(cid, R) if arm == "retrieval" else (None, None)
            if arm == "retrieval" and ref is None:
                continue
            row = {"case_id": cid, "split": sp, "arm": arm, "generator": gen_name,
                   "input_findings": fs, "reference_findings": ext_fs, "neighbour": nb}
            if a.generator == "template":
                row["output"] = TR.render(fs, style=0)
            elif a.generator == "copy":
                row["output"] = ref
            else:
                row["messages"] = build_messages(arm, fs, ref)
            jobs.append(row)

    meta = {"prompt_version": PROMPT_VERSION, "generator": a.generator, "arms": arms,
            "cohort": a.cohort, "splits": a.splits, "limit": a.limit, "n_rows": len(jobs),
            "hedge_below": HEDGE_BELOW, "node_policy": "predicted arm abstains",
            "cot": {"steps": {k: v for k, v in COT_STEPS.items() if k in arms}, "suffix": COT_SUFFIX,
                    "max_tokens": COT_MAX_TOKENS} if set(arms) & set(COT_ARMS) else None,
            "injection": {"order": INJECT_ORDER, "wrong": {k: {str(a): b for a, b in v.items()} for k, v in WRONG.items()},
                          "low_prob": INJECT_PROB} if set(arms) & set(INJECT_ARMS) else None,
            "prediction_input": "predictions_cv_calibrated.json, temperature" if a.cohort == "tcga"
                                else "predictions_cptac.json, tumour_slides",
            "host": socket.gethostname(),
            "started_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
            **git_state()}

    if a.generator == "llm":
        from vllm import LLM, SamplingParams
        path = local_model_path(a.model)
        # no try/except fallback here: a failed first attempt keeps GPU memory and hides the real error
        # two GPUs on this workstation cannot talk directly (NCCL hung at start-up on 26 Sep),
        # so with --tp 2 run NCCL_P2P_DISABLE=1 and skip vLLM's custom all-reduce (needs P2P)
        llm = LLM(model=path, tensor_parallel_size=a.tp, max_model_len=8192,
                  gpu_memory_utilization=0.85, seed=0, enforce_eager=a.eager,
                  disable_custom_all_reduce=a.tp > 1, quantization=a.quantization)
        if set(arms) & set(COT_ARMS):
            a.max_tokens = max(a.max_tokens, COT_MAX_TOKENS)
        sp_ = SamplingParams(temperature=0.0, max_tokens=a.max_tokens, seed=0,
                             repetition_penalty=a.repetition_penalty)
        res = llm.chat([j["messages"] for j in jobs], sp_, use_tqdm=True)
        for j, r in zip(jobs, res):
            o = r.outputs[0]
            j["output"], j["finish_reason"], j["n_tokens"] = o.text.strip(), o.finish_reason, len(o.token_ids)
            if j["arm"] in COT_ARMS:          # score only the report; keep the full text and the trace
                j["raw_output"] = j["output"]
                j["reasoning"], j["output"], j["cot_format_ok"] = split_cot(j["raw_output"])
        import vllm, torch
        import os
        meta.update({"model": a.model, "model_revision": Path(path).name, "tp": a.tp,
                     "quantization": a.quantization, "nccl_p2p_disable": os.environ.get("NCCL_P2P_DISABLE"),
                     "sampling": {"temperature": 0.0, "max_tokens": a.max_tokens, "seed": 0,
                                  "repetition_penalty": a.repetition_penalty},
                     "system_prompt": SYSTEM, "strict_prompt": STRICT, "free_prompt": FREE,
                     "vllm": vllm.__version__, "torch": torch.__version__})

    agg = score_rows(jobs)
    meta["finished_at"] = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    meta["scores"] = {k: dict(v) for k, v in agg.items()}
    (outdir / "meta.json").write_text(json.dumps(meta, indent=1))
    for arm in arms:
        with open(outdir / f"{arm}.jsonl", "w") as fh:
            for j in jobs:
                if j["arm"] == arm:
                    fh.write(json.dumps(j) + "\n")
    print_scores(agg)
    if a.limit:
        print("\n--- examples (first case, each arm) ---")
        first = jobs[0]["case_id"] if jobs else None
        for j in jobs:
            if j["case_id"] == first:
                print(f"\n[{j['arm']}] {j['output']}")
    print(f"\nwrote {outdir.relative_to(BASE)}/  (meta.json + one .jsonl per arm)")


if __name__ == "__main__":
    main()
