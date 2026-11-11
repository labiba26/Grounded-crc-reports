#!/bin/sh
# make_bundle.sh - pack what Stage 2 needs on the GPU server (run on the Mac, from the repo root).
# Writes stage2_bundle.tar.gz (~2 MB). The bundle records the git commit it came from,
# because the server has no git repository (generate.py reads stage2/BUNDLE_INFO.json).
set -e
cd "$(dirname "$0")/.."
python3 - <<'PY'
import json, subprocess
run = lambda *c: subprocess.run(["git", *c], capture_output=True, text=True).stdout
# porcelain lines start with a status column that may be a space: never strip the whole output
files = [l[3:] for l in run("status", "--porcelain").splitlines() if l.strip()]
json.dump({"git_commit": run("rev-parse", "--short", "HEAD").strip(), "bundled_from": "Mac",
           "git_dirty_code": any(f.endswith(".py") for f in files), "git_dirty_files": files},
          open("stage2/BUNDLE_INFO.json", "w"), indent=1)
PY
tar czf stage2_bundle.tar.gz stage2/*.py stage2/BUNDLE_INFO.json stage2/inputs \
    stage3/*.py stage1/extract_fields.py stage1/structured_labels.json tcga_report_text/reports_txt
echo "wrote stage2_bundle.tar.gz ($(du -h stage2_bundle.tar.gz | cut -f1)) from commit $(git rev-parse --short HEAD)"
