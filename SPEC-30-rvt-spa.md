# SPEC-30: RVT SPA Deployment

**Date:** 2026-04-26
**Status:** Approved
**Repo:** `BuildWithDreams/rvt` (fork of Verus-facing Vue SPA)

---

## 1. Purpose

Deploy [BuildWithDreams/rvt](https://github.com/BuildWithDreams/rvt) — a Vue.js single-page application — on BWD server behind Caddy with TLS. The SPA makes RPC calls to display Verus data.

This is an as-is deployment from the upstream fork. Future development will happen on a fork; at that point the clone source and branch will be updated.

---

## 2. Architecture

```
Internet → Caddy (443) → rvt.buildwithdreams.com → static files on host ~/rvt/build/
```

- **Build:** `node:alpine` container runs `npm run build`, output lands in `~/rvt/build/` on the host
- **Serve:** Existing Caddy (10.201.0.10) serves `~/rvt/build/` directly via `file_server` + `try_files {path} /index.html`
- **No SPA container needed** — Caddy hosts the static files directly, avoiding a separate container for this
- **Network:** `net-vrsc-blue` (10.201.0.0/24), Caddy already on `.10`
- **Note:** Vite is configured with `outDir: 'build'` — this is the project's existing config, not a convention choice

---

## 3. Domain / DNS

- **Subdomain:** `rvt.buildwithdreams.com`
- **DNS:** A record points to `135.181.136.105` ✅ (already updated)
- **TLS:** Automatic via Caddy + Let's Encrypt (existing email: `hermesreport@verus.trading`)

---

## 4. Existing Caddyfile (for reference)

```
{ email hermesreport@verus.trading }

rpc.vrsc.buildwithdreams.com {
  reverse_proxy 10.201.0.12:37486
  tls hermesreport@verus.trading
}

qrcodes.buildwithdreams.com {
  reverse_proxy 10.201.0.13:3000
  tls hermesreport@verus.trading
}
```

New route to add:
```
rvt.buildwithdreams.com {
  root * /srv/rvt/dist
  file_server
  try_files {path} /index.html
  tls hermesreport@verus.trading
}
```

Note: Caddy serves from `/srv/rvt/dist` inside the container, which maps to `~/rvt/build` on the host via the volume mount. The `root` directive must use the **container path**, not the host path — Caddy evaluates it inside the container where the volume is mounted.

---

## 5. Playbook Inventory

### 5.1 `30-spa-rvt-clone.yml`
- Clones `https://github.com/BuildWithDreams/rvt.git` to `~/rvt`
- Idempotent: skips if directory exists, does `git pull` if already cloned
- **Requires:** nothing
- **Run:** `ansible-playbook -i inventory.ini playbooks/30-spa-rvt-clone.yml`

### 5.2 `31-spa-rvt-build.yml`
- Runs `npm run build` inside a `node:alpine` container (bind-mounts rvt dir as `/srv/app`)
- Build output lands in `~/rvt/build/` on the host (Vite's configured outDir)
- Always runs build (no skip logic — Vite is fast and stale output detection is unreliable)
- **Requires:** `30-spa-rvt-clone.yml`
- **Run:** `ansible-playbook -i inventory.ini playbooks/31-spa-rvt-build.yml`

### 5.3 `32-spa-rvt-caddy-route.yml`
- Adds `rvt.buildwithdreams.com` route block to the existing Caddyfile at `~/caddy/Caddyfile`
- Caddy serves from `/srv/rvt/dist` (container path) → `~/rvt/build` (host path) via volume mount
- Uses `file_server` + `try_files {path} /index.html` for SPA routing (vue-router history mode)
- Templates the Caddyfile atomically (writes temp file, then moves it)
- Triggers Caddy reload: `docker exec mains_blue_caddy-caddy-1 caddy reload --config /etc/caddy/Caddyfile`
- Idempotent: uses `lineinfile` / blockinfile to append route only if not already present
- **Requires:** `31-spa-rvt-build.yml` (build/ must exist)
- **Run:** `ansible-playbook -i inventory.ini playbooks/32-spa-rvt-caddy-route.yml`

---

## 6. Caddy Container Path Requirement

The Caddy container needs to read `~/rvt/dist/`. The existing Caddy deploy (playbook 28) does **not** currently bind-mount the rvt dist path. This needs to be addressed:

**Option A (preferred):** Add `~/rvt/dist` as a read-only bind mount to the Caddy container's docker-compose.yml — update playbook 28's compose template to include the volume.

**Option B:** Copy `dist/` to inside the caddy path (`/home/dream-hermes-agent/caddy/dist`) — simpler but creates a second copy to keep in sync.

**Decision needed** — recommend Option A. The Caddy compose template in playbook 28 should be updated to include:
```yaml
volumes:
  - ./Caddyfile:/etc/caddy/Caddyfile:ro
  - ./data:/data
  - /home/dream-hermes-agent/rvt/build:/srv/rvt/dist:ro
```

This must be done before playbook 32 can work. See feedback item below.

---

## 7. Out of Scope (Future Work)

- [ ] Fork RVT and update clone source to the fork
- [ ] Custom branding / theming
- [ ] Authentication / access control
- [ ] Staging environment
- [ ] ID verify service (IP .15) — separate spec
- [ ] SPA rebuilds on git push (CI/webhook trigger) — separate automation spec

---

## 8. Feedback & Open Questions

- [x] DNS updated ✅
- [x] Use Caddy alpine node to build ✅
- [x] Use existing Caddy to serve static files ✅
- [x] **Caddy volume:** Playbook 28 patched to add `~/rvt/dist:/srv/rvt/dist:ro` to Caddy compose template ✅ — no action needed, prerequisite resolved.
- [x] SPA routing Caddy config (`try_files {path} /index.html`) is included in the new route block per the template above ✅

---

## 9. Secrets / Variables

| Variable | Source | Required |
|---|---|---|
| `ansible_user` | `group_vars/production.yml` | Yes |
| `ansible_ssh_private_key_file` | `group_vars/production.yml` | Yes |
| `target_host` | `group_vars/production.yml` | Yes (already set) |

No extra `-e` flags needed. Caddy email is read from the existing Caddyfile.

---

## 10. Acceptance Criteria

- [x] `rvt.buildwithdreams.com` resolves and returns HTTP 200 with SPA content
- [x] TLS certificate auto-provisioned (Caddy handles this)
- [x] SPA routing works — deep links return the app, not 404
- [x] All playbooks idempotent — safe to re-run
- [x] No manual SSH commands required
- [x] Caddy container uses correct volume mount path (playbook 28 + 32 fixes)

