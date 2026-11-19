# Phase 2 — Chaos Mesh + 7 allowlisted attacks

## What this phase adds

An `attacker/` module that can inject seven real faults into the **test**
namespace only. It can never reach `shop-prod`: the namespace list and the
service list are hard-coded in Python, and every generated object is validated
again before it is applied. Chaos Mesh itself is installed in the standard
cluster-scoped mode (the namespace-scoped chart mode crash-looped on this Kind
cluster); the Python allowlist is the safety boundary.

## Files

| Path | Purpose |
|---|---|
| `attacker/allowlist.py` | Hard `shop-test` namespace + service allowlist and manifest validation |
| `attacker/specs.py` | The 7 attack definitions and manifest builder |
| `attacker/kubectl.py` | Thin `kubectl` wrapper used to apply/delete chaos objects |
| `attacker/runner.py` | Applies an attack, holds it, and guarantees cleanup in `finally` + `atexit` |
| `attacker/cli.py` | `python -m attacker.cli` commands |
| `tests/test_phase2.py` | 18 tests for allowlist, all 7 attacks and cleanup |
| `Makefile` | `chaos-install`, `chaos-list`, `chaos-status`, `chaos-clean`, `attack` |

## The seven attacks

| Name | Chaos Mesh kind | Effect | Default target |
|---|---|---|---|
| `pod-kill` | PodChaos | Kill one pod (K8s restarts it) | order-service |
| `pod-failure` | PodChaos | Pod unavailable for the duration | cart-service |
| `network-latency` | NetworkChaos | 300 ms delay on all traffic | payment-service |
| `network-loss` | NetworkChaos | 40% packet loss | order-service |
| `network-partition` | NetworkChaos | Cut both directions between two services | order-service ↔ product-service |
| `cpu-stress` | StressChaos | 2 workers at 80% CPU | order-service |
| `memory-stress` | StressChaos | 2 workers allocating 256 MB | product-service |

## Install (one time)

```powershell
$env:PATH = "D:\Projects\1\chaosarena\tools\bin;" + $env:PATH
helm repo add chaos-mesh https://charts.chaos-mesh.org
helm repo update chaos-mesh
helm upgrade --install chaos-mesh chaos-mesh/chaos-mesh --version 2.8.8 `
  --namespace chaos-mesh --create-namespace `
  --set clusterScoped=true `
  --set controllerManager.hostNetwork=false `
  --set controllerManager.replicaCount=1 `
  --set chaosDaemon.runtime=containerd `
  --set chaosDaemon.socketPath=/run/containerd/containerd.sock `
  --set dashboard.create=false --wait --timeout 10m
kubectl -n chaos-mesh get pods
```

Why these flags: `hostNetwork=false` avoids a port-10250 collision with the
Kind node's kubelet, `replicaCount=1` suits a single-node cluster, and
`chaosDaemon.runtime=containerd` plus the socket path match Kind's container
runtime so network and stress faults can actually be injected. We tried
`clusterScoped=false` with `targetNamespace=shop-test` first, but that chart
mode repeatedly failed DNSChaos cache sync and crash-looped the controller, so
the stable cluster-scoped mode is used instead.

## Run an attack

```powershell
cd D:\Projects\1\chaosarena
.\.venv\Scripts\python.exe -m attacker.cli list
.\.venv\Scripts\python.exe -m attacker.cli show network-latency
.\.venv\Scripts\python.exe -m attacker.cli attack pod-kill --target order-service --duration 10
.\.venv\Scripts\python.exe -m attacker.cli status
.\.venv\Scripts\python.exe -m attacker.cli cleanup
```

`attack` applies one custom resource, waits for the requested duration and
deletes it in a `finally` block. The custom resource also carries a Chaos Mesh
`duration`, so the fault stops even if the CLI process is killed.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest -q
kubectl get crd | Select-String chaos-mesh
kubectl -n chaos-mesh get pods
kubectl -n shop-test get podchaos,networkchaos,stresschaos
```

Expected: 27 tests pass (9 from Phase 1 + 18 new), 3 Chaos Mesh pods Running,
and no chaos objects left after an attack finishes.

### Results actually measured on this laptop

- All 7 generated manifests passed `kubectl apply --dry-run=server`.
- `pod-failure` on `cart-service` for 15 s: `ok: true`, `cleanup_ok: true`,
  all pods Running afterwards, zero chaos objects left.
- `network-latency` on `payment-service` for 60 s: p95 of `order-service`
  over a 30-second Prometheus window went **0.24 s → 0.845 s → 0.24 s**
  (before / during / after). Chaos Mesh events showed
  `Successfully apply chaos for shop-test/payment-service-...` for both pods.

## Common errors and fixes

| Error | Cause | Fix |
|---|---|---|
| `listen tcp 0.0.0.0:10250: bind: address already in use` | `controllerManager.hostNetwork=true` collides with kubelet | Use `hostNetwork=false` |
| `didn't have free ports for the requested pod ports` | 3 replicas with hostNetwork on a single node | Set `controllerManager.replicaCount=1` |
| `AttackRejected: namespace 'shop-prod' is not allowed` | Someone tried to attack production | This is the safety guard working; do not remove it |
| Attack object stays `Running` | `kubectl` not on PATH / wrong kubeconfig | Set `KUBECTL` env var to `tools\bin\kubectl.exe` |
| Chaos has no effect | Wrong container runtime configured | Use `runtime=containerd` and socket `/run/containerd/containerd.sock` |
| Controller restarts with `timed out waiting for cache to be synced` | `clusterScoped=false` in Chaos Mesh 2.8.8 on Kind | Use `clusterScoped=true`; keep the Python allowlist |
| Metric change appears only after the attack ends | Prometheus `[1m]` rate window lags | Sample with `[30s]` for a demo |

## Why cleanup is deterministic

Every chaos object carries `chaosarena.io/attack=true`. Cleanup selects only
that label and deletes exactly those objects, so it cannot touch experiments
created by anyone else. The `finally` block plus an `atexit` hook mean an
exception, a Ctrl-C or a normal exit all end with the same cleanup call.
