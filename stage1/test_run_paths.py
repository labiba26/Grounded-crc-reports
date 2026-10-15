"""test_run_paths.py - checks on the run-naming logic in train_stage1.py.

Why this file exists. results_stage1.json and stage1_mil.pt once held the
shuffled-label control rather than the real five-seed run: train_stage1.py wrote
to fixed paths whatever the run was, so whichever run finished last owned the
filenames. Nothing crashed - the contents of a file just quietly became something
else. These checks pin down the fix so it cannot regress:

  * a control and a real run never write the same file
  * --shuffle_labels cannot write the real run's filenames at all
  * --match_config leaves the control differing from its reference in exactly one
    setting, the shuffling
  * a missing or malformed --match_config file is an error, not a silent skip
  * provenance flags uncommitted code, so a commit hash cannot silently point
    at code other than what actually ran (the Phase 9 reruns did exactly that)

Runs in about a second and needs no torch, no GPU and no feature files: the heavy
imports are stubbed, since none of this logic touches them.

    python3 test_run_paths.py
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent


# --- stub the heavy imports so train_stage1 can be imported bare --------------
def _stub(name, **attrs):
    m = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(m, k, v)
    sys.modules[name] = m
    return m


def _install_stubs():
    t = _stub("torch", __version__="STUB", save=lambda *a, **k: None,
              no_grad=lambda: (lambda f: f), device=str,
              cuda=types.SimpleNamespace(is_available=lambda: False))
    t.nn = _stub("torch.nn", Module=object)
    _stub("torch.utils")
    _stub("torch.utils.data", DataLoader=object)
    _stub("numpy", mean=lambda x: 0, std=lambda x: 0, ndarray=object)
    _stub("models", GatedAttentionMIL=object)
    _stub("wsi_dataset", BASE=HERE.parent, IGNORE=-100, TASKS={},
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


def args(**kw):
    return argparse.Namespace(**{"run_tag": None, "smoke": False,
                                 "shuffle_labels": False, **kw})


REAL_CONFIG = {"seeds": 5, "epochs": 60, "patience": 8, "val_frac": 0.15,
               "max_patches": 2048, "batch_size": 8, "lr": 2e-4, "dropout": 0.4,
               "weight_decay": 1e-2, "hidden": 512, "num_workers": 4, "verbose": False,
               "shuffle_labels": False, "smoke": False}

# the control as it was actually run, before the fix
CONTROL_AS_RUN = dict(REAL_CONFIG, seeds=1, epochs=8, patience=3,
                      max_patches=512, shuffle_labels=True)


def test_tags():
    print("\n[1] each kind of run gets its own name")
    check("normal run", T.resolve_run_tag(args()), "main")
    check("--shuffle_labels", T.resolve_run_tag(args(shuffle_labels=True)), "shuffled")
    check("--smoke", T.resolve_run_tag(args(smoke=True)), "smoke")
    check("--run_tag wins", T.resolve_run_tag(args(run_tag="lr3e4")), "lr3e4")


def test_paths():
    print("\n[2] the real run keeps the canonical filenames")
    main = {k: v.name for k, v in T.run_paths("main").items()}
    check("results", main["results"], "results_stage1.json")
    check("partial", main["partial"], "results_partial.json")
    check("model", main["model"], "stage1_mil.pt")

    print("\n[3] every other run writes elsewhere")
    ctrl = {k: v.name for k, v in T.run_paths("shuffled").items()}
    check("results", ctrl["results"], "results_shuffled.json")
    check("partial", ctrl["partial"], "results_partial_shuffled.json")
    check("model", ctrl["model"], "stage1_mil_shuffled.pt")

    tags = ["main", "shuffled", "smoke", "lr3e4"]
    every = [p.name for tag in tags for p in T.run_paths(tag).values()]
    check("no two runs share a filename", len(set(every)), 3 * len(tags))


def test_control_cannot_take_the_main_paths():
    print("\n[4] a control cannot write the real run's files, even if told to")

    class Reached(Exception):
        """raised in place of training, to see whether the guard let us through"""

    original, T.split_ids = T.split_ids, lambda *_: (_ for _ in ()).throw(Reached())
    try:
        for argv, want in [(["--shuffle_labels", "--run_tag", "main"], "blocked"),
                           (["--shuffle_labels"], "allowed"),
                           (["--shuffle_labels", "--run_tag", "ctrl"], "allowed"),
                           (["--run_tag", "main"], "allowed")]:
            sys.argv = ["train_stage1.py"] + argv
            try:
                T.main()
                got = "no outcome"
            except Reached:
                got = "allowed"
            except SystemExit:
                got = "blocked"
            check(" ".join(argv), got, want)
    finally:
        T.split_ids = original


def test_match_config():
    print("\n[5] --match_config leaves one difference: the shuffling")
    with tempfile.TemporaryDirectory() as tmp:
        ref = Path(tmp) / "ref_real_run.json"
        ref.write_text(json.dumps({"config": REAL_CONFIG}))
        control = args(**CONTROL_AS_RUN)

        differs = lambda a: sorted(k for k in T.MATCHABLE + ("shuffle_labels",)
                                   if getattr(a, k) != REAL_CONFIG[k])
        check("before matching", differs(control),
              sorted(["seeds", "epochs", "patience", "max_patches", "shuffle_labels"]))
        check("source recorded", T.apply_match_config(control, str(ref)), "ref_real_run.json")
        check("after matching", differs(control), ["shuffle_labels"])

        # a results file written before --hidden existed has no "hidden" key: matching
        # must leave the default (512) in place rather than fail
        old = Path(tmp) / "pre_hidden_run.json"
        old.write_text(json.dumps({"config": {k: v for k, v in REAL_CONFIG.items() if k != "hidden"}}))
        c2 = args(**dict(CONTROL_AS_RUN, hidden=512))
        T.apply_match_config(c2, str(old))
        check("pre-'hidden' reference keeps the default width", c2.hidden, 512)


def test_bad_reference_is_an_error():
    print("\n[6] a bad --match_config file is refused, not ignored")
    with tempfile.TemporaryDirectory() as tmp:
        empty = Path(tmp) / "no_config.json"
        empty.write_text('{"n_seeds": 5}')
        for label, path in [("missing file", Path(tmp) / "nope.json"),
                            ("no config block", empty)]:
            try:
                T.apply_match_config(args(shuffle_labels=True), str(path))
                check(label, "accepted silently", "SystemExit")
            except SystemExit:
                check(label, "SystemExit", "SystemExit")


def test_git_state_flags_uncommitted_code():
    import subprocess
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        g = lambda *c: subprocess.run(["git", *c], cwd=tmp, capture_output=True)
        g("init", "-q")
        g("config", "user.email", "t@t"); g("config", "user.name", "t")
        (repo / "train.py").write_text("x = 1\n")
        (repo / "results.json").write_text("{}")
        g("add", "."); g("commit", "-qm", "init")

        clean = T.git_state(repo)
        check("clean tree: has a commit", bool(clean["git_commit"]), True)
        check("clean tree: code not dirty", clean["git_dirty_code"], False)
        check("clean tree: no dirty files", clean["git_dirty_files"], [])

        (repo / "results.json").write_text('{"a": 1}')
        only_results = T.git_state(repo)
        check("results changed only: code not dirty", only_results["git_dirty_code"], False)
        check("results changed only: file listed", only_results["git_dirty_files"],
              ["results.json"])

        (repo / "train.py").write_text("x = 2\n")
        (repo / "new_test.py").write_text("")
        dirty = T.git_state(repo)
        check("edited + untracked .py: code dirty", dirty["git_dirty_code"], True)
        check("edited + untracked .py: both named",
              [f for f in dirty["git_dirty_files"] if f.endswith(".py")],
              ["new_test.py", "train.py"])

        not_a_repo = T.git_state(Path(tmp) / "..")
        check("outside a repo: unknown, not clean", not_a_repo["git_dirty_code"]
              if not_a_repo["git_commit"] is None else None, None)


def main():
    for t in (test_tags, test_paths, test_control_cannot_take_the_main_paths,
              test_match_config, test_bad_reference_is_an_error,
              test_git_state_flags_uncommitted_code):
        t()
    print()
    if FAILURES:
        print("FAILED:\n  " + "\n  ".join(FAILURES))
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
