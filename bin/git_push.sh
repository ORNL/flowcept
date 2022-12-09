#!/bin/bash

function help()
{
    echo "Usage: bash $0 \"<commit message>\""
    exit 2
}

function code_check() {
  black --check .
  flake8 .
}

function pull_check() {
  git pull
}

function version_bump() {
  export PYTHONPATH=$PYTHONPATH:flowcept
  export BRANCH_NAME=$(git branch | sed -n -e 's/^\* \(.*\)/\1/p')
  python .github/workflows/version_bumper.py
}

function commit_and_push() {
  git add .
  git status
  git commit -m "${1}"
  echo "${1}"
  #git push
}

VALID_ARGUMENTS=$#
if [ "$VALID_ARGUMENTS" -eq 0 ]; then
  help
fi

if ! code_check; then
  echo "Sorry, code check did not pass"
  exit 1
fi

if ! pull_check; then
  echo "Sorry, could not pull from repository"
  exit 1
fi

if ! version_bump; then
  echo "Sorry, could not bump version"
  exit 1
fi

if ! commit_and_push "${1}"; then
  echo "Sorry, could not commit and push"
  exit 1
fi


