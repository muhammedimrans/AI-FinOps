# Deployment Runbook

## Production deployment order

Every deployment must follow this sequence. Steps are not interchangeable.

```
1. alembic upgrade head      # apply pending schema migrations
2. start uvicorn             # application seeds demo data on first boot
```

### Why this order matters

The application seeds demo data automatically on every startup
(`AppContainer.create()` → `seed_startup_data()`). If the schema does not
exist yet, the seed detects `UndefinedTableError`, logs
`seed_skipped_database_not_initialized`, and allows the application to
continue. The seed will run successfully on the next startup after migrations
have been applied.

Running the application before migrations means no demo data will be created
until the service is restarted after migrations complete.

---

## Step 1 — Apply migrations

**Render (recommended):** add a Pre-Deploy Command in the service settings:

```
cd backend && alembic upgrade head
```

Render runs this command before swapping traffic to the new instance, so the
schema is always up-to-date before the application starts.

**Manual (SSH / Render Shell):**

```bash
cd backend
alembic upgrade head
```

**Local development:**

```bash
cd backend
alembic upgrade head
```

---

## Step 2 — Start the application

Render starts the application automatically after the pre-deploy command
succeeds. The uvicorn start command (set in Render's Start Command):

```
cd backend && uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

On first boot after a fresh migration, `seed_startup_data()` creates:

| Entity       | Value                                        |
|--------------|----------------------------------------------|
| Organization | Zero Protocol (slug: `zero-protocol`)        |
| User         | `admin@0protocol.net` / `Admin@123`          |
| Membership   | `admin@0protocol.net` → Zero Protocol (OWNER)|
| Project      | AI FinOps Demo (PRODUCTION)                  |

On every subsequent boot the seed is skipped after a single `SELECT` (fast path).

---

## Step 3 — Verify (optional)

Check the health endpoint:

```bash
curl https://ai-finops-bqf3.onrender.com/health
```

Expected response:

```json
{"status": "healthy", ...}
```

Then confirm login works:

```bash
curl -s -X POST https://ai-finops-bqf3.onrender.com/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@0protocol.net","password":"Admin@123"}' | jq .
```

---

## Manual seed (without a running server)

If you need to seed outside of application startup (e.g. before first deploy
or after a database reset):

```bash
cd backend
DATABASE_URL="postgresql://..." python -m scripts.seed_demo
```

The script is idempotent — running it multiple times is safe.

---

## Rollback

Alembic supports rolling back the most recent migration:

```bash
cd backend
alembic downgrade -1
```

To roll back to a specific revision:

```bash
alembic downgrade <revision-id>
```

Always redeploy the previous application version alongside a downgrade.
