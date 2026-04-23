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

`07-setup-vrsc.yml` runs before every container start. It reads the last line of `debug.log` to determine whether bootstrap should be on or off.

### System Hygiene Check (separate playbook)

After a clean daemon shutdown, run `09-hygiene.yml` to flip `BOOTSTRAP_FLAG=` off. This is a once-off operation — once the chain is confirmed synced and healthy, bootstrap is disabled permanently until a future need arises (corruption, fresh install, etc.).

### Clean Shutdown Detection

verusd writes `Shutdown: done` to `debug.log` on graceful exit. This is the canonical check.

```
# Inside container:
tail -1 /root/.komodo/VRSC/debug.log
# Should contain: "Shutdown: done"

# Or for PBaaS:
tail -1 /root/.verus/pbaas/<hex>/debug.log
```

---

## Docker /24 Network IP Convention

Applies to any chain, any /24 subnet.

| Octet | Role |
|-------|------|
| `.1` | Docker gateway |
| `.11` | verusd daemon |
| `.12` | RPC server (future) |
| `.13` | block explorer (future) |
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

| Chain | Data dir inside container |
|-------|-------------------------|
| VRSC | `/root/.komodo/VRSC` |
| vRSCTEST | `/root/.komodo/vrsctest` |
| PBaaS (vDEX, varrr, chips) | `/root/.verus/pbaas/<currency_hex_id>` |

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
