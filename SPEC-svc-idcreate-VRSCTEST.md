# SPEC: svc-idcreate Deployment on BWD VRSCTEST Node

**Date:** 2026-04-29
**Updated:** 2026-05-15
**Status:** Active — v2 postgres migration
**Repo:** `BuildWithDreams/svc-idcreate`

---

## 1. Purpose

Deploy `svc-idcreate` (FastAPI identity creation service + background worker + PostgreSQL) on the BWD VRSCTEST node, accessible at `https://idcreate.vrsctest.buildwithdreams.com` with Let's Encrypt TLS.

The service:
- Exposes an external API (`/api/register`, `/api/registrations/*`, `/api/webhook/*`)
- Connects to the **VRSCTEST** verusd daemon via the `DAEMON_VERUSD_VRSC` slot + `NATIVE_COIN="VRSCTEST"`
- Runs a background worker that polls pending registrations and advances their state
- Uses **PostgreSQL** for durable concurrent data access (v2 — replaces SQLite)
- Provisioning adapter runs in **HTTP mode** (`PROVISIONING_ADAPTER_MODE=http`)

---

## 2. Architecture (v2)

```
Internet → Caddy (10.201.0.10:443) → idcreate.vrsctest.buildwithdreams.com
                                                 ↓
                                    reverse_proxy 10.200.0.14:5003
                                                 ↓
                         ┌──────────────────────┴──────────────────────┐
                         ↓                                              ↓
            idcreate-api (FastAPI)                        idcreate-provisioning (Node.js)
            10.200.0.14:5003                               10.200.0.14:5055
                         ↓                                              ↓
            idcreate-worker (polling)                svc-provisioning (scripts)
                         ↓
            PostgreSQL 16-alpine
            dev200_idcreate-postgres-1
            5432 (host: 127.0.0.1:5432)
                         ↓
            VRSCTEST verusd daemon (10.200.0.11:18843)
```

- **Docker network:** `net-vrsctest` (`10.200.0.0/24`)
- **Service IP:** `10.200.0.14`
- **Compose project:** `dev200_idcreate`
- **PostgreSQL:** `dev200_idcreate-postgres-1` (named volume: `dev200_idcreate_idcreate_postgres_data`)

---

## 3. Container Inventory (v2)

| Container | Service | IP | Ports |
|---|---|---|---|
| `dev200_idcreate-postgres-1` | PostgreSQL 16-alpine | auto | `5432` (host: `127.0.0.1:5432`) |
| `dev200_idcreate-provisioning-1` | Node.js provisioning scripts | auto | `5055` (host: `127.0.0.1:5055`) |
| `dev200_idcreate-api-1` | FastAPI | `10.200.0.14` | `5003` (host: `127.0.0.1:5003`) |
| `dev200_idcreate-worker-1` | Background state machine | auto | — (internal) |

---

## 4. Domain / DNS

- **Subdomain:** `idcreate.vrsctest.buildwithdreams.com`
- **DNS:** A record points to `135.181.136.105` (BWD server)
- **TLS:** Automatic via Caddy + Let's Encrypt (existing email: `hermesreport@verus.trading`)

---

## 5. Environment Variables

### Set by playbook 41 (RPC + service)

```
NATIVE_COIN="VRSCTEST"
HEALTH_RPC_DAEMON="verusd_vrsc"
verusd_vrsc_rpc_enabled="true"
verusd_vrsc_rpc_user="<from vrsctest.conf>"
verusd_vrsc_rpc_password="<from vrsctest.conf>"
verusd_vrsc_rpc_port="18843"
verusd_vrsc_rpc_host="10.200.0.11"
```

### New in v2 (provisioning adapter + postgres)

```
DATABASE_URL="postgresql://idcreate:<password>@postgres:5432/idcreate"
PROVISIONING_ADAPTER_MODE="http"
PROVISIONING_SERVICE_URL="http://127.0.0.1:5055"
PROVISIONING_HTTP_TIMEOUT_SECONDS="10"
PROVISIONING_RETRY_COUNT="1"
PROVISIONING_LOG_LEVEL="INFO"
```

### Required in .env (operator-managed)

```
REGISTRAR_API_KEYS=...       # API authentication key(s), comma-separated
PRIMARY_ADDRESS=...           # Must be an R-address
SOURCE_OF_FUNDS=...           # R-address, I-address, or friendly name@
DELIVER_ID_CONTROL_TOKEN=...  # Friendly name of the identity control token
PARENT=...                    # Parent currency, e.g. "bitcoins.vrsc"
FEE_OFFER=...                 # Identity registration fee offer
Z_ADDRESS=...                # Z-address (optional)
REFERRAL_ID=...               # Referral identity (optional)
```

---

## 6. Playbook Inventory

| # | Playbook | Purpose |
|---|---|---|
| `39` | `39-idcreate-clone.yml` | Clone repo (idempotent) |
| `40` | `40-idcreate-build.yml` | Build Docker image |
| `41` | `41-idcreate-deploy.yml` | Deploy full stack (postgres + provisioning + api + worker) |
| `42` | `42-idcreate-caddy-route.yml` | Add HTTPS route in Caddy (unchanged in v2) |
| `43` | `43-idcreate-add-api-key.yml` | Generate + persist `REGISTRAR_API_KEYS` (unchanged in v2) |
| `44` | `44-idcreate-source-of-funds.yml` | Set source of funds (unchanged in v2) |
| `45` | `45-idcreate-update.yml` | Pull + rebuild + restart (v2: postgres health wait) |
| `46` | `46-idcreate-allowed-parents.yml` | Configure allowed parent currencies (unchanged in v2) |
| `47` | `47-idcreate-restart.yml` | Restart to pick up .env changes (v2: postgres health wait) |

---

## 7. Provisioning Adapter

The provisioning adapter (`provisioning/engine.py`) is the core identity provisioning state machine. In v2 it runs in **HTTP mode** — it is packaged as a separate `provisioning` container that the API and worker call via HTTP.

```
api/worker → HTTP → provisioning:5055 → provisioning/engine.py → VRSCTEST daemon
```

Key env vars for provisioning adapter:
- `PROVISIONING_ADAPTER_MODE=http` — required, SQLite removed in v2
- `PROVISIONING_SERVICE_URL=http://127.0.0.1:5055` — internal HTTP endpoint
- `PROVISIONING_HTTP_TIMEOUT_SECONDS=10`
- `PROVISIONING_RETRY_COUNT=1`
- `PROVISIONING_LOG_LEVEL=INFO`

---

## 8. PostgreSQL

- **Image:** `postgres:16-alpine`
- **Version:** PostgreSQL 16
- **Database:** `idcreate`
- **User:** `idcreate`
- **Password:** auto-generated, stored in `.env` as `DATABASE_URL`
- **Data volume:** `dev200_idcreate_idcreate_postgres_data` (Docker named volume)
- **Port:** `5432` published to `127.0.0.1:5432` (host-only, not exposed externally)
- **Health check:** `pg_isready -U idcreate -d idcreate`

### Why PostgreSQL instead of SQLite

SQLite locks the database file on writes. The api and worker containers both write to the DB concurrently, causing `sqlite3.OperationalError: database is locked` errors. PostgreSQL handles concurrent access correctly and supports the connection pooling used by SQLAlchemy in the v2 codebase.

### Migration

The app handles schema migrations on startup via Alembic or equivalent (handled in `db.py` / app startup). On a fresh v2 deploy the schema is created automatically.

---

## 9. Deployment Order

```
39-idcreate-clone.yml      # Clone repo
40-idcreate-build.yml      # Build Docker image
41-idcreate-deploy.yml     # Deploy full stack (postgres + provisioning + api + worker)
42-idcreate-caddy-route.yml # Add HTTPS route (already done — idempotent re-run OK)
(43-idcreate-add-api-key.yml) # If API keys not yet set
```

On update (new commits):
```
45-idcreate-update.yml     # Pull + rebuild + restart with postgres health wait
```

After editing .env:
```
47-idcreate-restart.yml     # Restart containers (includes postgres health wait)
```

---

## 10. Data Persistence

| Data | Storage | Notes |
|---|---|---|
| PostgreSQL data | Docker named volume `dev200_idcreate_idcreate_postgres_data` | Survives container restart; backup with `pg_dump` |
| App data (SQLite fallback) | Docker named volume `dev200_idcreate_idcreate_data` | Not used in v2 (postgres) |
| Source of funds / Z-address / Referral ID | `.env` | Operator-managed |
| API keys | `.env` (`REGISTRAR_API_KEYS`) | Operator-managed |

---

## 11. Key Differences: v1 (SQLite) → v2 (PostgreSQL)

| Aspect | v1 | v2 |
|---|---|---|
| Database | SQLite (file-based, locking) | PostgreSQL 16-alpine |
| DB connection | `REGISTRAR_DB_PATH=/data/registrar.db` | `DATABASE_URL=postgresql://...` |
| Provisioning | Not deployed | HTTP adapter via `provisioning:5055` |
| Containers | `api` + `worker` | `postgres` + `provisioning` + `api` + `worker` |
| Concurrent writes | Fails with `database is locked` | Works |
| Migration | N/A | Auto on app startup |

---

## 12. Acceptance Criteria

- [x] PostgreSQL container starts and is healthy (`pg_isready` succeeds)
- [x] Provisioning container starts and listens on port 5055
- [x] API connects to PostgreSQL via `DATABASE_URL`
- [x] Worker connects to PostgreSQL via `DATABASE_URL`
- [x] `curl http://10.200.0.14:5003/health` returns `200 OK`
- [x] `https://idcreate.vrsctest.buildwithdreams.com` returns `200 OK` from internet
- [x] `database is locked` errors are gone
- [x] All playbooks idempotent — safe to re-run