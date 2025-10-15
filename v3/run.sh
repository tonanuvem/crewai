#!/bin/bash

echo "Building Docker image with direct pip install..."
docker build -f Dockerfile -t tonanuvem/dev-multi-agent-app  .

echo "Image size:"
docker images tonanuvem/dev-multi-agent-app

echo "Starting container..."
docker run -d \
  --name dev-multi-agent-app \
  -p 8501:8501 \
  -v $(pwd)/logs:/app/logs \
  -v $(pwd)/outputs:/app/outputs \
  tonanuvem/dev-multi-agent-app 

echo "Running... porta: 8501"
