#!/bin/bash

# Exit immediately on non-zero exit status and propagate errors in pipelines
set -e
set -o pipefail

# Function to run tests with common steps
run_test() {
  test_path="${EXAMPLES_DIR}/${1}_example.py"
  test_type="$1"
  with_mongo="$2"
  echo "Test type=${test_type}"
  echo "Running $test_path"

  pip uninstall flowcept -y > /dev/null 2>&1 || true  # Ignore errors during uninstall

  pip install . > /dev/null 2>&1

  if [[ "$with_mongo" == "true" ]]; then
    pip install .[mongo] > /dev/null 2>&1
  fi

  if [[ "$test_type" =~ "mlflow" ]]; then
    echo "Installing mlflow"
    pip install .[mlflow] > /dev/null 2>&1
  elif [[ "$test_type" =~ "dask" ]]; then
    echo "Installing dask"
    pip install .[dask] > /dev/null 2>&1
  elif [[ "$test_type" =~ "tensorboard" ]]; then
    echo "Installing tensorboard"
    pip install .[tensorboard] > /dev/null 2>&1
  fi

  # Run the test and capture output
  python "$test_path" | tee output.log

  # Check for errors in the output
  if grep -iq "error" output.log; then
    echo "Test failed! See output.log for details."
    exit 1
  fi

  # Clean up the log file
  rm output.log
}

# Get the examples directory as the first argument
EXAMPLES_DIR="$1"
WITH_MONGO="$2"
echo "Using examples directory: $EXAMPLES_DIR"
echo "With Mongo? ${WITH_MONGO}"

# Define the test cases
tests=("instrumented_simple" "instrumented_loop" "dask" "mlflow" "tensorboard")

# Iterate over the tests and run them
for test_ in "${tests[@]}"; do
  run_test $test_ $WITH_MONGO
done

echo "Tests completed successfully!"
