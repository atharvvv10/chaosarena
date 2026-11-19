#!/usr/bin/env bash
set -euo pipefail

NS="${NS:-shop-test}"
PF_PORT="${PF_PORT:-18004}"
kubectl -n "$NS" port-forward svc/order-service "${PF_PORT}:8000" >/tmp/chaosarena-pf.log 2>&1 &
PF_PID=$!
trap 'kill "$PF_PID" 2>/dev/null || true' EXIT
sleep 3

echo "==> order-service health"
curl -fsS "http://127.0.0.1:${PF_PORT}/health"; echo

echo "==> product catalogue"
curl -fsS "http://127.0.0.1:${PF_PORT}/ready"; echo

echo "==> metrics sample (first 12 lines)"
curl -fsS "http://127.0.0.1:${PF_PORT}/metrics" | head -n 12
