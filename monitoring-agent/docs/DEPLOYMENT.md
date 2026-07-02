# Deployment Guide

The agent is designed to run **under a process supervisor** rather than as
its own daemon — systemd, Docker/Kubernetes, or a Windows Scheduled
Task/Service already solve respawn-on-crash, log capture, and
start-on-boot better than a hand-rolled daemon would. This guide covers
each supported target. For Docker/Kubernetes specifically, see
`DOCKER.md` and `KUBERNETES.md`.

## Linux (systemd)

```bash
cd packaging/linux
sudo ./install.sh
```

This installs `costorah-agent` into a dedicated virtualenv under
`/opt/costorah-agent`, creates a restricted system user
(`costorah-agent`, no login shell, no home directory), lays down
`/etc/costorah-agent`, `/var/lib/costorah-agent`, `/var/log/costorah-agent`
with correct ownership, and installs (but does not start) the systemd unit
at `packaging/linux/costorah-agent.service`.

```bash
sudo vim /etc/costorah-agent/config.yaml   # set organization.api_key, or use the env var below
sudo systemctl enable --now costorah-agent
sudo systemctl status costorah-agent
curl http://127.0.0.1:9091/health
```

The unit is hardened: `NoNewPrivileges=true`, `ProtectSystem=strict`,
`ProtectHome=true`, dedicated `RuntimeDirectory`/`StateDirectory`/
`LogsDirectory`, and `Restart=on-failure`.

To supply the API key without writing it to `config.yaml`:

```bash
sudo systemctl edit costorah-agent
```
```ini
[Service]
Environment=COSTORAH_AGENT_ORGANIZATION__API_KEY=costorah_live_xxxxxxxxxxxx
```

## Windows

```powershell
cd packaging\windows
powershell -ExecutionPolicy Bypass -File install.ps1
```

Installs into a venv under `%ProgramData%\costorah-agent`, writes a default
config, and registers a Scheduled Task (`CostorahAgent`) that starts the
agent at boot with an automatic-restart policy — a lightweight always-on
alternative that doesn't require a separate service wrapper.

```powershell
notepad "$env:ProgramData\costorah-agent\config\config.yaml"   # set organization.api_key
Start-ScheduledTask -TaskName CostorahAgent
Invoke-WebRequest http://127.0.0.1:9091/health
```

For fleets that need native Windows Service semantics (central
restart-on-crash policy, Service Manager integration), wrap
`costorah-agent.exe start --config ...` with
[NSSM](https://nssm.cc/) instead of the Scheduled Task — this is the
supported production path when a Scheduled Task isn't sufficient, though
EP-17 doesn't automate that wrapping.

## Manual / development (foreground)

```bash
pip install -e .
cp config.example.yaml config.yaml   # edit organization.api_key
costorah-agent start --config config.yaml
```

`Ctrl-C` triggers the same graceful-shutdown path as SIGTERM in production.

### Background mode (POSIX only, manual/dev use)

```bash
costorah-agent start --detach --config config.yaml
costorah-agent status
costorah-agent stop
```

This is a basic `subprocess.Popen(start_new_session=True)` background mode
with PID-file tracking — not a true daemon, and not recommended for
production (use systemd/Docker/Kubernetes instead, which supervise restart
behavior that a bare detached process doesn't get).

## Health checks for any deployment target

```bash
costorah-agent health                    # exits non-zero if unhealthy — CI/deploy-gate friendly
curl http://127.0.0.1:9091/health        # raw JSON
curl http://127.0.0.1:9091/metrics       # Prometheus text exposition
```

See `CONFIGURATION.md` for the full `/health` response shape and status
semantics (`healthy` vs `degraded`).

## Auto-update

Not implemented in EP-17 by design (explicitly out of scope per the
ticket). The plugin/collector architecture and the `costorah-agent
version` command exist specifically so a future updater has a clean
integration point — see `ARCHITECTURE.md` and `TROUBLESHOOTING.md` for
the intended shape of that follow-up work.

## Resource targets

| Metric | Target | Where it's enforced/tested |
|---|---|---|
| Memory | < 100MB | `tests/performance/test_queue_throughput.py` (10,000-event queue-depth memory delta); Kubernetes `resources.limits.memory: 128Mi` |
| CPU | < 2% steady-state | Kubernetes `resources.limits.cpu: 200m`; see `TEST_COVERAGE` notes in the final report for what the CPU performance test actually measures (bounded absolute CPU time, not a sustained-load percentage) |
| Per-event overhead | < 10ms | Collection/delivery loops run on independent intervals so a slow provider poll never blocks delivery, and vice versa |
