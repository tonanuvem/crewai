#!/bin/bash

IMAGE="tonanuvem/sisprime-multi-banco-agent"
CONTAINER="sisprime-multi-banco-agent"

echo "Stopping container..."

if [ "$(docker ps -q -f name=$CONTAINER)" ]; then
  docker stop $CONTAINER
else
  echo "Container not running."
fi

echo "Removing container..."

if [ "$(docker ps -aq -f name=$CONTAINER)" ]; then
  docker rm $CONTAINER
else
  echo "Container does not exist."
fi

echo "Removing image..."

if [ "$(docker images -q $IMAGE)" ]; then
  docker rmi $IMAGE
else
  echo "Image does not exist."
fi

echo "Cleanup finished."
