#!/bin/bash
#SBATCH --job-name=flowcept_frontier
#SBATCH --nodes=2
#SBATCH --ntasks-per-node=8
#SBATCH --cpus-per-task=7
#SBATCH --time=00:30:00
#SBATCH --output=%x_%j.out
#SBATCH --error=%x_%j.err

# ── Environment ──────────────────────────────────────────────────────────────
module load PrgEnv-gnu

# Set CONDA_ROOT to your miniconda/anaconda installation directory
source "${CONDA_ROOT}/etc/profile.d/conda.sh"
conda activate flowcept

EXAMPLE_DIR="$SLURM_SUBMIT_DIR"
export FLOWCEPT_SETTINGS_PATH="$EXAMPLE_DIR/flowcept_settings.yaml"
export LMDB_PATH="$EXAMPLE_DIR/flowcept_output/lmdb/$SLURM_JOB_ID"

# Flowcept reads MQ_HOST env var to override mq.host in settings.
export MQ_HOST=$(hostname)

echo "Job node: $MQ_HOST"
echo "Settings: $FLOWCEPT_SETTINGS_PATH"
echo "LMDB path: $LMDB_PATH"

# ── 1. Start Redis ────────────────────────────────────────────────────────────
pkill -f redis-server 2>/dev/null; sleep 1   # clear any stale Redis from a previous job
echo "[$(date)] Starting Redis..."
flowcept --start-redis &
sleep 3

# ── 2. Start Flowcept consumer (writes MQ messages to LMDB) ──────────────────
echo "[$(date)] Starting Flowcept consumer..."
flowcept --start-consumption-services &
sleep 2

# ── 3. Run the workflow across all nodes/ranks ────────────────────────────────
echo "[$(date)] Launching MPI workflow..."
srun --ntasks=$SLURM_NTASKS \
     --ntasks-per-node=$SLURM_NTASKS_PER_NODE \
     python "$EXAMPLE_DIR/workflow.py"

echo "[$(date)] Workflow complete."

# ── 4. Teardown ───────────────────────────────────────────────────────────────
echo "[$(date)] Stopping Flowcept consumer..."
flowcept --stop-consumption-services

echo "[$(date)] Stopping Redis..."
flowcept --stop-redis

echo "[$(date)] Done. Output written to: $SLURM_SUBMIT_DIR/flowcept_output"
