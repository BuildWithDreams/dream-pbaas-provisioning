# SPEC: svc-idcreate Deployment on BWD VRSCTEST Node

**Date:** 2026-04-29
**Status:** Draft — pending operator approval
**Repo:** `BuildWithDreams/svc-idcreate`

---

## 1. Purpose

Deploy `svc-idcreate` (FastAPI identity creation service + background worker) on the BWD VRSCTEST node, accessible at `https://idcreate.vrsctest.buildwithdreams.com` with Let's Encrypt TLS.

The service:
- Exposes an external API (`/api/provisioning/challenge`, `/api/provisioning/request`, `/api/provisioning/status/{id}`)
- Connects to the **VRSCTEST** verusd daemon via RPC to sign and submit on-chain identity registrations
- Runs a background worker that polls pending registrations and advances their state
- Uses a companion `svc-provisioning` HTTP adapter for primitive cryptographic operations

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
- **Compose project:** `test_blue_idcreate` (follows `<network>_<color>` convention)
- **API container:** `test_blue_idcreate-api-1` — FastAPI on port 5003
- **Worker container:** `test_blue_idcreate-worker-1` — polling worker
- **Caddy container:** Already on `net-vrsc-blue` — must be added to `net-vrsctest` to proxy the new route

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
| `verusd_vrsc` | VRSC mainnet | — |
| `verusd_varrr` | vARRR PBaaS | — |
| `verusd_vdex` | vDEX PBaaS | — |
| `verusd_chips` | CHIPS PBaaS | — |

The VRSCTEST chain does NOT appear in `SFConstants.py` directly — it uses the `DAEMON_VERUSD_VRSC` slot with `NATIVE_COIN="VRSCTEST"` to connect to VRSCTEST via the VRSC mainnet daemon's _cross-chain_ RPC (or the VRSCTEST daemon itself).

> **Review needed:** Confirm whether `SFConstants.py` maps `DAEMON_VERUSD_VRSC` + `NATIVE_COIN="VRSCTEST"` to the VRSCTEST daemon (10.200.0.11:27486) or to VRSC mainnet. This affects which RPC credentials are written to `.env`.

For deployment, the following RPC env vars must be set in `.env`:

```
verusd_vrsc_rpc_enabled="true"
verusd_vrsc_rpc_user="dream"
verusd_vrsc_rpc_password="<from vrsctest .env RPCPASS>"
verusd_vrsc_rpc_port="27486"
verusd_vrsc_rpc_host="10.200.0.11"
```

> **RPC allowip:** The VRSCTEST daemon must have `rpcallowip=10.200.0.0/24` in its config to accept connections from the idcreate container. This is likely already set via playbook 16b.

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
| Service IP | `10.200.0.14` | Next available (.14) |
| API port | `5003` (host: `127.0.0.1:5003`) | svc-idcreate default |
| Worker port | none (internal) | svc-idcreate default |
| Compose project | `test_blue_idcreate` | Convention |
| Container (API) | `test_blue_idcreate-api-1` | Auto-generated |
| Container (Worker) | `test_blue_idcreate-worker-1` | Auto-generated |
| Image | `buildwithdreams/svc-idcreate:local` | Built locally |
| Domain | `idcreate.vrsctest.buildwithdreams.com` | This spec |
| Upstream for Caddy | `10.200.0.14:5003` | This spec |
| NATIVE_COIN | `VRSCTEST` | This spec |
| HEALTH_RPC_DAEMON | `verusd_vrsc` | svc-idcreate default |

---

## 8. Caddy Network Extension

Caddy currently runs on `net-vrsc-blue` only. Since `idcreate.vrsctest.buildwithdreams.com` resolves to the same server IP, Caddy must be reachable from `net-vrsctest` to proxy to `10.200.0.14`.

**Solution:** Add `net-vrsctest` as a second network in Caddy's `docker-compose.yml`. The compose file is rewritten by playbook 42 to add the extra network. No Caddy image rebuild needed — networks are a runtime concern.

New Caddy networks in compose:
```yaml
networks:
  pbaas_network:  # existing net-vrsc-blue
    name: net-vrsc-blue
    external: true
  vrsctest_network:  # new
    name: net-vrsctest
    external: true
```

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

## 11. Open Questions

- [ ] **SFConstants mapping:** Confirm whether `DAEMON_VERUSD_VRSC` + `NATIVE_COIN="VRSCTEST"` connects to VRSCTEST daemon or VRSC mainnet daemon. If VRSCTEST has a separate entry in `SFConstants`, update RPC env var names accordingly.
- [ ] **DNS A record:** Confirm `idcreate.vrsctest.buildwithdreams.com` A record is set to `135.181.136.105`.
- [ ] **RPC credentials:** Confirm VRSCTEST daemon RPC user (`dream`) and password match what's in `~/docker-verusd/vrsctest/.env`.
- [ ] **Existing `rpcallowip`:** Confirm VRSCTEST daemon's `.conf` already includes `rpcallowip=10.200.0.0/24` (likely set by playbook 16b, but verify).

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
