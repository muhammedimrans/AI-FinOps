"""
`costorah` CLI (EP-18.4) — helps developers configure and verify a
COSTORAH integration from the command line.

    costorah init      # detect environment, print next steps
    costorah doctor     # validate SDK, config, connectivity, auth
    costorah health      # live health snapshot from a real client
    costorah version     # installed SDK version
    costorah config      # print resolved configuration (secrets masked)

Every subcommand is implemented as a small, independently testable
function (`run_*`) that the `main()` entry point wires up to argparse and
stdout — this keeps the actual logic decoupled from CLI parsing/printing,
so it's testable without spawning a subprocess.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import importlib.util
import json
import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from costorah.integrations._common import check_min_version
from costorah.version import __version__

PROVIDER_PACKAGES: dict[str, str] = {
    "openai": "openai",
    "anthropic": "anthropic",
    "google-genai": "google.genai",
    "mistralai": "mistralai",
    "cohere": "cohere",
    "boto3 (bedrock)": "boto3",
}

FRAMEWORK_PACKAGES: dict[str, str] = {
    "fastapi": "fastapi",
    "flask": "flask",
    "django": "django",
    "starlette": "starlette",
    "celery": "celery",
}

# Distribution name on PyPI, when it differs from the importable module
# name above (e.g. `pip install fastapi` -> `import fastapi`, same name;
# but `importlib.metadata.version()` needs the *distribution* name,
# which for these five happens to match the module name exactly — kept
# as an explicit map rather than reusing FRAMEWORK_PACKAGES's values
# so a future framework with a differing module/distribution name
# doesn't silently break version detection).
FRAMEWORK_DISTRIBUTION_NAMES: dict[str, str] = {
    "fastapi": "fastapi",
    "flask": "flask",
    "django": "django",
    "starlette": "starlette",
    "celery": "celery",
}

# See sdk/docs/FRAMEWORK_INTEGRATIONS.md's compatibility matrix for the
# rationale behind each floor.
MIN_FRAMEWORK_VERSIONS: dict[str, tuple[int, ...]] = {
    "fastapi": (0, 100),
    "flask": (2, 0),
    "django": (4, 0),
    "starlette": (0, 27),
    "celery": (5, 3),
}


def _is_installed(module_name: str) -> bool:
    try:
        return importlib.util.find_spec(module_name) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


def _detect(packages: dict[str, str]) -> dict[str, bool]:
    return {label: _is_installed(module) for label, module in packages.items()}


def _framework_version_warning(label: str) -> str | None:
    """None if `label` isn't installed, isn't in the min-version table,
    or is at/above the floor; otherwise a human-readable warning —
    never raises, matching every integration's "unsupported version is
    a graceful degrade, not a crash" policy."""
    distribution = FRAMEWORK_DISTRIBUTION_NAMES.get(label)
    minimum = MIN_FRAMEWORK_VERSIONS.get(label)
    if distribution is None or minimum is None:
        return None
    try:
        installed_version = importlib.metadata.version(distribution)
    except importlib.metadata.PackageNotFoundError:
        return None
    return check_min_version(installed_version, minimum, framework_name=label)


def _mask_api_key(api_key: str | None) -> str:
    if not api_key:
        return "<not set>"
    if len(api_key) <= 18:
        return "***"
    return f"{api_key[:14]}...{api_key[-4:]}"


# ── version ──────────────────────────────────────────────────────────────


def run_version() -> str:
    return f"costorah {__version__}"


# ── config ───────────────────────────────────────────────────────────────


def run_config(env: Mapping[str, str] | None = None) -> dict[str, Any]:
    env = env if env is not None else os.environ
    api_key = env.get("COSTORAH_API_KEY")
    return {
        "api_key": _mask_api_key(api_key),
        "api_key_set": bool(api_key),
        "endpoint": env.get("COSTORAH_ENDPOINT", "https://api.costorah.com"),
        "sdk_version": __version__,
    }


# ── init ─────────────────────────────────────────────────────────────────


@dataclass
class InitReport:
    api_key_configured: bool
    detected_frameworks: list[str] = field(default_factory=list)
    detected_providers: list[str] = field(default_factory=list)
    next_steps: list[str] = field(default_factory=list)


def run_init(env: Mapping[str, str] | None = None) -> InitReport:
    env = env if env is not None else os.environ
    api_key_configured = bool(env.get("COSTORAH_API_KEY"))
    frameworks = [name for name, present in _detect(FRAMEWORK_PACKAGES).items() if present]
    providers = [name for name, present in _detect(PROVIDER_PACKAGES).items() if present]

    steps: list[str] = []
    if not api_key_configured:
        steps.append(
            "Set COSTORAH_API_KEY (Organization API Key from the COSTORAH dashboard, "
            "prefixed costorah_live_...)."
        )
    if providers:
        example = providers[0].split(" ")[0].replace("-", "_")
        steps.append(
            f"Detected {', '.join(providers)} installed — instrument with e.g. "
            f"`from costorah.instrumentation import OpenAIInstrumentor` "
            f"(see sdk/docs/AUTOMATIC_INSTRUMENTATION.md for {example}'s instrumentor name)."
        )
    else:
        steps.append(
            "No supported AI provider SDK detected yet — install one (openai, anthropic, ...) "
            "to use automatic instrumentation, or call client.track() manually."
        )
    if "fastapi" in frameworks or "starlette" in frameworks:
        steps.append(
            "FastAPI/Starlette detected — add "
            "`app.add_middleware(CostorahMiddleware)` "
            "(from costorah.integrations.fastapi) for automatic request context."
        )
    steps.append("Run `costorah doctor` to verify the integration end-to-end.")

    return InitReport(
        api_key_configured=api_key_configured,
        detected_frameworks=frameworks,
        detected_providers=providers,
        next_steps=steps,
    )


# ── doctor ───────────────────────────────────────────────────────────────


@dataclass
class DoctorCheck:
    name: str
    ok: bool
    detail: str


@dataclass
class DoctorReport:
    checks: list[DoctorCheck]

    @property
    def all_ok(self) -> bool:
        return all(c.ok for c in self.checks)


def run_doctor(env: Mapping[str, str] | None = None, *, timeout: float = 10.0) -> DoctorReport:
    """Validates SDK import, configuration, connectivity, authentication,
    framework detection, and provider detection. Connectivity/auth are
    verified with a single real (best-effort) `track()` call — a
    `costorah_doctor_check` no-op event, not a fabricated success."""
    env = env if env is not None else os.environ
    checks: list[DoctorCheck] = []

    checks.append(DoctorCheck("SDK import", True, f"costorah {__version__}"))

    api_key = env.get("COSTORAH_API_KEY")
    key_ok = bool(api_key and api_key.startswith("costorah_live_"))
    checks.append(
        DoctorCheck(
            "Configuration",
            key_ok,
            "COSTORAH_API_KEY is set and well-formed"
            if key_ok
            else "COSTORAH_API_KEY is missing or doesn't start with 'costorah_live_'",
        )
    )

    if key_ok and api_key is not None:
        checks.extend(_check_connectivity_and_auth(api_key, env, timeout))
    else:
        checks.append(DoctorCheck("Connectivity", False, "skipped — fix configuration first"))
        checks.append(DoctorCheck("Authentication", False, "skipped — fix configuration first"))

    frameworks = _detect(FRAMEWORK_PACKAGES)
    found_frameworks = [name for name, present in frameworks.items() if present]
    checks.append(
        DoctorCheck(
            "Framework detection",
            True,
            f"detected: {', '.join(found_frameworks)}" if found_frameworks else "none detected",
        )
    )
    # Below-minimum versions are surfaced as their own advisory check
    # (not folded into "ok=False" above) — an old-but-working framework
    # version shouldn't flip `doctor`'s exit code, matching every
    # integration's "unsupported version is a graceful degrade, not a
    # hard failure" policy.
    for name in found_frameworks:
        warning = _framework_version_warning(name)
        if warning is not None:
            checks.append(DoctorCheck("Framework version compatibility", True, warning))

    providers = _detect(PROVIDER_PACKAGES)
    found_providers = [name for name, present in providers.items() if present]
    checks.append(
        DoctorCheck(
            "Provider detection",
            True,
            f"detected: {', '.join(found_providers)}" if found_providers else "none detected",
        )
    )

    return DoctorReport(checks=checks)


def _check_connectivity_and_auth(
    api_key: str, env: Mapping[str, str], timeout: float
) -> list[DoctorCheck]:
    from costorah.client import Costorah
    from costorah.exceptions import CostorahError

    endpoint = env.get("COSTORAH_ENDPOINT", "https://api.costorah.com")
    try:
        client = Costorah(api_key=api_key, endpoint=endpoint)
    except CostorahError as exc:
        return [
            DoctorCheck("Connectivity", False, f"client construction failed: {exc}"),
            DoctorCheck("Authentication", False, "skipped — client construction failed"),
        ]

    try:
        client.track(
            provider="openai",
            model="costorah-doctor-check",
            cost=0.0,
            metadata={"costorah_doctor": True},
        )
        client.flush(timeout=timeout)
        stats = client.queue_stats()
    finally:
        client.shutdown(timeout=timeout)

    if stats["sent_total"] > 0:
        return [
            DoctorCheck("Connectivity", True, f"reached {endpoint}"),
            DoctorCheck("Authentication", True, "API key accepted"),
        ]
    # retry_count > 0 means the failure was classified as transient (a
    # network error, or a 5xx/429/408 response) and is still being
    # retried — connectivity/auth are NOT confirmed either way. Only
    # retry_count == 0 with a recorded failure means a permanent
    # rejection (400/401/403/404) — a real, terminal response, so the
    # endpoint *was* reachable, it just rejected the request.
    if stats["retry_count"] == 0 and stats["failed_total"] > 0:
        return [
            DoctorCheck("Connectivity", True, f"reached {endpoint}"),
            DoctorCheck(
                "Authentication",
                False,
                "the endpoint rejected the check event — verify the API key has "
                "usage:write scope and isn't expired/suspended",
            ),
        ]
    return [
        DoctorCheck(
            "Connectivity",
            False,
            f"no confirmed response from {endpoint} within {timeout}s "
            "(network unreachable, DNS failure, or the endpoint is down)",
        ),
        DoctorCheck("Authentication", False, "skipped — connectivity could not be confirmed"),
    ]


# ── health ───────────────────────────────────────────────────────────────


def run_health(env: Mapping[str, str] | None = None, *, timeout: float = 5.0) -> dict[str, Any]:
    """Constructs a real client from the environment, gives the
    background worker a moment to start, and reports its live
    `health()`/`queue_stats()` snapshot."""
    env = env if env is not None else os.environ
    api_key = env.get("COSTORAH_API_KEY")
    if not api_key:
        return {"error": "COSTORAH_API_KEY is not set"}

    from costorah.client import Costorah
    from costorah.exceptions import CostorahError

    endpoint = env.get("COSTORAH_ENDPOINT", "https://api.costorah.com")
    try:
        client = Costorah(api_key=api_key, endpoint=endpoint)
    except CostorahError as exc:
        return {"error": str(exc)}

    try:
        health = client.health()
        stats = client.queue_stats()
    finally:
        client.shutdown(timeout=timeout)

    return {**health, "queue_stats": stats}


# ── argparse wiring ──────────────────────────────────────────────────────


def _print_doctor_report(report: DoctorReport) -> None:
    for check in report.checks:
        symbol = "✓" if check.ok else "✗"
        print(f"  {symbol} {check.name}: {check.detail}")
    print()
    print("All checks passed." if report.all_ok else "Some checks failed — see above.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="costorah", description="COSTORAH SDK CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("version", help="print the installed SDK version")
    subparsers.add_parser("config", help="print resolved configuration (secrets masked)")
    subparsers.add_parser("init", help="detect your environment and print setup steps")

    doctor_parser = subparsers.add_parser(
        "doctor", help="validate SDK, configuration, connectivity, and authentication"
    )
    doctor_parser.add_argument("--timeout", type=float, default=10.0)

    health_parser = subparsers.add_parser(
        "health", help="print a live health snapshot from a real client"
    )
    health_parser.add_argument("--timeout", type=float, default=5.0)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "version":
        print(run_version())
        return 0

    if args.command == "config":
        print(json.dumps(run_config(), indent=2))
        return 0

    if args.command == "init":
        init_report = run_init()
        print(f"API key configured: {'yes' if init_report.api_key_configured else 'no'}")
        print(f"Detected frameworks: {', '.join(init_report.detected_frameworks) or 'none'}")
        print(f"Detected AI providers: {', '.join(init_report.detected_providers) or 'none'}")
        print("\nNext steps:")
        for step in init_report.next_steps:
            print(f"  - {step}")
        return 0

    if args.command == "doctor":
        doctor_report = run_doctor(timeout=args.timeout)
        _print_doctor_report(doctor_report)
        return 0 if doctor_report.all_ok else 1

    if args.command == "health":
        result = run_health(timeout=args.timeout)
        print(json.dumps(result, indent=2))
        return 1 if "error" in result else 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
