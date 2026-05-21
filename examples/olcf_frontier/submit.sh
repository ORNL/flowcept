#!/bin/bash
set -e

if [ -z "${1}" ]; then
  echo "Usage: CONDA_ROOT=/path/to/miniconda bash submit.sh <project-account>"
  exit 1
fi

if [ -z "${CONDA_ROOT}" ]; then
  echo "Error: CONDA_ROOT is not set. Example:"
  echo "  CONDA_ROOT=/path/to/miniconda bash submit.sh <project-account>"
  exit 1
fi

ACCOUNT=${1}
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

sbatch \
  --account="$ACCOUNT" \
  --partition=batch \
  --qos=debug \
  --time=00:30:00 \
  --export=ALL,CONDA_ROOT="$CONDA_ROOT" \
  "$SCRIPT_DIR/run.slurm"
