# Contributing to AI FinOps

Thank you for contributing. This document outlines the process.

## Getting Started

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Follow the [Development Guide](DEVELOPMENT.md)
4. Make your changes
5. Run `make ci` — all checks must pass
6. Submit a pull request

## Pull Request Requirements

- Fill in the PR template completely
- All CI checks must pass
- Code must be type-safe (mypy strict / TypeScript strict)
- Tests required for any new behavior
- No secrets or credentials in commits

## Commit Messages

Use conventional commit format:

```
type(scope): short description

Optional body explaining WHY (not WHAT).
```

Types: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`, `ci`

Examples:

```
feat(api): add /health endpoint
fix(workers): handle retry on rate limit
docs(readme): update quick start steps
```

## Code of Conduct

See [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

## Questions

Open a GitHub Discussion or an issue labeled `question`.
