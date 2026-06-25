#!/bin/bash
set -e

if [ ! -d "src" ]; then
    echo "Error: 'src' directory does not exist in the current path. Please run it from the project root."
    exit 1
fi

IMAGE_TAG="${IMAGE_TAG:-flowcept:latest}"
EXTRAS="${EXTRAS-all}"
PYTHON_VERSION="${PYTHON_VERSION:-3.11.10}"
BUILD_UI="${BUILD_UI:-true}"
FLOWCEPT_CMD="${FLOWCEPT_CMD:-bash}"

echo "Building ${IMAGE_TAG}"
echo "  PYTHON_VERSION=${PYTHON_VERSION}"
echo "  EXTRAS=${EXTRAS:-<core only>}"
echo "  BUILD_UI=${BUILD_UI}"
echo "  FLOWCEPT_CMD=${FLOWCEPT_CMD}"

docker build \
    --build-arg "PYTHON_VERSION=${PYTHON_VERSION}" \
    --build-arg "EXTRAS=${EXTRAS}" \
    --build-arg "BUILD_UI=${BUILD_UI}" \
    --build-arg "FLOWCEPT_CMD=${FLOWCEPT_CMD}" \
    -t "${IMAGE_TAG}" \
    -f deployment/Dockerfile \
    ${DOCKER_BUILD_ARGS:-} \
    .

echo "Flowcept image built successfully: ${IMAGE_TAG}"
echo "You can now run it using: make run"
