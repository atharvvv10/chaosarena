# Phase 1 — ShopApp and Observability

## What this phase built

The demo application and its measurements: five small FastAPI services, a
load generator, a shared observability package, Kustomize overlays for
`shop-test` and `shop-prod`, and local Prometheus/Grafana/Loki.

## Plan (executed)

1. Create one FastAPI app per service with identical `/health` and `/metrics`.
2. Add `common/` so every service emits the same structured logs and metrics.
3. Add `loadgen` to generate steady traffic through the service graph.
4. Add Kustomize bases/overlays so test and prod differ only by `VERSION`.
5. Add Prometheus, Grafana and Loki (with Promtail) for metrics and logs.
6. Provide a Docker Compose path for laptops without Kubernetes.
7. Verify local Python, Docker Compose and Kind deployments.

## Important paths

| Path | Purpose |
| --- | --- |
| `services/user/`, `product/`, `cart/`, `order/`, `payment/` | Five app services |
| `services/loadgen/` | Steady synthetic traffic |
| `common/` | Shared logging, metrics and health helpers |
| `infra/k8s/base/`, `overlays/test/`, `overlays/prod/` | Kustomize manifests |
| `infra/k8s/observability/` | Prometheus, Grafana, Loki, Promtail |
| `docker-compose.yml` | No-Kubernetes local stack |
| `scripts/build-and-load.sh`, `smoke-test.sh` | Kind image load and smoke test |
| `tests/test_phase1.py` | 9 acceptance tests |

## Commands

```powershell
# Pure Python, no containers
make dev-local

# Docker Compose
make dev-up
make dev-down

# Kind cluster
make cluster
make deploy
make status
make smoke
make dashboard   # Grafana on http://localhost:3000, admin/admin
```

## Verified results

- All five services and loadgen answer `/health`.
- Metrics are scraped by Prometheus; logs reach Loki through Promtail.
- `shop-test` and `shop-prod` deploy from the same base with different versions.
- Local Python, Docker Compose and Kind paths all worked.
- 9 Phase 1 tests pass.

## Common errors and fixes

| Problem | Cause | Fix |
| --- | --- | --- |
| Pods are `ImagePullBackOff` | Images not loaded into Kind | Run `make deploy`, which builds and loads images. |
| Grafana shows no data | Prometheus target not ready | Wait for `make status`, then refresh the dashboard. |
| Port 3000 already used | Another Grafana instance | Stop the old port-forward or change the local port. |

## Why these choices

Small services make attacks easy to interpret. One shared observability module
means the Defender later sees identical signals from every service, which is
exactly what an anomaly detector needs. Kustomize overlays keep production
physically separate while sharing the same reviewed manifests.

## Cost check

All images are built locally from open-source dependencies. No registry, hosted
observability or paid dashboard is used.
