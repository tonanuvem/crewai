#!/bin/bash

IMAGE="tonanuvem/sisprime-multi-banco-app"
CONTAINER="sisprime-multi-banco-agent-app"
PORTA="8801"

echo "Building Docker image with direct pip install..."
docker build -f Dockerfile -t $IMAGE  .

echo "Image size:"
docker images $IMAGE

echo "Starting container..."
docker run -d \
  --name $CONTAINER \
  -p $PORTA:8501 \
  -v $(pwd)/logs:/app/logs \
  -v $(pwd)/outputs:/app/outputs \
  $IMAGE

echo "Running... porta: $PORTA"
