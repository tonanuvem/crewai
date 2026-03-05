#!/bin/bash

IMAGE="tonanuvem/sisprime-multi-agent-app"
CONTAINER="sisprime-multi-agent-app"

echo "Building Docker image with direct pip install..."
docker build -f Dockerfile -t $IMAGE  .

echo "Image size:"
docker images $IMAGE

echo "Starting container..."
docker run -d \
  --name $CONTAINER \
  -p 8801:8501 \
  -v $(pwd)/logs:/app/logs \
  -v $(pwd)/outputs:/app/outputs \
  $IMAGE

echo "Running... porta: 8801"
