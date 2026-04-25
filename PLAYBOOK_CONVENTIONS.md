# Provisioning Conventions

## Bootstrap Flag Logic

The `VERUSD_BOOTSTRAP_FLAG` controls whether verusd bootstraps from a pre-synced snapshot or syncs from peers.

### Flag States

| `VERUSD_BOOTSTRAP_FLAG` | When to use |
|------------------------|-------------|
| `-bootstrap` | Fresh node, first run, or after data dir corruption |
| *(empty)* | Normal operation, syncing from peers, or after clean shutdown |

### Robust Bootstrap Decision (on startup)

Two conditions must be checked together:

1. **Data directories exist** — `chainstate/` AND `blocks/` present in `data_dir/`
2. **Clean shutdown confirmed** — `debug.log` ends with `Shutdown: done`

```
IF chainstate exists AND blocks exists AND debug.log ends with "Shutdown: done"
  → set BOOTSTRAP_FLAG= (empty)  ← safe to sync from peers
ELSE
  → set BOOTSTRAP_FLAG=-bootstrap  ← re-bootstrap to ensure clean state
```

**Why both checks?** An unclean daemon exit leaves data dirs intact but potentially corrupted. Without the `Shutdown: done` check, a subsequent startup would silently try peer sync on corrupted data. The `Shutdown: done` confirmation is the single source of truth for chain health.

### Startup Hygiene Check (integrated into 07-setup-vrsc.yml)

`07-setup-vrsc.yml` runs before every container start. It checks `debug.log` for `Shutdown: done` since the daemon is offline at that point.

### System Hygiene Check (09-hygiene.yml — RPC-based, cron-friendly)

Runs while the daemon is **online**. Uses RPC `getinfo` to check:
- `blocks == longestchain` → fully synced, no fork → flip `BOOTSTRAP_FLAG=` (empty)
- `blocks != longestchain` → fork detected → leave `-bootstrap` on, report fork
- RPC unavailable → daemon offline/unreachable → leave `-bootstrap` on, report

Idempotent and safe to run as a cron job every hour.

---

## Docker /24 Network IP Convention

Applies to any chain, any /24 subnet.

| Octet | Role |
|-------|------|
| `.1` | Docker gateway |
| `.10` | caddy reverse proxy (new) |
| `.11` | verusd daemon |
| `.12` | RPC server |
| `.13` | QR creator |
| `.14` | ID verification service (future) |

---

## Compose Project Naming Convention

Format: `<network>_<color>`

Container names become `<project_name>-<service>-1`.

| Chain | Project name | Example container |
|-------|-------------|-----------------|
| VRSC mainnet | `mains_blue` | `mains_blue-vrsc-1` |
| VRSC mainnet (failover) | `mains_green` | `mains_green-vrsc-1` |
| vRSCTEST | `test_blue` | `test_blue-vrsc-1` |
| vDEX PBaaS | `vdex_blue` | `vdex_blue-vdex-1` |
| varrr PBaaS | `varrr_blue` | `varrr_blue-varrr-1` |
| chips PBaaS | `chips_blue` | `chips_blue-chips-1` |

---

## Docker Network Naming Convention

Format: `net-<chain>-<color>`

Examples: `net-vrsc-blue`, `net-vrsc-green`, `net-vdex-blue`, `net-varrr-blue`

---

## Data Directory Reference

| Chain | Data dir inside container | Config path inside container | `CURRENCYID_HEX` env var | Notes |
|-------|-------------------------|------------------------------|-------------------------|-------|
| VRSC | `/root/.komodo/VRSC` | `/root/.komodo/VRSC/VRSC.conf` | *(not used)* | Non-PBaaS, flat structure |
| vRSCTEST | `/root/.komodo/vrsctest` | `/root/.komodo/vrsctest/vrsctest.conf` | *(not used)* | Non-PBaaS, flat structure |
| vARRR | `/root/.verus/pbaas/<hex>` | `/root/.verus/pbaas/<hex>/<hex>.conf` | `e9e10955b7d16031e3d6f55d9c908a038e3ae47d` | PBaaS nested structure |
| vDEX | `/root/.verus/pbaas/<hex>` | `/root/.verus/pbaas/<hex>/<hex>.conf` | `53fe39eea8c06bba32f1a4e20db67e5524f0309d` | PBaaS nested structure |
| CHIPS | `/root/.verus/pbaas/<hex>` | `/root/.verus/pbaas/<hex>/<hex>.conf` | `f315367528394674d45277e369629605a1c3ce9f` | PBaaS nested structure |

> **PBaaS chains** use a nested data dir: `/root/.verus/pbaas/<currencyidhex>/<currencyidhex>.conf`
> The hex ID is also set as `CURRENCYID_HEX` in the chain's `.env` file.
> On the host, compose mounts `./data_dir:/root/.verus/pbaas/${CURRENCYID_HEX}` so the host-side config is `<chain_dir>/data_dir/<hex>.conf`.

### PBaaS Currency ID Discovery Procedure

When a new PBaaS chain needs to be provisioned and its hex ID is unknown:

```bash
# Step 1: Query the VRSC main chain (container must be running)
ssh bwd "docker exec mains_blue-vrsc-1 verus getcurrency <lowercase_name> 2>&1"

# Step 2: Extract currencyidhex from the JSON response
ssh bwd "docker exec mains_blue-vrsc-1 verus getcurrency <name> 2>&1" \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['currencyidhex'])"

# Example — get vARRR hex ID:
ssh bwd "docker exec mains_blue-vrsc-1 verus getcurrency varrr 2>&1" \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['currencyidhex'])"
# Output: e9e10955b7d16031e3d6f55d9c908a038e3ae47d
```

The `currencyidhex` field is the raw hex chain ID. It is used for:
1. `CURRENCYID_HEX` in the chain's `.env` file
2. The nested directory and config filename inside the container
3. The host-side config file path via the volume mount

Known IDs (confirmed on BWD):

| Chain | `getcurrency` arg | `currencyidhex` |
|-------|------------------|----------------|
| vARRR | `varrr` | `e9e10955b7d16031e3d6f55d9c908a038e3ae47d` |
| vDEX | `vdex` | `53fe39eea8c06bba32f1a4e20db67e5524f0309d` |
| CHIPS | `chips` | `f315367528394674d45277e369629605a1c3ce9f` |

> **Note:** Use lowercase chain names in the RPC call (`varrr`, `vdex`, `chips`).

---

## Playbook Inventory

| Playbook | Purpose |
|----------|---------|
| `01-prep.yml` | Install prerequisites (Docker, Python, git) |
| `02-clone-repos.yml` | Clone docker-verusd, dream-pbaas-provisioning |
| `03-docker-networks.yml` | Create Docker bridge networks per chain |
| `04-check-version.yml` | Compare Dockerfile VERUS_VERSION vs GitHub latest |
| `05-build-image.yml` | Build `buildwithdreams/verusd:<version>` image |
| `06-fetch-params.yml` | Download Zcash Sapling params (~800MB) |
| `07-setup-vrsc.yml` | Copy env.sample → .env, set BOOTSTRAP_FLAG, fix IP |
| `08-start-vrsc.yml` | `docker compose up -d` with health check |
| `09-hygiene.yml` | Post-shutdown: confirm clean shutdown, flip bootstrap off |
| `10-shutdown-vrsc.yml` | Gracefully stop VRSC daemon |
| `11-setup-pbaas.yml` | Configure PBaaS chain config + generate RPC credentials |
| `12-clean-pbaas-chainstate.yml` | Remove chainstate/blocks/database — preserve wallet + config |
| `13-start-pbaas.yml` | Start PBaaS container with health check |
| `14-pbaas-peer-config.yml` | Write peer data to PBaaS config |
| `14-shutdown-pbaas.yml` | Gracefully stop PBaaS container |
| `15-sync-status.yml` | Poll `getinfo` until blocks == longestchain |
| `16-add-vrsc-rpc-allowip.yml` | Add CIDR to VRSC.conf rpcallowip |
| `17-add-pbaas-rpc-allowip.yml` | Add CIDR to PBaaS.conf rpcallowip |
| `18-wait-verify-sync.yml` | Wait + verify full sync to longestchain |
| `20-rpc-server-clone.yml` | Clone rust_verusd_rpc_server repo |
| `21-rpc-server-configure.yml` | Write Conf.toml with daemon URL + credentials |
| `22-rpc-server-build.yml` | Build Docker image for RPC server |
| `23-rpc-server-deploy.yml` | Deploy RPC server container on net-vrsc-blue (.12) |
| `24-rpc-server-getinfo.yml` | Smoke-test RPC server via curl |
| `25-qr-creator-clone.yml` | Clone verus-identity-qr-creator repo |
| `26-qr-creator-configure.yml` | Write config.js + Dockerfile + docker-compose.yml |
| `27-qr-creator-deploy.yml` | Build + deploy QR creator on net-vrsc-blue (.13) |
| `28-caddy-deploy.yml` | Deploy Caddy reverse proxy + Lets Encrypt on net-vrsc-blue (.10) |
| `29-caddy-teardown.yml` | Remove Caddy container, compose project, and data |
