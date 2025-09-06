#!/bin/bash

# Exit immediately on non-zero exit status and propagate errors in pipelines
set -e
set -o pipefail

# Display usage/help message
usage() {
  echo -e "\nUsage: $0 <examples_dir> <with_mongo> [tests]\n"
  echo "Arguments:"
  echo "  examples_dir   Path to the examples directory (Mandatory)"
  echo "  with_mongo     Boolean flag (true/false) indicating whether to include MongoDB support (Mandatory)"
  echo "  tests          Optional array of test cases to run (e.g., \"test1 test2 test3\")"
  echo -e "\nExample:"
  echo "  $0 examples true"
  echo "  $0 examples false \"test1 test2\""
  exit 1
}

# Check if the required arguments are provided
if [[ -z "$1" || -z "$2" ]]; then
  echo "Error: Missing mandatory arguments!"
  usage
fi

# Function to run tests with common steps
run_test() {
  test_path="${EXAMPLES_DIR}/${1}"
  test_type="$1"
  with_mongo="$2"
  echo "Test type=${test_type}"
  echo "Starting $test_path"

  pip uninstall flowcept -y > /dev/null 2>&1 || true  # Ignore errors during uninstall

  pip install . > /dev/null 2>&1
  pip install .[extras] > /dev/null 2>&1
  pip install .[lmdb]
  pip list

  if [[ "$with_mongo" == "true" ]]; then
    pip install .[mongo] > /dev/null 2>&1
  fi


  # The following block is only needed to install special dependencies.
  if [[ "$test_type" =~ "mlflow" ]]; then
    echo "Installing mlflow"
    pip install .[mlflow] > /dev/null 2>&1
  elif [[ "$test_type" =~ "dask" ]]; then
    echo "Installing dask"
    pip install .[dask] > /dev/null 2>&1
  elif [[ "$test_type" =~ "tensorboard" ]]; then
    echo "Installing tensorboard"
    pip install .[tensorboard] > /dev/null 2>&1
  elif [[ "$test_type" =~ "single_layer_perceptron" ]]; then
    echo "Installing ml_dev dependencies"
    pip install .[ml_dev] > /dev/null 2>&1
  elif [[ "$test_type" =~ "llm_complex" ]]; then
    echo "Installing ml_dev dependencies"
    pip install .[dask] > /dev/null 2>&1
    pip install .[ml_dev]
    echo "Defining python path for llm_complex..."
  fi

  echo "Running $test_path ..."
  python "$test_path" | tee output.log
  echo "Ok, ran $test_path."
  if grep -iq "error" output.log; then
    echo "Test $test_path failed! See output.log for details."
    cat output.log
    exit 1
  fi

  echo "Great, no errors to run $test_path."

  rm output.log
}

# Get the examples directory as the first argument
EXAMPLES_DIR="$1"
WITH_MONGO="$2"
echo "Using examples directory: $EXAMPLES_DIR"
echo "With Mongo? ${WITH_MONGO}"

# Define the test cases
default_tests=("instrumented_simple_example.py" "instrumented_loop_example.py" "distributed_consumer_example.py" "dask_example.py" "mlflow_example.py" "single_layer_perceptron_example.py" "llm_complex/llm_main_example.py" "unmanaged/main.py")
# Removing tensorboard_example.py from the list above while the dataset link is not fixed.

# Use the third argument if provided, otherwise use default tests
if [[ -n "$3" ]]; then
  eval "tests=($3)"
else
  tests=("${default_tests[@]}")
fi

echo "Running the following tests: ${tests[*]}"

# Iterate over the tests and run them
for test_ in "${tests[@]}"; do
  run_test $test_ $WITH_MONGO
done

echo "Tests completed successfully!"
