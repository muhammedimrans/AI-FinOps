# Kubernetes Guide

## Why a Deployment, not a DaemonSet

The agent polls **account-level provider usage APIs** (OpenAI's org usage
endpoint, OpenRouter's key-info endpoint, etc.) — it is not watching
per-pod or per-node traffic. Running one instance per node (a DaemonSet)
would just poll the same provider account N times and produce duplicate
work for no benefit. `packaging/kubernetes/deployment.yaml` therefore runs
a single-replica `Deployment`.

Running multiple replicas would still be *safe* (never produce duplicate
*data*) because of EP-16's `(organization_id, request_id)` deduplication —
`deterministic_request_id()` (`collectors/_util.py`) makes re-polling an
overlapping time window naturally produce the same `request_id` — but it
would waste API calls against provider rate limits for no benefit, hence
`replicas: 1`.

## Deploying

```bash
kubectl create namespace costorah
kubectl -n costorah create secret generic costorah-agent-api-key \
    --from-literal=api-key=costorah_live_xxxxxxxxxxxxx
kubectl -n costorah apply -f packaging/kubernetes/deployment.yaml
```

The manifest defines, in order:

1. A `ConfigMap` (`costorah-agent-config`) holding `config.yaml`, mounted
   read-only at `/etc/costorah-agent/config.yaml`.
2. A `Deployment` (1 replica) that reads the API key from the
   `costorah-agent-api-key` Secret via
   `COSTORAH_AGENT_ORGANIZATION__API_KEY`, runs as a non-root user
   (`runAsUser: 1000`), and defines `livenessProbe`/`readinessProbe`
   against `GET /health`.
3. A `PersistentVolumeClaim` (`costorah-agent-data`, 1Gi, `ReadWriteOnce`)
   for the offline retry queue's SQLite file. **This is a
   `PersistentVolumeClaim`, not `emptyDir`, deliberately**: `emptyDir`
   doesn't survive pod rescheduling, which would silently break "never
   lose telemetry" during exactly the kind of cluster event (node
   failure, eviction) that might coincide with a COSTORAH outage — the
   scenario the offline queue exists for in the first place.
4. A `Service` exposing port `9091` in-cluster (for a `ServiceMonitor` or
   internal health checks — it is not exposed outside the cluster by this
   manifest).

## Resource requests/limits

```yaml
resources:
  requests: { cpu: 50m, memory: 64Mi }
  limits:   { cpu: 200m, memory: 128Mi }
```

Roughly targets the EP-17 spec's <100MB/<2% CPU footprint with headroom;
tune based on your actual `providers` enabled and `collection.interval_seconds`
(more providers polled more frequently means more concurrent HTTP calls,
though the agent's own memory/CPU floor is small — see
`tests/performance/test_queue_throughput.py` for what was actually
measured).

## Scraping metrics with Prometheus

The `Service` exposes `9091/metrics` in Prometheus text exposition format
(`GET /metrics`, rendered by `server/metrics.py`). Point a
`ServiceMonitor` (if you run the Prometheus Operator) or a static scrape
config at `costorah-agent.costorah.svc.cluster.local:9091/metrics`.

## Verifying

```bash
kubectl -n costorah get pods -l app=costorah-agent
kubectl -n costorah logs -l app=costorah-agent -f
kubectl -n costorah port-forward svc/costorah-agent 9091:9091
curl http://localhost:9091/health
```

## Rolling restart after a config change

The agent does not hot-reload `config.yaml` (see `CONFIGURATION.md`).
After editing the `ConfigMap`:

```bash
kubectl -n costorah rollout restart deployment costorah-agent
```
