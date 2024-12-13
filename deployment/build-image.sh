#!/bin/bash

if [ ! -d "src" ]; then
    echo "Error: 'src' directory does not exist in the current path. Please run it from the project root."
    exit 1
fi

# Download the Miniconda Dockerfile
echo "Downloading Miniconda Dockerfile..."
curl --silent -o Dockerfile_miniconda https://raw.githubusercontent.com/anaconda/docker-images/refs/heads/main/miniconda3/debian/Dockerfile
cat Dockerfile_miniconda

# Build the Miniconda image locally
echo "Building miniconda:local image..."
docker build -t miniconda:local -f Dockerfile_miniconda .
rm Dockerfile_miniconda

# Check if the Miniconda build failed
if [ $? -ne 0 ]; then
    echo "Error: Miniconda image build failed."
    exit 1
fi

echo "Miniconda image built successfully."
# Step 4: Build the flowcept image with both 'latest' and versioned tags
echo "Building flowcept image with latest and version tags..."
docker build --no-cache -t flowcept:latest -f deployment/Dockerfile .

# Check if the flowcept build succeeded
if [ $? -eq 0 ]; then
    echo "Flowcept image built successfully with tags 'latest'."
    echo "You can now run it using $> make run"
else
    echo "Failed to build flowcept image."
    exit 1
fi

