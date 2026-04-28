# SPEC: VRSCTEST Testnet Node Provisioning

## Status
Draft — pending questions in §6

## Overview

Provision a Verus **testnet** node (`VRSCTEST`) on the BWD server, mirroring the VRSC mainnet playbook pipeline (setup → start), using the production `buildwithdreams/verusd` image.

---

## 1. Network

| Property | Value |
|---|---|
| Subnet | `10.200.0.0/24` |
| Bridge name | `SP1020001` |
| Docker network name | `net-vrsctest` |
| verusd IP | `10.200.0.11` |

> **Conventions (from memory):** VRSC=201, VARRR=202, vDEX=203, CHIPS=204 → VRSCTEST=200 (user-specified).

**Playbook: `03-docker-networks.yml`** (augmented)
- Add a `net-vrsctest` entry to `verus_networks` in `group_vars/production.yml`
- Or better: add to the source `env.sample` in `docker-verusd/infrastructure/` and regenerate via `02-generate-env-files.yml`
- The network create step in `03-docker-networks.yml` is already a loop — no new playbook needed

---

## 2. docker-verusd Files (vrsctest/ dir)

> ⚠️ The existing `vrsctest/` dir in `docker-verusd` has stale content that must be corrected before provisioning.

### `vrsctest/docker-compose.yml` — issues to fix

| Field | Existing (wrong) | Correct |
|---|---|---|
| `image` | `verustrading/verusd:0.1` | `buildwithdreams/verusd:<tag>` |
| `command` | `verusd -chain=vrsctest -testnet …` | `verusd -chain=VRSCTEST ${VERUSD_BOOTSTRAP_FLAG}` |
| `volumes` | `./data_dir:/root/.komodo/vrsctest` | `./data_dir:/root/.komodo/VRSCTEST` |
| `network` | `dev16` | `pbaas_network` (matches mainnet) |

### `vrsctest/env.sample` — issues to fix

| Field | Existing (wrong) | Correct |
|---|---|---|
| `DOCKER_NETWORK_SUBNET` | `10.199.0.0/24` | `10.200.0.0/24` |
| `BRIDGE_CUSTOM_NAME` | `SP1019901` | `SP1020001` |
| `DOCKER_NETWORK_NAME` | `dev199` | `net-vrsctest` |
| `VERUSD_IPV4` | `10.199.0.11` | `10.200.0.11` |
| `VERUSD_HOSTNAME` | `verusd_vrsctest` | `verusd_vrsctest` (ok) |

> The command in compose should be `verusd -chain=VRSCTEST` — Verus uses `-chain=VRSCTEST` to select the testnet chain; `-testnet` is a separate legacy flag that should not be combined with `-chain=` for a named testnet.

### `vrsctest/data_dir/VRSC.conf` (on host)

No separate config file is created by the compose — verusd reads from the data dir. A `sample.conf` exists; it appears to be a PBaaS chain config (not a plain VRSCTEST config). Confirm whether a basic `VRSC.conf` with `rpcuser`, `rpcpassword`, `server=1`, `txindex=1` is sufficient or if the existing PBaaS fields are needed.

---

## 3. Playbooks

### Playbook A: `07b-setup-vrsctest.yml` — setup + bootstrap detection

Mirrors `07-setup-vrsc.yml` exactly, with these substitutions:

| Variable | VRSC mainnet | VRSCTEST |
|---|---|---|
| `chain_path` | `mainnet` | `vrsctest` |
| `data_dir` | `{{ mainnet_path }}/data_dir` | `{{ vrsctest_path }}/data_dir` |
| `chain_subdir` | `VRSC` | `VRSCTEST` |
| `compose_path` | `{{ mainnet_path }}` | `{{ vrsctest_path }}` |
| `.env path` | `{{ mainnet_path }}/.env` | `{{ vrsctest_path }}/.env` |
| `chain_name` | `VRSC` | `VRSCTEST` |

**Steps:**
1. Copy `vrsctest/env.sample` → `vrsctest/.env` (idempotent — `ansible.builtin.copy` with `remote_src: true`)
2. Get `net-vrsctest` subnet from Docker, derive `verusd_ip = <subnet>.11`
3. Update `VERUSD_IPV4` in `.env`
4. Check `{{ data_dir }}/chainstate` and `{{ data_dir }}/blocks` exist
5. Check `tail -1 /root/.komodo/VRSCTEST/debug.log` for `Shutdown: done`
6. **Bootstrap logic** (identical to mainnet): both chainstate+blocks dirs **and** clean shutdown → `BOOTSTRAP_FLAG=` (empty); either missing → `BOOTSTRAP_FLAG=-bootstrap`
7. Write `VERUSD_BOOTSTRAP_FLAG` to `.env`
8. Display final `.env`

**Bootstrap logic (for reference):**
```
is_first_run = not (chainstate_exists and blocks_exists and clean_shutdown)
BOOTSTRAP_FLAG = '-bootstrap' if is_first_run else ''
```

---

### Playbook B: `08b-start-vrsctest.yml` — start container

Mirrors `08-start-vrsc.yml` with these substitutions:

| Variable | VRSC mainnet | VRSCTEST |
|---|---|---|
| `compose_path` | `mainnet` | `vrsctest` |
| `service_name` | `vrsc` | `vrsctest` |
| `container_check_pattern` | `(-vrsc-1\|mains_blue-vrsc-1\|pbaas_mainnets-vrsc-1)` | `vrsctest` |

**Steps:**
1. Fetch latest Verus release → resolve image tag
2. Read `.env` → extract `DOCKER_NETWORK_NAME`
3. Verify `net-vrsctest` Docker network exists (fail if not)
4. `source .env && docker compose pull && docker compose up -d`
5. Run `check-vrsc-container.sh` (or a renamed variant) to verify container health

---

### Playbook C (optional): `10b-shutdown-vrsctest.yml` — graceful shutdown

Mirrors `10-shutdown-vrsc.yml`:
1. Detect container by `vrsctest` name pattern
2. Wait for daemon readiness (`getinfo` not loading block index)
3. `verus-cli stop`
4. `docker stop -t 60` (timeout 90s)
5. `docker network disconnect net-vrsctest <container>`
6. Clear `BOOTSTRAP_FLAG=` in `.env` (record clean shutdown)

---

## 4. Playbook Ordering

```
07-setup-vrsc.yml        # VRSC mainnet
07b-setup-vrsctest.yml   # VRSCTEST testnet  ← new
08-start-vrsc.yml         # VRSC mainnet
08b-start-vrsctest.yml    # VRSCTEST testnet  ← new
```

> Note: playbooks `07-setup-*` and `08-start-*` are independent chains — they can run in either order. `07b` and `08b` follow the same pattern as their mainnet counterparts.

---

## 5. Verification / Post-run Checklist

- [ ] `docker network inspect net-vrsctest` → subnet `10.200.0.0/24`
- [ ] `docker ps` → container `mains_blue-vrsctest-1` (or compose project name variant) running
- [ ] `verus-cli -chain=VRSCTEST getinfo` → `blocks > 0`, `synced: false`
- [ ] `verus-cli -chain=VRSCTEST getinfo` called twice with same `blocks` value → stable (not still downloading)
- [ ] `grep BOOTSTRAP_FLAG vrsctest/.env` → `VERUSD_BOOTSTRAP_FLAG=` (empty) on subsequent runs

---

## 6. Outstanding Questions

### Q1: compose-project-name collision
VRSC mainnet uses `COMPOSE_PROJECT_NAME=mains_blue`. VRSCTEST compose has `COMPOSE_PROJECT_NAME=dev199`. What should the compose project name for VRSCTEST be? Options:
- `mains_blue` (same project, different network — likely breaks existing naming)
- `testnet` / `vrsctest`
- `dev200`

### Q2: docker-verusd repo changes
The `vrsctest/` dir in `docker-verusd` needs the fixes listed in §2. Who applies these before running the playbooks, or should the playbooks fix them idempotently?

### Q3: Verus image tag
Should VRSCTEST pin to the same tagged version as production (`buildwithdreams/verusd:1.2.16`), or always use `latest`? VRSC mainnet resolves the tag dynamically from GitHub releases.

### Q4: PBaaS fields in VRSC.conf
The existing `data_dir/sample.conf` has PBaaS-specific fields (`launchsystemid`, `parentid`, `ac_algo`, etc.). Is a plain VRSCTEST testnet config needed, or is the sample sufficient as-is?
