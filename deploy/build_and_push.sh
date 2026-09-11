#!/bin/bash
# Build the arm64 image, push to ECR, stamp build-marker.txt.
# Usage: bash deploy/build_and_push.sh [--tag <marker>] [--repo <name>] [--region <r>] [--no-push]
set -euo pipefail

TAG=""
REPO="spaghetti-sentinel"
REGION="${AWS_REGION:-us-east-1}"
PUSH="1"

while [ $# -gt 0 ]; do
  case "$1" in
    --tag) TAG="$2"; shift 2 ;;
    --repo) REPO="$2"; shift 2 ;;
    --region) REGION="$2"; shift 2 ;;
    --no-push) PUSH="0"; shift ;;
    *) echo "unknown flag $1" >&2; exit 2 ;;
  esac
done

sanitise() {
  echo "$1" | tr -c 'A-Za-z0-9._-' '_' | cut -c1-64
}

if [ -z "$TAG" ]; then
  GIT_SHA="$(git rev-parse --short HEAD 2>/dev/null || echo nogit)"
  MARKER="$(date -u +%Y-%m-%dT%H:%M:%SZ)-${GIT_SHA}"
else
  MARKER="$TAG"
fi
MARKER="$(sanitise "$MARKER")"

ACCOUNT="$(aws sts get-caller-identity --query Account --output text --region "$REGION")"
IMAGE_URI="${ACCOUNT}.dkr.ecr.${REGION}.amazonaws.com/${REPO}:${MARKER}"

aws ecr describe-repositories --repository-names "$REPO" --region "$REGION" >/dev/null 2>&1 || \
  aws ecr create-repository --repository-name "$REPO" --region "$REGION" >/dev/null

if [ "$PUSH" = "1" ]; then
  aws ecr get-login-password --region "$REGION" | \
    docker login --username AWS --password-stdin "${ACCOUNT}.dkr.ecr.${REGION}.amazonaws.com"
  docker buildx build --platform linux/arm64 --build-arg BUILD_MARKER="$MARKER" \
    -t "$IMAGE_URI" --push .
  DIGEST="$(aws ecr describe-images --repository-name "$REPO" \
    --image-ids imageTag="$MARKER" --region "$REGION" \
    --query 'imageDetails[0].imageDigest' --output text)"
else
  docker buildx build --platform linux/arm64 --build-arg BUILD_MARKER="$MARKER" \
    -t "$IMAGE_URI" --load .
  DIGEST="local-no-push"
fi

echo "$MARKER" > build-marker.txt
echo "BUILD_MARKER=${MARKER}"
echo "IMAGE_URI=${IMAGE_URI}"
echo "IMAGE_DIGEST=${DIGEST}"
