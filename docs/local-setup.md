# Local setup on this laptop (Atharv's Windows 11 machine)

## What is installed and where

| Tool | Version | Location |
|---|---|---|
| Python venv | 3.11 | `D:\Projects\1\chaosarena\.venv` |
| pytest + fakeredis | 8.3.4 / 2.25.0 | in the venv |
| Prometheus | 2.53.2 | `tools\prometheus-2.53.2.windows-amd64` |
| Grafana | 11.2.0 | `tools\grafana-v11.2.0` |
| kubectl | v1.30.0 | `tools\bin\kubectl.exe` |
| kind | v0.23.0 | `tools\bin\kind.exe` |
| helm | v3.15.4 | `tools\bin\helm.exe` |
| Docker Desktop | 4.99.0 / engine 29.9.3 | `C:\Program Files\Docker\Docker` (running) |
| WSL runtime | 3.0.5.0 (kernel 6.18.58.1-1, WSLg 1.0.79) | installed system-wide |

`tools/` is gitignored — binaries are not part of the source repo.

## What works right now (no Docker needed)

```powershell
cd D:\Projects\1\chaosarena
.\.venv\Scripts\python.exe scripts\run_local.py          # terminal 1
powershell -File scripts\run_observability_native.ps1    # terminal 2
```

Then open:
- Grafana: http://localhost:3000 (admin / admin) → **ChaosArena - ShopApp Live**
- Prometheus: http://localhost:9090

Verified live query:
```
sum by (service) (rate(http_requests_total[1m]))
```
returned real values for cart, user, product, payment, order and loadgen.

## Kubernetes cluster (created and verified)

WSL2 features were enabled with `/norestart`, so a restart was required. After the
restart, `wsl --install --no-distribution` installed the WSL runtime package
(3.0.5.0) because the features alone were not enough. Docker Desktop was then
started and the daemon came up on engine 29.9.3.

The `chaosarena` Kind cluster was created and all Phase 1 manifests were applied:

```powershell
$env:PATH = "D:\Projects\1\chaosarena\tools\bin;C:\Program Files\Docker\Docker\resources\bin;" + $env:PATH
kind create cluster --name chaosarena --config infra/kind-config.yaml
kubectl apply -f infra/k8s/namespaces.yaml
kubectl apply -k infra/k8s/observability
kubectl apply -k infra/k8s/overlays/test
kubectl apply -k infra/k8s/overlays/prod
```

Useful verification commands:

```powershell
kubectl get pods -A
kubectl -n monitoring get pods
kubectl -n monitoring logs ds/promtail --tail=20
```

To see the dashboards, port-forward the services (run each in its own terminal):

```powershell
kubectl -n monitoring port-forward svc/grafana 3000:3000
kubectl -n monitoring port-forward svc/prometheus 9090:9090
kubectl -n monitoring port-forward svc/loki 3100:3100
```

Then open http://localhost:3000 (admin / admin) → **ChaosArena - ShopApp Live**.

### One fix made during deployment

Kustomize refuses ConfigMap file sources outside its root, so the Grafana
datasource/provider/dashboard files were copied into
`infra/k8s/observability/` and the `kustomization.yaml` entries updated to point
at those local copies. Also, Promtail was switched from Kubernetes SD to a
static pod-log path with `regex` → `labels` → `cri` pipeline stages. This was
necessary because Kubernetes SD discovered zero targets on this single-node Kind
cluster; the static path is simple and verified with real log entries in Loki.

## Why the native path exists

Docker needs WSL2, and WSL2 could not be activated without a reboot inside this
session. Running Prometheus and Grafana as native Windows binaries gives a real
live dashboard immediately, without faking any metrics. The Kubernetes manifests
remain the production path and are unchanged.
