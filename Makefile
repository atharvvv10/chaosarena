.DEFAULT_GOAL := help
CLUSTER ?= chaosarena
KUBECTL ?= kubectl
PYTHON ?= python
IMG_TAG ?= dev
ATTACK ?= pod-kill
TARGET ?= order-service
DURATION ?= 30
THRESHOLD ?= 70

.PHONY: help verify technical-demo demo-media demo-media-offline benchmarks experimental-validation experimental-holdout experimental-summary cluster deploy dashboard metrics logs status smoke baseline train defend detect defender-guard attack battle gate gate-api ui-install ui-build ui-dev rl-guard rl-train rl-policy rl-real rl-real-dry report report-groq ci-check ci-selftest ci-guard dev-up dev-down clean chaos-install chaos-list chaos-status chaos-clean

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

verify: ## Phase 9: run every cluster-free check in one command
	$(PYTHON) scripts/verify_all.py

technical-demo: ## Short evidence-based technical demo (no cluster needed)
	$(PYTHON) scripts/technical_demo.py

demo-media: ## Optional: recapture live battle, Grafana, screenshots, GIF and video (needs lab)
	$(PYTHON) scripts/capture_demo.py

demo-media-offline: ## Refresh dashboard PNG/GIF/MP4 from committed evidence (no cluster)
	$(PYTHON) scripts/capture_demo.py --offline

benchmarks: ## Regenerate committed offline RL and detector benchmark evidence
	$(PYTHON) -m rl.cli benchmark
	$(PYTHON) -m defender.cli benchmark

experimental-validation: ## Run 10 paired live Defender-vs-observe trials (needs lab)
	$(PYTHON) scripts/experimental_validation.py run --trials 10

experimental-holdout: ## Collect 30 held-out normal samples with the frozen detector
	$(PYTHON) scripts/experimental_validation.py holdout --samples 30

experimental-summary: ## Recompute v1.1 validation summary from committed records
	$(PYTHON) scripts/experimental_validation.py summary

cluster: ## Create the local Kind cluster and namespaces
	chmod +x scripts/*.sh
	kind get clusters | grep -qx $(CLUSTER) || kind create cluster --name $(CLUSTER) --config infra/kind-config.yaml
	$(KUBECTL) apply -f infra/k8s/namespaces.yaml

deploy: ## Build images, load into Kind, deploy app + observability
	chmod +x scripts/*.sh
	./scripts/build-and-load.sh
	$(KUBECTL) apply -k infra/k8s/observability
	$(KUBECTL) apply -k infra/k8s/overlays/test
	$(KUBECTL) apply -k infra/k8s/overlays/prod
	$(KUBECTL) -n shop-test rollout status deploy/user-service --timeout=240s
	$(KUBECTL) -n shop-test rollout status deploy/order-service --timeout=240s
	$(KUBECTL) -n monitoring rollout status deploy/grafana --timeout=240s

status: ## Show all pods in the three namespaces
	$(KUBECTL) get pods -n shop-test -o wide
	$(KUBECTL) get pods -n shop-prod -o wide
	$(KUBECTL) get pods -n monitoring -o wide

smoke: ## Port-forward order-service and smoke test it
	chmod +x scripts/*.sh
	./scripts/smoke-test.sh

dashboard: ## Open Grafana at http://localhost:3000 (admin/admin)
	$(KUBECTL) -n monitoring port-forward svc/grafana 3000:3000

metrics: ## Open Prometheus at http://localhost:9090
	$(KUBECTL) -n monitoring port-forward svc/prometheus 9090:9090

logs: ## Open Loki at http://localhost:3100
	$(KUBECTL) -n monitoring port-forward svc/loki 3100:3100

dev-local: ## Run all services with Python only (no Docker, no Kubernetes)
	python scripts/run_local.py

dev-up: ## Fast local dev without Kubernetes (docker compose)
	docker compose up -d --build

dev-down: ## Tear down the docker compose stack
	docker compose down -v

baseline: ## Phase 3: collect a normal-traffic baseline (30s windows)
	$(PYTHON) -m defender.cli baseline --samples 40 --interval 3 --window 30s

train: ## Phase 3: train the Isolation Forest from ml/baseline.csv
	$(PYTHON) -m defender.cli train

detect: ## Phase 3: score current traffic against the trained model
	$(PYTHON) -m defender.cli detect

defender-guard: ## Phase 3: print the defender's hard action allowlist
	$(PYTHON) -m defender.cli guard

defend: ## Phase 3: full detect -> diagnose -> act -> verify loop
	$(PYTHON) -m defender.cli run --act

chaos-install: ## Phase 2: install Chaos Mesh (Python allowlist gates targets)
	helm upgrade --install chaos-mesh chaos-mesh/chaos-mesh --version 2.8.8 --namespace chaos-mesh --create-namespace --set clusterScoped=true --set controllerManager.hostNetwork=false --set controllerManager.replicaCount=1 --set chaosDaemon.runtime=containerd --set chaosDaemon.socketPath=/run/containerd/containerd.sock --set dashboard.create=false --wait --timeout 10m

chaos-list: ## Phase 2: list the seven attacks
	$(PYTHON) -m attacker.cli list

chaos-status: ## Phase 2: show active chaos objects and pod phases
	$(PYTHON) -m attacker.cli status

chaos-clean: ## Phase 2: force-delete all chaosarena-labelled chaos objects
	$(PYTHON) -m attacker.cli cleanup

attack: ## Phase 2: run one allowlisted attack (ATTACK,TARGET,DURATION)
	$(PYTHON) -m attacker.cli attack $(ATTACK) --target $(TARGET) --duration $(DURATION)

battle: ## Phase 4: run a full attack -> defend -> recover battle and gate
	$(PYTHON) -m controller.cli evaluate --attack $(ATTACK) --target $(TARGET) --duration $(DURATION) --threshold $(THRESHOLD)

gate: ## Phase 4: show the last recorded gate decision
	$(PYTHON) -m controller.cli last

gate-api: ## Phase 4: serve /gate/evaluate at http://127.0.0.1:8080
	$(PYTHON) -m uvicorn controller.api:app --host 127.0.0.1 --port 8080

ui-install: ## Phase 7: install locked dashboard dependencies
	cd dashboard && npm ci

ui-build: ## Phase 7: build the React dashboard into dashboard/dist
	cd dashboard && npm run build

ui-dev: ## Phase 7: serve the dashboard at http://127.0.0.1:5173
	cd dashboard && npm run dev

rl-guard: ## Phase 8: print the RL attacker's allowlist and safety rules
	$(PYTHON) -m rl.cli guard

rl-train: ## Phase 8: train the Q table in the free simulator (no cluster)
	$(PYTHON) -m rl.cli train --episodes 200 --seed 7

rl-policy: ## Phase 8: show the learned policy
	$(PYTHON) -m rl.cli policy

rl-real-dry: ## Phase 8: print the real battle command without running it
	$(PYTHON) -m rl.cli real --dry-run

rl-real: ## Phase 8: run one real RL battle through controller.cli
	$(PYTHON) -m rl.cli real --episodes 1 --duration 10 --settle 20 --threshold 0

report: ## Phase 5: write a Markdown incident report (offline template)
	$(PYTHON) -m reporter.cli report --backend template

report-groq: ## Phase 5: report with Groq's FREE tier (needs GROQ_API_KEY)
	$(PYTHON) -m reporter.cli report --backend groq

ci-guard: ## Phase 6: print the free CI gate's safety rules
	$(PYTHON) -m ci.gate guard

ci-selftest: ## Phase 6: prove a bad battle is BLOCKed by the gate
	$(PYTHON) -m ci.gate check --evidence ci/fixtures/failing_battle.json --expect BLOCK

ci-check: ## Phase 6: enforce the committed battle (must PROMOTE)
	$(PYTHON) -m ci.gate check --evidence ml/last_battle.json --expect PROMOTE

clean: ## Delete the local Kind cluster
	kind delete cluster --name $(CLUSTER)
