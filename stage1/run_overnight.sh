#!/bin/bash
# run_overnight.sh - regularisation sweep -> (if it changes the setting) Stage 1 rerun + control
#                    -> 5-fold cross-validation.   THESIS_LOG.md, Phase 12.
#
#   cd ~/TCGA_thesis/stage1
#   bash run_overnight.sh smoke                  # 3-5 minutes: proves every step runs
#   nohup caffeinate -is bash run_overnight.sh < /dev/null > overnight.log 2>&1 &     # the real run, ~4 h
set -euo pipefail
cd "$(dirname "$0")"
ulimit -n 10240 2>/dev/null || ulimit -n 4096 2>/dev/null || true   # macOS default is 256
echo "open-file limit: $(ulimit -n)"

if [ "${1:-}" = "smoke" ]; then
  python3 -u reg_sweep.py --smoke
  python3 -u crossval.py --smoke
  echo "SMOKE OK - every step ran. Nothing here is a result."
  exit 0
fi

echo "=== 1/3 regularisation sweep  $(date)"
python3 -u reg_sweep.py
CHOICE=$(python3 -c "import json; print(json.load(open('reg_sweep.json'))['choice'])")
FLAGS=$(python3 -c "import json; print(json.load(open('reg_sweep.json'))['choice_flags'])")
echo "sweep chose: $CHOICE"

if [ "$CHOICE" != "baseline" ]; then
  echo "=== 2/3 new setting ($FLAGS): rerun Stage 1 and its matched control  $(date)"
  mkdir -p archive_pre_sweep
  cp -n results_stage1.json results_shuffled.json stage1_mil.pt stage1_mil_shuffled.pt archive_pre_sweep/
  python3 -u train_stage1.py --seeds 5 $FLAGS
  python3 -u train_stage1.py --shuffle_labels --match_config results_stage1.json
else
  echo "=== 2/3 baseline kept - Stage 1 results stand, nothing to rerun"
fi

echo "=== 3/3 5-fold cross-validation  $(date)"
python3 -u crossval.py --use_sweep
echo "=== ALL DONE  $(date)"
