#!/bin/bash

if [ ! -d "src" ]; then
    echo "Error: 'src' directory does not exist in the current path. Please run it from the project root."
    exit 1
fi

# Build the flowcept image with latest tag
echo "Building flowcept image with latest and version tags..."
docker build -t flowcept:latest -f deployment/Dockerfile .

# Check if the flowcept build succeeded
if [ $? -eq 0 ]; then
    echo "Flowcept image built successfully with tags 'latest'."
    echo "You can now run it using $> make run"
else
    echo "Failed to build flowcept image."
    exit 1
fi
