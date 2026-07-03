# Docker Guide

## Image

`packaging/docker/Dockerfile` is a multi-stage build: a full `python:3.12-slim`
stage compiles a wheel (`python -m build --wheel`), and the runtime stage
installs only that wheel into a fresh `python:3.12-slim` image, so no build
toolchain ships in the final image. The process runs as a non-root user
(`costorah`), exposes port `9091`, and defines a `HEALTHCHECK` that calls
`costorah-agent health` (exits non-zero if the agent reports unhealthy).

Build it:

```bash
cd /path/to/monitoring-agent
docker build -f packaging/docker/Dockerfile -t costorah-agent:latest .
```

> This image could not be build-tested in the development sandbox used for
> EP-17 (no Docker daemon available there — `docker build` failed with
> `dial unix /var/run/docker.sock: connect: no such file or directory`).
> The Dockerfile was reviewed by inspection and follows the same pattern as
> the backend's own Dockerfile; build it in an environment with Docker
> available before relying on it in production, and see
> `TROUBLESHOOTING.md` if the build fails.

## Docker Compose (standalone)

```bash
cd packaging/docker
cp ../../config.example.yaml ./config.yaml   # edit if needed — see below for the API key
cat > .env <<'EOF'
COSTORAH_AGENT_API_KEY=costorah_live_xxxxxxxxxxxx
EOF
docker compose up -d
curl http://localhost:9091/health
```

`docker-compose.yml` mounts `config.yaml` read-only and injects the API key
via `COSTORAH_AGENT_ORGANIZATION__API_KEY` from the environment (sourced
from `.env`) rather than baking it into the mounted file — keep `.env` out
of version control (it isn't a config file the image needs baked in).

The offline retry queue (SQLite) persists in a named volume
(`costorah-agent-data`), so it survives `docker compose restart` and
`docker compose up` after a `down` (as long as you don't also pass `-v`).

## Running standalone (no Compose)

```bash
docker run -d \
  --name costorah-agent \
  -p 127.0.0.1:9091:9091 \
  -e COSTORAH_AGENT_ORGANIZATION__API_KEY=costorah_live_xxxxxxxxxxxx \
  -v costorah-agent-data:/var/lib/costorah-agent \
  -v $(pwd)/config.yaml:/etc/costorah-agent/config.yaml:ro \
  costorah-agent:latest
```

## Verifying a running container

```bash
docker exec costorah-agent costorah-agent health
docker logs -f costorah-agent
```

## Common issues

See `TROUBLESHOOTING.md` for the full list; the most common Docker-specific
one is forgetting to mount `config.yaml` (the image ships only
`config.yaml.example` at `/etc/costorah-agent/config.yaml.example`, not a
live config) or forgetting the API key environment variable, both of which
surface as `AgentAuthenticationError` on container start (visible via
`docker logs`).
