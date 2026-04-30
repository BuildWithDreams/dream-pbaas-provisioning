# SPEC: svc-idcreate — REGISTRAR_ALLOWED_PARENTS Configuration

**Date:** 2026-04-30
**Status:** Draft — pending operator approval
**Repo:** `BuildWithDreams/dream-pbaas-provisioning`
**Branch:** `feature/idcreate-allowed-parents`

---

## 1. Purpose

Set the `REGISTRAR_ALLOWED_PARENTS` currency ID list in the `svc-idcreate` `.env` and force-restart the running containers so the new value is picked up at runtime.

---

## 2. Background

The `svc-idcreate` service (provisioning + API + worker) reads configuration from `~/svc-idcreate/.env`. The `REGISTRAR_ALLOWED_PARENTS` variable defines which Verus chain currencies the registrar will accept as identity parents. It is set at deploy time and can be updated post-deployment by editing `.env` and restarting the containers.

Values are currency IDs — on VRSC mainnet these are names like `VRSC`; on PBaaS chains they are hex string IDs. The special keyword `this` refers to the chain itself.

The variable is already present in the `env.sample` that was copied to `.env` during `41-idcreate-deploy.yml`. This playbook populates it with an operator-supplied currency ID list and restarts the stack.

---

## 3. Playbook Design

### Playbook: `46-idcreate-allowed-parents.yml`

| Property | Value |
|---|---|
| Number | `46` |
| Purpose | Set `REGISTRAR_ALLOWED_PARENTS` in `.env` and force-restart running containers |
| Template | Mirrors `44-idcreate-source-of-funds.yml` |
| Idempotent | Yes — safe to re-run with a new list; old value is replaced |

#### Variables

| Variable | Source | Description |
|---|---|---|
| `currency_ids` | Extra var (`-e`) | Comma-separated list of currency IDs (e.g. `VRSC,RVSR` or hex IDs) |
| `idcreate_path` | Hardcoded | `/home/{{ ansible_user }}/svc-idcreate` |
| `compose_project` | Hardcoded | `dev200_idcreate` |

#### Run Command

```bash
ansible-playbook -i inventory.ini playbooks/46-idcreate-allowed-parents.yml \
  -e "currency_ids=VRSC,RVSR"
```

#### Steps

1. **Validate input** — verify `currency_ids` is non-empty (Ansible `assert`)
2. **Check `.env` exists** — fail with a helpful message if `41-idcreate-deploy.yml` has not been run yet
3. **Update `.env`** — use `lineinfile` with `regexp` anchored to `^REGISTRAR_ALLOWED_PARENTS=` to replace the existing value (or insert if absent)
4. **Force-restart containers** — `docker compose -p dev200_idcreate up -d --force-recreate` reads the new `.env` and recreates containers with updated env
5. **Confirm** — poll until both containers are `Up`

---

## 4. Force-Recreate vs. No-Refresh

`docker compose up -d --force-recreate` is used instead of `docker compose restart` because:
- `restart` does **not** re-read `.env` — environment is baked in at `up` time
- `up -d --force-recreate` stops the old containers and starts new ones, causing Docker Compose to re-read `.env`
- Both `api` and `worker` containers use `env_file: .env` — a recreate is required for either to pick up the new value

---

## 5. Alternative Approaches Considered

| Approach | Why Not |
|---|---|
| `docker compose stop` + `docker compose start` | Does not re-read `.env` |
| `docker compose restart` | Does not re-read `.env` |
| `docker exec <container> export REGISTRAR_ALLOWED_PARENTS=…` | Ephemeral; lost on restart |
| Edit `docker-compose.yml` to add `environment:` block | Requires rewriting compose file; `env_file` approach is cleaner |

---

## 6. Error Handling

| Condition | Result |
|---|---|
| `currency_ids` not provided | Ansible assert fails with helpful message before any remote changes |
| `.env` not found | Play fails with message pointing to run `41-idcreate-deploy.yml` first |
| Containers already stopped | `up -d` starts them fresh; `force-recreate` is harmless when containers are absent |

---

## 7. Playbook Content

```yaml
# Playbook: 46-idcreate-allowed-parents.yml
# Purpose: Set REGISTRAR_ALLOWED_PARENTS in svc-idcreate .env and force-restart the stack.
# Run with: ansible-playbook -i inventory.ini playbooks/46-idcreate-allowed-parents.yml
#           -e "currency_ids=VRSC,RVSR"
---
- name: Set REGISTRAR_ALLOWED_PARENTS for svc-idcreate
  hosts: production
  become: false
  vars:
    idcreate_path: "/home/{{ ansible_user }}/svc-idcreate"
    compose_project: "dev200_idcreate"

  tasks:
    # ── 1. Validate input ──────────────────────────────────────────────────────
    - name: Require currency_ids
      ansible.builtin.assert:
        that:
          - currency_ids | length > 0
        fail_msg: "currency_ids is required. Run with: -e 'currency_ids=VRSC,RVSR'"

    # ── 2. Verify .env exists ─────────────────────────────────────────────────
    - name: Check if .env exists
      ansible.builtin.stat:
        path: "{{ idcreate_path }}/.env"
      register: env_file_stat

    - name: Fail if .env not found
      ansible.builtin.fail:
        msg: |
          .env not found at {{ idcreate_path }}/.env.
          Run playbook 41-idcreate-deploy.yml first to create it.
      when: not env_file_stat.stat.exists

    # ── 3. Write REGISTRAR_ALLOWED_PARENTS to .env ────────────────────────────
    - name: Set REGISTRAR_ALLOWED_PARENTS in .env
      ansible.builtin.lineinfile:
        path: "{{ idcreate_path }}/.env"
        regexp: '^REGISTRAR_ALLOWED_PARENTS=.*'
        line: 'REGISTRAR_ALLOWED_PARENTS="{{ currency_ids }}"'
        state: present
      register: allowed_parents_written

    - name: Confirm value written
      ansible.builtin.debug:
        msg: |
          REGISTRAR_ALLOWED_PARENTS written to {{ idcreate_path }}/.env
          Value: {{ currency_ids }}

    # ── 4. Force-recreate containers to pick up new .env ─────────────────────
    - name: Force-recreate idcreate containers
      ansible.builtin.shell:
        cmd: "cd {{ idcreate_path }} && docker compose -p {{ compose_project }} up -d --force-recreate"
      changed_when: true
      register: compose_recreate

    # ── 5. Verify containers are Up ──────────────────────────────────────────
    - name: Wait for api container to be running
      ansible.builtin.shell:
        cmd: "docker ps 2>&1 | grep '{{ compose_project }}-api-1' | head -1 || true"
      register: api_check
      changed_when: false
      retries: 10
      delay: 3
      until: api_check.stdout | length > 0
      failed_when: false

    - name: Wait for worker container to be running
      ansible.builtin.shell:
        cmd: "docker ps 2>&1 | grep '{{ compose_project }}-worker-1' | head -1 || true"
      register: worker_check
      changed_when: false
      retries: 10
      delay: 3
      until: worker_check.stdout | length > 0
      failed_when: false

    # ── 6. Summary ────────────────────────────────────────────────────────────
    - name: Display result
      ansible.builtin.debug:
        msg: |
          REGISTRAR_ALLOWED_PARENTS updated and containers restarted:
            .env path               → {{ idcreate_path }}/.env
            REGISTRAR_ALLOWED_PARENTS → {{ currency_ids }}
            compose project         → {{ compose_project }}
            api container           → {{ compose_project }}-api-1
            worker container        → {{ compose_project }}-worker-1
```

---

## 8. Acceptance Criteria

- [ ] Running the playbook with a valid currency ID list updates `REGISTRAR_ALLOWED_PARENTS=` in `~/svc-idcreate/.env`
- [ ] Running the playbook when `REGISTRAR_ALLOWED_PARENTS` is already set replaces the old value (idempotent)
- [ ] Both containers (`api-1`, `worker-1`) are restarted and `Up` after the playbook completes
- [ ] Play fails with a clear message if `.env` does not exist
- [ ] Play fails with a clear message if `currency_ids` is not provided
- [ ] No manual SSH commands required
