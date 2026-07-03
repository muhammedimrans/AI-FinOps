# COSTORAH Monitoring Agent — production image.
#
# Multi-stage build: compile the wheel in a full Python image, install it
# into a slim runtime image so the final image doesn't carry build tools.
# Runs as a non-root user; the queue DB and logs live in a mounted volume
# (see docker-compose.yml).

FROM python:3.12-slim AS build

WORKDIR /src
COPY pyproject.toml ./
COPY costorah_agent ./costorah_agent
RUN pip install --no-cache-dir build && python -m build --wheel

FROM python:3.12-slim AS runtime

RUN groupadd --system costorah && useradd --system --gid costorah --no-create-home costorah

COPY --from=build /src/dist/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl && rm -f /tmp/*.whl

RUN mkdir -p /etc/costorah-agent /var/lib/costorah-agent && \
    chown -R costorah:costorah /etc/costorah-agent /var/lib/costorah-agent

COPY config.example.yaml /etc/costorah-agent/config.yaml.example

USER costorah
WORKDIR /var/lib/costorah-agent

EXPOSE 9091

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD costorah-agent health || exit 1

ENTRYPOINT ["costorah-agent"]
CMD ["start", "--config", "/etc/costorah-agent/config.yaml"]
