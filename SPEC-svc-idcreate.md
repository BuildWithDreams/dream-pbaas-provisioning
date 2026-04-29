# SPEC: svc-idcreate Deployment on BWD VRSCTEST Node

**Date:** 2026-04-29
**Status:** Draft — pending operator approval
**Repo:** `BuildWithDreams/svc-idcreate`

---

## 1. Purpose

Deploy `svc-idcreate` (FastAPI identity creation service + background worker) on the BWD VRSCTEST node, accessible at `https://idcreate.vrsctest.buildwithdreams.com` with Let's Encrypt TLS.

The service:
- Exposes an external API (`/api/provisioning/challenge`, `/api/provisioning/request`, `/api/provisioning/status/{id}`)
- Connects to the **VRSCTEST** verusd daemon via the `DAEMON_VERUSD_VRSC` slot + `NATIVE_COIN="VRSCTEST"` (VRSCTEST hijacks the VRSC slot in `SFConstants.py`)
- Runs a background worker that polls pending registrations and advances their state
- **Provisioning service not included** — not ready yet, focus is on the id creation base Python service

---

## 2. Architecture

```
Internet → Caddy (10.201.0.10:443) → idcreate.vrsctest.buildwithdreams.com
                                                 ↓
                                    reverse_proxy 10.200.0.14:5003
                                                 ↓
                              idcreate-api + idcreate-worker (net-vrsctest)
                                                 ↓
                                    VRSCTEST verusd daemon (10.200.0.11:27486)
```

- **Docker network:** `net-vrsctest` (`10.200.0.0/24`) — the same network as the VRSCTEST daemon
- **Service IP:** `10.200.0.14` (.14 is next available after .11=verusd)
- **Compose project:** `dev200_idcreate` (follows `<network>_<color>` convention — VRSCTEST uses `dev200` from its env.sample)
- **Compose project:** `dev200_idcreate`

---

## 3. Domain / DNS

- **Subdomain:** `idcreate.vrsctest.buildwithdreams.com`
- **DNS:** A record must point to `135.181.136.105` (BWD server)
- **TLS:** Automatic via Caddy + Let's Encrypt (existing email: `hermesreport@verus.trading`)

---

## 4. RPC Configuration

The service reads daemon RPC config from environment variables named after the pattern `{daemon_name}_rpc_*`, where daemon names are defined in `SFConstants.py`:

| Daemon name | Chain | Notes |
|-------------|-------|-------|
| `DAEMON_VERUSD_VRSC` | VRSCTEST | **Hijacks the VRSC slot** via `NATIVE_COIN="VRSCTEST"` — no separate VRSCTEST slot exists |

For deployment, the following RPC env vars are written to `.env` by playbook 41:

```
verusd_vrsc_rpc_enabled="true"
verusd_vrsc_rpc_user="<from vrsctest.conf>"
verusd_vrsc_rpc_password="<from vrsctest.conf>"
verusd_vrsc_rpc_port="18842"
verusd_vrsc_rpc_host="10.200.0.11"
NATIVE_COIN="VRSCTEST"
```

> **RPC allowip:** The VRSCTEST daemon must have `rpcallowip=10.200.0.0/24` in its config — already set via playbook 16b.

---

## 5. Playbook Inventory

### 5.1 `39-idcreate-clone.yml`
- Clones `https://github.com/BuildWithDreams/svc-idcreate.git` to `~/svc-idcreate`
- Idempotent: skips if directory exists, does `git pull` if already cloned
- **Requires:** nothing
- **Run:** `ansible-playbook -i inventory.ini playbooks/39-idcreate-clone.yml`

### 5.2 `40-idcreate-build.yml`
- Builds Docker image `buildwithdreams/svc-idcreate:local` from `~/svc-idcreate`
- Uses `docker build` with `--no-cache` option; always rebuilds
- Build args: `UV_LINK_MODE=copy`
- **Requires:** `39-idcreate-clone.yml`
- **Run:** `ansible-playbook -i inventory.ini playbooks/40-idcreate-build.yml`

### 5.3 `41-idcreate-deploy.yml`
- Creates `docker-compose.yml` for the idcreate stack (api + worker) at `~/svc-idcreate/`
- Deploys on `net-vrsctest` with fixed IP `10.200.0.14`
- Writes `.env` from `env.sample` + RPC connection vars + `NATIVE_COIN="VRSCTEST"`
- **Requires:** `40-idcreate-build.yml`; VRSCTEST daemon must be running
- **Run:** `ansible-playbook -i inventory.ini playbooks/41-idcreate-deploy.yml`

### 5.4 `42-idcreate-caddy-route.yml`
- Adds `idcreate.vrsctest.buildwithdreams.com` route block to the existing Caddyfile at `~/caddy/Caddyfile`
- **Pre-requisite:** Caddy container must be on `net-vrsctest` — this playbook also updates Caddy's `docker-compose.yml` to add `net-vrsctest` as a second network
- Triggers Caddy reload after updating the route
- **Requires:** `41-idcreate-deploy.yml` (idcreate must be deployed first, since Caddy can't reload a route to a non-existent upstream)
- **Run:** `ansible-playbook -i inventory.ini playbooks/42-idcreate-caddy-route.yml`

---

## 6. Playbook Ordering

```
39-idcreate-clone.yml      # Clone repo
40-idcreate-build.yml      # Build Docker image
41-idcreate-deploy.yml     # Deploy idcreate stack
42-idcreate-caddy-route.yml # Add Caddy route + extend Caddy to net-vrsctest
```

---

## 7. Service Parameters

| Parameter | Value | Source |
|-----------|-------|--------|
| Repo URL | `https://github.com/BuildWithDreams/svc-idcreate.git` | This spec |
| Clone path | `/home/dream-hermes-agent/svc-idcreate` | This spec |
| Docker network | `net-vrsctest` | Existing |
| Service IP | `10.200.0.14` | Next available after .11=verusd, .13=qrcodes |
| API port | `5003` (host: `127.0.0.1:5003`) | svc-idcreate default |
| Provisioning port | `5055` (host-only) | svc-idcreate default |
| Worker port | none (internal) | svc-idcreate default |
| Compose project | `dev200_idcreate` | VRSCTEST uses `dev200` prefix |
| Container (API) | `dev200_idcreate-api-1` | Auto-generated |
| Container (Worker) | `dev200_idcreate-worker-1` | Auto-generated |
| Image | `buildwithdreams/svc-idcreate:local` | Built locally |
| Domain | `idcreate.vrsctest.buildwithdreams.com` | This spec |
| Upstream for Caddy | `10.200.0.14:5003` | This spec |
| NATIVE_COIN | `VRSCTEST` | This spec |
| HEALTH_RPC_DAEMON | `verusd_vrsc` | svc-idcreate default |
| RPC host for VRSCTEST | `10.200.0.11:18842` | VRSCTEST daemon (port 18842) |
| SFConstants slot | `DAEMON_VERUSD_VRSC` | VRSCTEST hijacks the VRSC slot via `NATIVE_COIN="VRSCTEST"` |

---

## 8. Caddy Network Extension

Caddy is already on `net-vrsctest` (added by `37-qrcodes-caddy-network.yml` during the qrcodes deployment). No further network changes needed.

---

## 9. Data Persistence

- **SQLite DB:** stored at `/data/registrar.db` inside container, mapped to Docker named volume `idcreate_data`
- **Source of funds / Z-address / Referral ID:** set via `.env` vars at deploy time (not hardcoded in playbooks — operator provides)
- **API keys:** via `REGISTRAR_API_KEYS` env var (operator provides; not set by playbooks)

---

## 10. Out of Scope

- API key provisioning (operator manages `REGISTRAR_API_KEYS`)
- Source of funds / Z-address population (operator sets in `.env`)
- Horizontal scaling (single replica only)
- Custom domain beyond `idcreate.vrsctest.buildwithdreams.com`
- PBaaS chain identity registration (VRSCTEST only for now)

---

## 11. Out of Scope

- Provisioning service (svc-provisioning companion) — not ready yet
- API key provisioning (operator manages `REGISTRAR_API_KEYS`)
- Source of funds / Z-address population (operator sets in `.env`)
- Horizontal scaling (single replica only)
- PBaaS chain identity registration (VRSCTEST only for now)

## 12. Open Questions

- [ ] **SFConstants mapping confirmed:** `DAEMON_VERUSD_VRSC` + `NATIVE_COIN="VRSCTEST"` points to VRSCTEST daemon at `10.200.0.11:18842` ✅
- [ ] **Provisioning service:** to be added once it's working

---

## 12. Acceptance Criteria

- [ ] `svc-idcreate` cloned to `~/svc-idcreate` on BWD
- [ ] Docker image `buildwithdreams/svc-idcreate:local` built on BWD
- [ ] idcreate-api and idcreate-worker containers running on `net-vrsctest` at `10.200.0.14`
- [ ] `.env` contains correct VRSCTEST RPC credentials and `NATIVE_COIN="VRSCTEST"`
- [ ] `curl http://10.200.0.14:5003/health` returns 200 from within the Docker network
- [ ] `https://idcreate.vrsctest.buildwithdreams.com` resolves and returns 200 from internet
- [ ] TLS certificate auto-provisioned by Caddy
- [ ] All playbooks idempotent — safe to re-run
- [ ] No manual SSH commands required
