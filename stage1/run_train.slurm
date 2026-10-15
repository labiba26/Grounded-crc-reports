#!/bin/bash
#SBATCH --job-name=tcga-stage1
#SBATCH --output=logs/stage1_%j.out
#SBATCH --error=logs/stage1_%j.err
#SBATCH --time=04:00:00
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
# ---- ADJUST THESE TWO FOR YOUR CLUSTER -------------------------------------
# Ask your admin or run `sinfo` to see partition names, and `sacctmgr show assoc
# user=$USER` for your account. The job will be rejected without valid values.
##SBATCH --partition=gpu
##SBATCH --account=your_account
# ----------------------------------------------------------------------------

set -euo pipefail
mkdir -p logs

module load cuda 2>/dev/null || echo "no module system - assuming CUDA already available"

source ~/tcga-env/bin/activate

cd "$SLURM_SUBMIT_DIR"
nvidia-smi

python3 train_stage1.py \
    --epochs 30 \
    --max_patches 2048 \
    --batch_size 8 \
    --num_workers 8 \
    --lr 2e-4

echo "done. results in results_stage1.json"
