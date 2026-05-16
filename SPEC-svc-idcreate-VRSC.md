# SPEC: svc-idcreate Deployment on BWD VRSC Mainnet

**Date:** 2026-05-16
**Status:** Active — initial deployment
**Repo:** `BuildWithDreams/svc-idcreate`
**URL:** `https://idcreate.vrsc.buildwithdreams.com`

---

## 1. Purpose

Deploy `svc-idcreate` (FastAPI identity creation service + background worker + PostgreSQL) on the BWD VRSC mainnet node, accessible at `https://idcreate.vrsc.buildwithdreams.com` with Let's Encrypt TLS.

The service:
- Exposes an external API (`/api/register`, `/api/registrations/*`, `/api/webhook/*`)
- Connects to the **VRSC mainnet** verusd daemon via the `DAEMON_VERUSD_VRSC` slot + `NATIVE_COIN="VRSC"`
- Runs a background worker that polls pending registrations and advances their state
- Uses **PostgreSQL** for durable concurrent data access
- Provisioning adapter runs in **HTTP mode** (`PROVISIONING_ADAPTER_MODE=http`)

---

## 2. Architecture

```
Internet → Caddy (mains_blue_caddy-caddy-1) → idcreate.vrsc.buildwithdreams.com
                                                           ↓
                                         reverse_proxy 10.200.0.14:5003
                                         (via Caddy's net-vrsctest interface)
                                                           ↓
                         ┌─────────────────────────────────┴─────────────────────────────────┐
                         ↓                                                                  ↓
            idcreate-api (FastAPI)                                    idcreate-provisioning (Node.js)
            10.200.0.14:5003                                        10.200.0.14:5055
                         ↓                                                                  ↓
            idcreate-worker (polling)                           svc-provisioning (scripts)
                         ↓
            PostgreSQL 16-alpine
            dev200_idcreate-postgres-1
            5432 (host: 127.0.0.1:5432)
                         ↓
            VRSC mainnet verusd daemon (10.201.0.11:27486)
```

- **Docker network (idcreate containers):** `net-vrsctest` (`10.200.0.0/24`)
- **Caddy:** multi-homed on `net-vrsc-blue` (`10.201.0.10`) and `net-vrsctest` (`10.200.0.2`) — reaches idcreate via `net-vrsctest`
- **Service IP:** `10.200.0.14` (idcreate containers)
- **Compose project:** `dev201_idcreate` ⚠️ (see note below)
- **PostgreSQL:** `dev200_idcreate-postgres-1` (named volume)

> ⚠️ **Container naming issue:** Containers are currently named `dev200_idcreate-*` instead of `dev201_idcreate-*` because the compose file has hardcoded `container_name:` values that override the project-derived name. Tracked in [GitHub issue #24](https://github.com/BuildWithDreams/dream-pbaas-provisioning/issues/24). The compose project name should use `COMPOSE_PROJECT_NAME` env var instead.

---

## 3. Container Inventory

| Container | Service | IP | Ports |
|---|---|---|---|
| `dev200_idcreate-postgres-1` | PostgreSQL 16-alpine | auto | `5432` (host: `127.0.0.1:5432`) |
| `dev200_idcreate-provisioning-1` | Node.js provisioning scripts | auto | `5055` (host: `127.0.0.1:5055`) |
| `dev200_idcreate-api-1` | FastAPI | `10.200.0.14` | `5003` (host: `127.0.0.1:5003`) |
| `dev200_idcreate-worker-1` | Background state machine | auto | — (internal) |

---

## 4. Domain / DNS

- **Subdomain:** `idcreate.vrsc.buildwithdreams.com`
- **DNS:** A record points to `135.181.136.105` (BWD server)
- **TLS:** Manual via Caddy (`tls hermesreport@verus.trading`)

---

## 5. Environment Variables

### Set by playbook 41b (RPC + service)

```
NATIVE_COIN="VRSC"
HEALTH_RPC_DAEMON="verusd_vrsc"
verusd_vrsc_rpc_enabled="true"
verusd_vrsc_rpc_user="<from VRSC.conf>"
verusd_vrsc_rpc_password="<from VRSC.conf>"
verusd_vrsc_rpc_port="27486"
verusd_vrsc_rpc_host="10.201.0.11"
```

### Provisioning adapter + postgres

```
DATABASE_URL="postgresql://idcreate:***@postgres:5432/idcreate"
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
PARENT=...                    # Parent currency, e.g. "VRSC"
FEE_OFFER=...                 # Identity registration fee offer
Z_ADDRESS=...                # Z-address (optional)
REFERRAL_ID=...               # Referral identity (optional)
```

---

## 6. Playbook Inventory

| # | Playbook | Purpose |
|---|---|---|
| `39b` | `39b-idcreate-clone-vrsc.yml` | Clone repo for VRSC mainnet (idempotent) |
| `40b` | `40b-idcreate-build-vrsc.yml` | Build Docker image for VRSC |
| `41b` | `41b-idcreate-deploy-vrsc.yml` | Deploy full stack (postgres + provisioning + api + worker) |
| `42b` | `42b-idcreate-caddy-route-vrsc.yml` | Add HTTPS route in Caddy |
| `43b` | `43b-idcreate-add-api-key-vrsc.yml` | Generate + persist `REGISTRAR_API_KEYS` |
| `44b` | `44b-idcreate-source-of-funds-vrsc.yml` | Set source of funds |
| `45b` | `45b-idcreate-update-vrsc.yml` | Pull + rebuild + restart |
| `46b` | `46b-idcreate-allowed-parents-vrsc.yml` | Configure allowed parent currencies |
| `47b` | `47b-idcreate-restart-vrsc.yml` | Restart to pick up .env changes |

---

## 7. Provisioning Adapter

The provisioning adapter runs in **HTTP mode** — a separate `provisioning` container that the API and worker call via HTTP on port 5055.

```
api/worker → HTTP → provisioning:5055 → provisioning/engine.py → VRSC daemon
```

Key env vars:
- `PROVISIONING_ADAPTER_MODE=http`
- `PROVISIONING_SERVICE_URL=http://127.0.0.1:5055`
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
- **Port:** `5432` published to `127.0.0.1:5432` (host-only)
- **Health check:** `pg_isready -U idcreate -d idcreate`

---

## 9. Key Differences: VRSCTEST → VRSC

| Aspect | VRSCTEST | VRSC |
|---|---|---|
| Daemon RPC port | `18843` | `27486` |
| Docker network | `net-vrsctest` | `net-vrsctest` (containers) / `net-vrsc-blue` (Caddy) |
| NATIVE_COIN | `VRSCTEST` | `VRSC` |
| Config path | `vrsctest/data_dir/vrsctest.conf` | `mainnet/data_dir/VRSC.conf` |
| Domain | `idcreate.vrsctest.buildwithdreams.com` | `idcreate.vrsc.buildwithdreams.com` |
| Caddy network join | Required (net-vrsctest) | Not needed (Caddy native on net-vrsc-blue) |

---

## 10. Deployment Order

```
39b-idcreate-clone-vrsc.yml        # Clone repo
40b-idcreate-build-vrsc.yml        # Build Docker image
41b-idcreate-deploy-vrsc.yml       # Deploy full stack
42b-idcreate-caddy-route-vrsc.yml  # Add HTTPS route (idempotent)
43b-idcreate-add-api-key-vrsc.yml  # If API keys not yet set
```

On update (new commits):
```
45b-idcreate-update-vrsc.yml       # Pull + rebuild + restart with postgres health wait
```

After editing .env:
```
47b-idcreate-restart-vrsc.yml       # Restart containers (includes postgres health wait)
```

---

## 11. Acceptance Criteria

- [ ] VRSC mainnet daemon is running and reachable at `10.201.0.11:27486`
- [ ] PostgreSQL container starts and is healthy (`pg_isready` succeeds)
- [ ] Provisioning container starts and listens on port 5055
- [ ] API connects to PostgreSQL via `DATABASE_URL`
- [ ] Worker connects to PostgreSQL via `DATABASE_URL`
- [ ] `curl http://10.200.0.14:5003/` returns `{"message":"Hello from the new pipeline!"}`
- [ ] `https://idcreate.vrsc.buildwithdreams.com/` returns `200 OK` from internet
- [ ] All playbooks idempotent — safe to re-run