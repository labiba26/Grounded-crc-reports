"""test_per_class.py - checks on the per-class reporting added after the Phase 8 audit.

Why this file exists. Balanced accuracy averages per-class recall, so every class
counts the same however few patients stand behind it. The COAD test split holds
exactly one pT1 case, which therefore controls a quarter of the pt_stage figure:
getting that single patient right or wrong swings the headline number by 0.25,
whatever the model has actually learnt. The audit called for reporting per-class
recall with its support so this is visible instead of buried.

These checks pin down the reporting maths:

  * per-class recall is averaged across seeds and keeps the support beside it
  * a class below MIN_CLASS_N is flagged rather than silently averaged in
  * the thin-class-excluded figure uses only the surviving classes, and its
    chance baseline is 1 / (number of classes kept), not 1 / (all classes)
  * the headline balanced accuracy is untouched by any of the above, so the
    numbers stay comparable with Phase 7

Runs in about a second. torch is stubbed; numpy is real, since the maths under
test is numpy.

    python3 test_per_class.py
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent

TASKS = {
    "mucinous": [False, True],
    "grade": [1, 2, 3],
    "pt_stage": [1, 2, 3, 4],
    "node_positive": [False, True],
}


def _stub(name, **attrs):
    m = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(m, k, v)
    sys.modules[name] = m
    return m


def _install_stubs():
    """Stub only what is heavy. numpy stays real - it is what we are testing."""
    t = _stub("torch", __version__="STUB", save=lambda *a, **k: None,
              no_grad=lambda: (lambda f: f), device=str,
              cuda=types.SimpleNamespace(is_available=lambda: False))
    t.nn = _stub("torch.nn", Module=object)
    _stub("torch.utils")
    _stub("torch.utils.data", DataLoader=object)
    _stub("models", GatedAttentionMIL=object)
    _stub("wsi_dataset", BASE=HERE.parent, IGNORE=-100, TASKS=TASKS,
          CaseBagDataset=object, collate=None, derive_targets=None, encode=None)


_install_stubs()
sys.path.insert(0, str(HERE))
import train_stage1 as T  # noqa: E402

FAILURES: list[str] = []


def check(label, got, want):
    ok = got == want
    print(f"  {'PASS' if ok else 'FAIL'}  {label}: {got}")
    if not ok:
        FAILURES.append(f"{label}: got {got!r}, wanted {want!r}")


def close(label, got, want, tol=1e-9):
    ok = got is not None and abs(got - want) < tol
    print(f"  {'PASS' if ok else 'FAIL'}  {label}: {got}")
    if not ok:
        FAILURES.append(f"{label}: got {got!r}, wanted ~{want!r}")


def seed_result(pt_recalls, pt_supports=(1, 14, 41, 16), bal=0.325):
    """One seed's evaluate() output for pt_stage, shaped like the real thing."""
    return {
        "pt_stage": {
            "n": sum(pt_supports),
            "acc": 0.5,
            "bal_acc": bal,
            "majority": 0.569,
            "per_class": [
                {"class": c, "n": n, "recall": r}
                for c, n, r in zip([1, 2, 3, 4], pt_supports, pt_recalls)
            ],
            # classes with support >= 5 only: pT2, pT3, pT4
            "bal_acc_min5": sum(pt_recalls[1:]) / 3,
            "n_classes_min5": 3,
        }
    }


CHANCE = {"pt_stage": 0.25}


def test_per_class_is_averaged_with_support():
    print("\n[1] per-class recall is averaged over seeds, support kept beside it")
    per_seed = [seed_result((1.0, 0.2, 0.8, 0.1)),
                seed_result((0.0, 0.4, 0.6, 0.3))]
    rows = T.report("TEST", per_seed, CHANCE)
    pc = {c["class"]: c for c in rows["pt_stage"]["per_class"]}
    close("pT1 mean recall (1.0 and 0.0)", pc[1]["recall_mean"], 0.5)
    close("pT2 mean recall (0.2 and 0.4)", pc[2]["recall_mean"], 0.3)
    check("pT1 support survives", pc[1]["n"], 1)
    check("pT3 support survives", pc[3]["n"], 41)
    close("pT1 spread is reported", pc[1]["recall_sd"], 0.5)


def test_thin_classes_are_flagged():
    print("\n[2] a class below MIN_CLASS_N is flagged, not silently averaged")
    per_seed = [seed_result((1.0, 0.2, 0.8, 0.1))]
    rows = T.report("TEST", per_seed, CHANCE)
    pc = {c["class"]: c for c in rows["pt_stage"]["per_class"]}
    check("MIN_CLASS_N", T.MIN_CLASS_N, 5)
    check("pT1 (n=1) flagged thin", pc[1]["thin"], True)
    check("pT2 (n=14) not flagged", pc[2]["thin"], False)
    check("pT4 (n=16) not flagged", pc[4]["thin"], False)


def test_excluded_view_and_its_baseline():
    print("\n[3] the thin-class-excluded figure keeps its own chance baseline")
    per_seed = [seed_result((1.0, 0.3, 0.6, 0.3)),
                seed_result((0.0, 0.3, 0.6, 0.3))]
    rows = T.report("TEST", per_seed, CHANCE)[ "pt_stage"]
    check("classes kept", rows["n_classes_min5"], 3)
    close("excluded-view mean = mean(0.3,0.6,0.3)", rows["bal_acc_min5_mean"], 0.4)
    close("chance is 1/3, not 1/4", rows["chance_min5"], 1 / 3)
    close("chance for the headline figure is still 1/4", rows["chance"], 0.25)


def test_headline_number_is_unchanged():
    print("\n[4] none of this moves the headline balanced accuracy")
    per_seed = [seed_result((1.0, 0.2, 0.8, 0.1), bal=0.755),
                seed_result((0.0, 0.4, 0.6, 0.3), bal=0.745)]
    rows = T.report("TEST", per_seed, CHANCE)["pt_stage"]
    close("mean of the two seeds' bal_acc", rows["bal_acc_mean"], 0.75)
    check("n is the split size", rows["n"], 72)


def test_absent_class_does_not_crash():
    print("\n[5] a class with no cases at all is reported, not crashed on")
    per_seed = [{
        "pt_stage": {
            "n": 71, "acc": 0.5, "bal_acc": 0.33, "majority": 0.57,
            "per_class": [
                {"class": 1, "n": 0, "recall": None},
                {"class": 2, "n": 14, "recall": 0.2},
                {"class": 3, "n": 41, "recall": 0.8},
                {"class": 4, "n": 16, "recall": 0.1},
            ],
            "bal_acc_min5": 0.36666666666666664, "n_classes_min5": 3,
        }
    }]
    rows = T.report("TEST", per_seed, CHANCE)["pt_stage"]
    pc = {c["class"]: c for c in rows["per_class"]}
    check("absent class has no recall", pc[1]["recall_mean"], None)
    check("absent class counts as thin", pc[1]["thin"], True)
    close("present classes still averaged", pc[3]["recall_mean"], 0.8)


def main():
    for t in (test_per_class_is_averaged_with_support,
              test_thin_classes_are_flagged,
              test_excluded_view_and_its_baseline,
              test_headline_number_is_unchanged,
              test_absent_class_does_not_crash):
        t()
    print()
    if FAILURES:
        print("FAILED:\n  " + "\n  ".join(FAILURES))
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
