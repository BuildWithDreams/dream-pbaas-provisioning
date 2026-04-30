# SPEC: svc-idcreate — Source of Funds Configuration

**Date:** 2026-04-30
**Status:** Draft — pending operator approval
**Repo:** `BuildWithDreams/dream-pbaas-provisioning`
**Branch:** `feature/idcreate-source-of-funds`

---

## 1. Purpose

Set the `SOURCE_OF_FUNDS` R-address in the `svc-idcreate` `.env` and force-restart the running containers so the new value is picked up at runtime.

This is the companion playbook to `43-idcreate-add-api-key.yml` — both manage operator-supplied secrets that live in the `.env` file.

---

## 2. Background

The `svc-idcreate` service (provisioning + API + worker) reads configuration from `~/svc-idcreate/.env`. The `SOURCE_OF_FUNDS` variable defines the R-address that funds the Z-address generation for identity registrations. It is set at deploy time and can be updated post-deployment by editing `.env` and restarting the containers.

The variable is already present in the `env.sample` that was copied to `.env` during `41-idcreate-deploy.yml`. This playbook populates it with an operator-supplied R-address and restarts the stack.

---

## 3. Playbook Design

### Playbook: `44-idcreate-source-of-funds.yml`

| Property | Value |
|---|---|
| Number | `44` |
| Purpose | Set `SOURCE_OF_FUNDS` in `.env` and force-restart running containers |
| Template | Mirrors `43-idcreate-add-api-key.yml` |
| Idempotent | Yes — safe to re-run with a new address; old value is replaced |

#### Variables

| Variable | Source | Description |
|---|---|---|
| `source_of_funds_address` | Extra var (`-e`) | R-address provided by operator |
| `idcreate_path` | Hardcoded | `/home/{{ ansible_user }}/svc-idcreate` |
| `compose_project` | Hardcoded | `dev200_idcreate` |

#### Run Command

```bash
ansible-playbook -i inventory.ini playbooks/44-idcreate-source-of-funds.yml \
  -e "source_of_funds_address=RXXXXXXXXXXXXXXXXXXXXXXXX"
```

#### Steps

1. **Validate input** — verify `source_of_funds_address` is non-empty (Ansible `assert`)
2. **Check `.env` exists** — fail with a helpful message if `41-idcreate-deploy.yml` has not been run yet
3. **Update `.env`** — use `lineinfile` with `regexp` anchored to `^SOURCE_OF_FUNDS=` to replace the existing value (or insert if absent)
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
| `docker exec <container> export SOURCE_OF_FUNDS=…` | Ephemeral; lost on restart |
| Edit `docker-compose.yml` to add `environment:` block | Requires rewriting compose file; `env_file` approach is cleaner |

---

## 6. Error Handling

| Condition | Result |
|---|---|
| `source_of_funds_address` not provided | Ansible assert fails with helpful message before any remote changes |
| `.env` not found | Play fails with message pointing to run `41-idcreate-deploy.yml` first |
| Containers already stopped | `up -d` starts them fresh; `force-recreate` is harmless when containers are absent |

---

## 7. Playbook Content

```yaml
# Playbook: 44-idcreate-source-of-funds.yml
# Purpose: Set SOURCE_OF_FUNDS in svc-idcreate .env and force-restart the stack.
# Run with: ansible-playbook -i inventory.ini playbooks/44-idcreate-source-of-funds.yml
#           -e "source_of_funds_address=RXXXXXXXXXXXXXXXXXXXXXXXX"
---
- name: Set SOURCE_OF_FUNDS for svc-idcreate
  hosts: production
  become: false
  vars:
    idcreate_path: "/home/{{ ansible_user }}/svc-idcreate"
    compose_project: "dev200_idcreate"

  tasks:
    # ── 1. Validate input ──────────────────────────────────────────────────────
    - name: Require source_of_funds_address
      ansible.builtin.assert:
        that:
          - source_of_funds_address | length > 0
        fail_msg: "source_of_funds_address is required. Run with: -e 'source_of_funds_address=Rxxx...'"

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

    # ── 3. Write SOURCE_OF_FUNDS to .env ──────────────────────────────────────
    - name: Set SOURCE_OF_FUNDS in .env
      ansible.builtin.lineinfile:
        path: "{{ idcreate_path }}/.env"
        regexp: '^SOURCE_OF_FUNDS='
        line: 'SOURCE_OF_FUNDS="{{ source_of_funds_address }}"'
        state: present
      register: sof_written

    - name: Confirm value written
      ansible.builtin.debug:
        msg: |
          SOURCE_OF_FUNDS written to {{ idcreate_path }}/.env
          Value: {{ source_of_funds_address }}

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
          SOURCE_OF_FUNDS updated and containers restarted:
            .env path       → {{ idcreate_path }}/.env
            SOURCE_OF_FUNDS → {{ source_of_funds_address }}
            compose project → {{ compose_project }}
            api container   → {{ compose_project }}-api-1
            worker container → {{ compose_project }}-worker-1
```

---

## 8. Acceptance Criteria

- [ ] Running the playbook with a valid R-address updates `SOURCE_OF_FUNDS=` in `~/svc-idcreate/.env`
- [ ] Running the playbook when `SOURCE_OF_FUNDS` is already set replaces the old value (idempotent)
- [ ] Both containers (`api-1`, `worker-1`) are restarted and `Up` after the playbook completes
- [ ] Play fails with a clear message if `.env` does not exist
- [ ] Play fails with a clear message if `source_of_funds_address` is not provided
- [ ] No manual SSH commands required
