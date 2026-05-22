#!/bin/bash
# Login-node smoke test — mimics run.slurm for single-node, single-rank testing.
# Run this instead of sbatch when you want to verify the pipeline locally.
set -e

EXAMPLE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export FLOWCEPT_SETTINGS_PATH="$EXAMPLE_DIR/flowcept_settings.yaml"
export LMDB_PATH="$EXAMPLE_DIR/flowcept_output/lmdb/$(date +%Y%m%d_%H%M%S)"
export LD_LIBRARY_PATH=/opt/rocm-7.0.2/lib:$LD_LIBRARY_PATH

echo "Settings: $FLOWCEPT_SETTINGS_PATH"
echo "LMDB path: $LMDB_PATH"

# ── 1. Start Redis ────────────────────────────────────────────────────────────
pkill -f redis-server 2>/dev/null || true; sleep 1   # clear any stale Redis
echo "[$(date)] Starting Redis..."
flowcept --start-redis &
sleep 3

# ── 2. Start Flowcept consumer ────────────────────────────────────────────────
echo "[$(date)] Starting Flowcept consumer..."
flowcept --start-consumption-services &
sleep 2

# ── 3. Run workflow (single rank, no MPI) ─────────────────────────────────────
echo "[$(date)] Running workflow..."
python "$EXAMPLE_DIR/login_node_workflow.py"

echo "[$(date)] Workflow complete."

# ── 4. Teardown ───────────────────────────────────────────────────────────────
echo "[$(date)] Stopping Flowcept consumer..."
flowcept --stop-consumption-services

echo "[$(date)] Stopping Redis..."
flowcept --stop-redis

echo "[$(date)] Done. Output written to: $EXAMPLE_DIR/flowcept_output"
