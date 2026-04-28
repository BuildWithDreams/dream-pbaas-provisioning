# SPEC: VRSCTEST Testnet Node Provisioning

## Status
**Ready for implementation.** All open questions resolved (see §6).

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

**Playbook: `03-docker-networks.yml`** (augmented)
- Add `net-vrsctest` entry to `verus_networks` in `group_vars/production.yml`
- Or better: add to source `env.sample` in `docker-verusd/infrastructure/` and regenerate via `02-generate-env-files.yml`
- The network create loop already handles it — no new playbook needed

---

## 2. docker-verusd Files (vrsctest/ dir)

> ✅ docker-verusd `feature/vrsctest` branch has been updated. All changes are committed and pushed.

### `vrsctest/docker-compose.yml`

| Field | Value |
|---|---|
| `image` | `buildwithdreams/verusd:${VERUSD_IMAGE_TAG}` |
| `command` | `verusd -chain=VRSCTEST ${VERUSD_BOOTSTRAP_FLAG}` |
| `volumes` | `./data_dir:/root/.komodo/VRSCTEST` |
| `network` | `pbaas_network` (external: `net-vrsctest`) |
| `ports` | `127.0.0.1:${LOCAL_RPC_PORT}:${VERUSD_RPC_PORT}` |

### `vrsctest/env.sample`

| Field | Value |
|---|---|
| `COMPOSE_PROJECT_NAME` | `dev200` |
| `DOCKER_NETWORK_SUBNET` | `10.200.0.0/24` |
| `BRIDGE_CUSTOM_NAME` | `SP1020001` |
| `DOCKER_NETWORK_NAME` | `net-vrsctest` |
| `VERUSD_IPV4` | `10.200.0.11` |
| `VERUSD_IMAGE_TAG` | `1.2.16` (pinned) |

### `vrsctest/data_dir/`

Empty. No `sample.conf` or `VRSC.conf` committed — verusd generates `VRSCTEST.conf` on first start.

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
| **image tag** | Fetch from GitHub releases | Read `VERUSD_IMAGE_TAG` from `.env` (pinned: `1.2.16`) |

> Unlike mainnet, VRSCTEST does not fetch the latest release tag — it uses the pinned value from `env.sample`.

**Steps:**
1. Read `.env` → extract `DOCKER_NETWORK_NAME` and `VERUSD_IMAGE_TAG`
2. Verify `net-vrsctest` Docker network exists (fail if not)
3. `source .env && docker compose pull && docker compose up -d`
4. Run container check script to verify health

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

## 6. Resolved Decisions

| Q | Decision |
|---|---|
| compose-project-name | `dev200` |
| docker-verusd repo | Fixed on `feature/vrsctest` branch — committed and pushed |
| Image tag | Pinned to `1.2.16` via `VERUSD_IMAGE_TAG` env var |
| VRSC.conf | No pre-generated config — verusd generates `VRSCTEST.conf` on first start |
