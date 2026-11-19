#!/usr/bin/env bash
set -euo pipefail

CLUSTER="${CLUSTER:-chaosarena}"
TAG="${IMG_TAG:-dev}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

for svc in user product cart order payment loadgen; do
  image="shopapp-${svc}:${TAG}"
  echo "==> building ${image}"
  docker build -f "${ROOT}/services/${svc}/Dockerfile" -t "${image}" "${ROOT}/services"
  echo "==> loading ${image} into kind cluster ${CLUSTER}"
  kind load docker-image "${image}" --name "${CLUSTER}"
done
