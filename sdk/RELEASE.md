# Release Process

## Versioning

Both SDKs follow [Semantic Versioning](https://semver.org/) and are
released together under the same version number (currently **1.0.0**),
even though they publish to separate registries (PyPI, npm) under
separate tags. Keeping them in lockstep avoids a confusing "which
Python version works with which JS version" matrix — any 1.x Python
release is compatible with any 1.x JS release, since they implement the
same wire contract (`sdk/shared/API_CONTRACT.md`).

- **Major** (`2.0.0`): breaking changes to `track()`'s public signature,
  `TrackResult`'s shape, an instrumentor's public API, or the wire
  contract itself.
- **Minor** (`1.1.0`): new providers, new framework integrations, new
  configuration options — additive, backward compatible.
- **Patch** (`1.0.1`): bug fixes, documentation, internal refactors with
  no public API change.

## Version compatibility matrix

| SDK version | Python | Node.js | EP-16 API |
|---|---|---|---|
| 1.x | 3.9+ | 18+ | v1 (`/v1/ingest/usage`) |

## Deprecation policy

A public API scheduled for removal is marked deprecated (docstring/
`@deprecated`-style comment, and a runtime warning where practical) for
at least one minor release before removal in the next major release.
Deprecations are called out explicitly in `CHANGELOG.md`.

## Release checklist

1. Update `CHANGELOG.md` with the new version's changes.
2. Bump the version in **both**:
   - `sdk/python/pyproject.toml` (`[project].version`) and
     `sdk/python/costorah/version.py` (`__version__`) — these must match;
     `tests/test_config.py`-adjacent smoke checks don't currently enforce
     this automatically, so this is a manual step to double-check.
   - `sdk/javascript/package.json` (`version`) and
     `sdk/javascript/src/version.ts` (`VERSION`).
3. Run the full verification suite for both SDKs locally (see
   `sdk/docs/PERFORMANCE.md` and each SDK's CI job in
   `.github/workflows/ci.yml` for exactly what "full verification" means
   — lint, type check, tests, build).
4. Commit the version bump.
5. Tag and push:
   - `git tag sdk-python-v1.0.0 && git push origin sdk-python-v1.0.0`
   - `git tag sdk-js-v1.0.0 && git push origin sdk-js-v1.0.0`
6. Each tag triggers `.github/workflows/publish-sdks.yml`'s matching job,
   which re-verifies (lint/typecheck/test/build) before publishing to
   PyPI (via [Trusted Publishing](https://docs.pypi.org/trusted-publishers/) —
   no long-lived PyPI token stored in the repo) or npm (via an
   `NPM_TOKEN` repository secret).
7. Verify the published packages:
   - `pip install costorah==1.0.0`
   - `npm install @costorah/sdk@1.0.0`
8. Create a GitHub Release from the tag, linking to the relevant
   `CHANGELOG.md` section.

## Publishing prerequisites (one-time setup, not part of this Engineering
Package)

- A PyPI project named `costorah` configured for Trusted Publishing from
  this repository's `publish-sdks.yml` workflow.
- An npm organization/token with publish access to `@costorah/sdk`,
  stored as the `NPM_TOKEN` repository secret.
- Both are infrastructure/account-setup steps outside this repository's
  control — the workflow is ready to publish the moment they exist, but
  actually creating those PyPI/npm project registrations is an action
  for a human with the relevant account access, not something this
  Engineering Package can do on its own.
