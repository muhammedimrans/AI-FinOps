"""
costorah-agent CLI.

    costorah-agent start    [--config PATH] [--detach]
    costorah-agent stop     [--pid-file PATH]
    costorah-agent status   [--pid-file PATH]
    costorah-agent config   show|set-key [--config PATH]
    costorah-agent version
    costorah-agent health   [--host HOST] [--port PORT]

Process management uses a PID file rather than a true OS service/daemon —
this agent is designed to run *under* a supervisor (systemd, Docker,
Kubernetes, Windows Service wrapper; see packaging/) which already solves
respawn-on-crash, log capture, and start-on-boot far better than a
hand-rolled daemon would. `start --detach` provides a basic background
mode for manual/dev use on POSIX only (documented below); the supervised
deployments in packaging/ are the recommended production path.
"""

from __future__ import annotations

import asyncio
import json
import os
import signal
import subprocess
import sys
from pathlib import Path

import click
import httpx

from costorah_agent.agent import Agent, AgentAuthenticationError
from costorah_agent.config import load_config
from costorah_agent.logging_setup import configure_logging
from costorah_agent.security.key_store import KeyStore
from costorah_agent.server.app import run_server
from costorah_agent.version import __version__

_DEFAULT_PID_FILE = "costorah-agent.pid"


@click.group()
def cli() -> None:
    """COSTORAH Monitoring Agent."""


@cli.command()
@click.option("--config", "config_path", default="config.yaml", show_default=True)
@click.option("--detach", is_flag=True, help="Run in the background (POSIX only).")
@click.option("--pid-file", default=_DEFAULT_PID_FILE, show_default=True)
def start(config_path: str, detach: bool, pid_file: str) -> None:
    """Start the agent (collection + delivery loops + health/metrics server)."""
    if detach:
        _start_detached(config_path, pid_file)
        return

    Path(pid_file).write_text(str(os.getpid()))
    try:
        asyncio.run(_run_agent(config_path))
    finally:
        Path(pid_file).unlink(missing_ok=True)


def _start_detached(config_path: str, pid_file: str) -> None:
    if os.name != "posix":
        raise click.ClickException(
            "--detach is only supported on POSIX systems. On Windows, run "
            "under the Windows Service wrapper in packaging/windows/, or "
            "run `costorah-agent start` in the foreground under a "
            "supervisor of your choice."
        )
    proc = subprocess.Popen(  # noqa: S603 - fixed argv, no shell, no untrusted input
        [sys.executable, "-m", "costorah_agent", "start", "--config", config_path],
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    Path(pid_file).write_text(str(proc.pid))
    click.echo(f"costorah-agent started in background (pid {proc.pid})")


async def _run_agent(config_path: str) -> None:
    config = load_config(config_path)
    configure_logging(
        level=config.logging.level,
        log_file=config.logging.file,
        max_bytes=config.logging.max_bytes,
        backup_count=config.logging.backup_count,
    )
    try:
        agent = Agent(config)
    except AgentAuthenticationError as exc:
        raise click.ClickException(str(exc)) from exc

    await agent.start()
    runner = None
    if config.http_server.enabled:
        runner = await run_server(agent, host=config.http_server.host, port=config.http_server.port)

    try:
        await agent.run_forever()
    finally:
        if runner is not None:
            await runner.cleanup()


@cli.command()
@click.option("--pid-file", default=_DEFAULT_PID_FILE, show_default=True)
def stop(pid_file: str) -> None:
    """Stop a running agent started with `start --detach`."""
    path = Path(pid_file)
    if not path.exists():
        raise click.ClickException(f"No PID file at {pid_file} — is the agent running?")
    pid = int(path.read_text().strip())
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        click.echo("Process not found (already stopped); removing stale PID file.")
    path.unlink(missing_ok=True)
    click.echo(f"Sent stop signal to pid {pid}")


@cli.command()
@click.option("--pid-file", default=_DEFAULT_PID_FILE, show_default=True)
@click.option("--host", default="127.0.0.1", show_default=True)
@click.option("--port", default=9091, show_default=True)
def status(pid_file: str, host: str, port: int) -> None:
    """Report whether the agent process is running and healthy."""
    path = Path(pid_file)
    if not path.exists():
        click.echo("stopped (no PID file)")
        return
    pid = int(path.read_text().strip())
    if not _pid_alive(pid):
        click.echo(f"stopped (stale PID file for pid {pid})")
        return

    click.echo(f"running (pid {pid})")
    try:
        resp = httpx.get(f"http://{host}:{port}/health", timeout=3.0)
        click.echo(json.dumps(resp.json(), indent=2))
    except httpx.HTTPError as exc:
        click.echo(f"process alive but health endpoint unreachable: {exc}")


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except (ProcessLookupError, PermissionError):
        return os.name != "posix"  # best-effort on platforms without signal 0 semantics
    except OSError:
        return False
    return True


@cli.group()
def config() -> None:
    """Inspect or update agent configuration."""


@config.command("show")
@click.option("--config", "config_path", default="config.yaml", show_default=True)
def config_show(config_path: str) -> None:
    """Print the effective (merged) configuration as JSON. The API key is masked."""
    cfg = load_config(config_path)
    data = cfg.model_dump()
    if data.get("organization", {}).get("api_key"):
        key = data["organization"]["api_key"]
        masked = f"{key[:18]}...REDACTED" if len(key) > 18 else "***REDACTED***"
        data["organization"]["api_key"] = masked
    click.echo(json.dumps(data, indent=2, default=str))


@config.command("set-key")
@click.argument("api_key")
@click.option("--keystore-dir", default=".", show_default=True)
def config_set_key(api_key: str, keystore_dir: str) -> None:
    """Encrypt and store the organization API key at rest, instead of
    keeping it in plaintext config.yaml."""
    if not api_key.startswith("costorah_live_"):
        raise click.ClickException("API key must start with 'costorah_live_'")
    KeyStore(keystore_dir).store(api_key)
    click.echo("API key encrypted and stored. Remove organization.api_key from config.yaml.")


@cli.command()
def version() -> None:
    """Print the agent version."""
    click.echo(__version__)


@cli.command()
@click.option("--host", default="127.0.0.1", show_default=True)
@click.option("--port", default=9091, show_default=True)
def health(host: str, port: int) -> None:
    """Query the running agent's /health endpoint. Exits non-zero if unhealthy."""
    try:
        resp = httpx.get(f"http://{host}:{port}/health", timeout=3.0)
        body = resp.json()
    except httpx.HTTPError as exc:
        raise click.ClickException(f"Could not reach agent at {host}:{port}: {exc}") from exc

    click.echo(json.dumps(body, indent=2))
    if body.get("status") != "healthy":
        sys.exit(1)


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
