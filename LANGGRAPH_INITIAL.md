# LangGraph-Wrapped Ansible Playbooks

**Deterministic Infrastructure Operations via State Machine Orchestration**

> Status: Proposal | Date: 2026-06-21
> Source: Hermes assessment of the existing dream-pbaas-provisioning project

---

## 1. Motivation

The current Hermes-driven workflow has the agent reason over *which* playbook to run, *when*, and *with what parameters* — introducing non-determinism into operations that should be mechanical. Each Ansible playbook is itself deterministic. The non-determinism comes from the orchestration layer: sequencing, branching, parameter selection, and error handling are all LLM-decided each time.

The operator (Mylo) must stay in the loop, understand the full context as work proceeds, and correct the agent when it takes a wrong path. This is not sustainable for autonomous operations.

**LangGraph solves this by encoding the workflow as a state machine.** Given the same input, the graph always traverses the same nodes in the same order. Conditionals are explicit edges, not LLM reasoning steps.

| What it means | LangGraph | Current (Hermes agent) |
|---|---|---|
| Sequence | Baked into graph topology | Re-decided by LLM each run |
| Decision points | Explicit state checks | Open-ended LLM deliberation |
| Error handling | Structured edge to remediation | "Hmm, let me try something" |
| Operator role | Exception handler ("graph stopped at node X") | Full-time supervisor |

---

## 2. Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                      LangGraph Orchestrator                         │
│                                                                     │
│  State (Pydantic): {                                                │
│    target: "bwd",                      # remote host                │
│    chain: "vrsctest" | "vrsc",         # which chain                │
│    playbook_results: {},               # outputs from each step     │
│    flags: { cloned, built, deployed,   # decision state              │
│             routed, api_keyged },                                    │
│    errors: [],                         # failure journal            │
│    summary: ""                         # final report               │
│  }                                                                    │
│                                                                      │
│  Nodes: Each node wraps 1-2 related playbooks,                       │
│         calls ansible-playbook, parses output,                       │
│         updates state, returns next node to route to.                │
│                                                                      │
│  Edges: Conditional — based on state.flags,                          │
│         error presence, and param overrides.                         │
└──────────────────────────────────────────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────────────────────────────────────┐
│                    Ansible Execution Layer                           │
│                                                                      │
│  Each node runs the actual playbook via:                             │
│    ansible-playbook -i inventory.ini playbooks/NN-*.yml              │
│                    -e @group_vars/production-local.yml                │
│                    -e "extra_param=value"                             │
│                                                                      │
│  No SSH, no Docker — the playbook IS the executable.                 │
│  LangGraph just orchestrates playbook execution order.               │
└──────────────────────────────────────────────────────────────────────┘
```

**Core principle:** The graph never runs raw `docker` or `ssh` commands. Every action goes through a playbook. The playbook remains the source of truth for *how* to do something; LangGraph is the source of truth for *when* to do it and *what to do next*.

---

## 3. Existing Assets (What We Already Have)

### Playbooks (~85 total, numbered)

| Range | Subsystem | Example playbooks |
|-------|-----------|-------------------|
| 00-06 | **Infrastructure** | Docker install, clone repos, networks, build images, fetch params |
| 07-10 | **VRSC mainnet** | Setup, start, shutdown, hygiene |
| 07b-10b | **VRSCTEST** | Setup, start, shutdown (testnet mirrors) |
| 11-18 | **PBaaS chains** | Setup, start, shutdown, peer config, clean chainstate, sync status, RPC allowip |
| 20-29 | **RPC server + Caddy** | Deploy RPC proxy, Caddy reverse proxy, teardown |
| 30-38 | **SPA / QR codes / VRSCTEST** | Clone, build, deploy, Caddy routes, update |
| 39-47 | **idcreate VRSCTEST** | Clone, build, deploy, Caddy route, API keys, source of funds, update, restart |
| 39b-47b | **idcreate VRSC mainnet** | Same workflow, VRSC-specific params |
| 48-56 | **QR codes vDEX** | Clone, fetch WIF, configure, build, deploy, Caddy |

### SPEC Documents (7)

| File | Covers |
|------|--------|
| `SPEC-vrsctest.md` | VRSCTEST node provisioning: network, files, bootstrap logic, playbook ordering |
| `SPEC-svc-idcreate-VRSCTEST.md` | idcreate on VRSCTEST: architecture, containers, env vars, deployment order |
| `SPEC-svc-idcreate-VRSC.md` | idcreate on VRSC mainnet: same structure, VRSC-specific differences |
| `SPEC-44-idcreate-source-of-funds.md` | Source of funds parameter |
| `SPEC-46-idcreate-allowed-parents.md` | Allowed parent currencies |
| `SPEC-CADDY.md` | Caddy reverse proxy: design, routing table, playbook structure, DNS prereqs |
| `SPEC-30-rvt-spa.md` | SPA deployment |

### Runbooks (11, in `repos/operations/runbooks/`)

Jekyll/GitHub Pages format. Each is a step-by-step deployment procedure with Delegate blocks:

| Runbook | Covers |
|---------|--------|
| `sync-status.md` | Check VRSC + vDEX sync |
| `idcreate-vrsctest-deploy.md` | Full VRSCTEST idcreate deploy (cloning through Caddy route) |
| `idcreate-vrsc-deploy.md` | VRSC mainnet idcreate deploy |
| `idcreate-vrsctest-update.md` | Update existing VRSCTEST idcreate |
| `qrcodes-vrsctest-deploy.md` | QR codes VRSCTEST deploy |
| `vrsctest-rpc-server-deploy.md` | RPC server deploy on VRSCTEST |
| `vrsctest-rpcallowip.md` | Add RPC allowip for VRSCTEST |
| `idcreate-allowed-parents.md` | Configure allowed parents |
| `idcreate-source-of-funds.md` | Set source of funds |
| `listunspent.md` | List unspent transactions |

### Shared Conventions (`PLAYBOOK_CONVENTIONS.md`)

| Convention | Detail |
|------------|--------|
| Bootstrap flag logic | `chainstate+blocks exist AND debug.log has "Shutdown: done"` |
| IP octet map | `.1` gateway, `.10` Caddy, `.11` daemon, `.12` RPC, `.13` QR, `.14` idcreate |
| Compose project naming | `<network>_<color>` → `mains_blue`, `vdex_blue`, `test_blue` |
| Docker network naming | `net-<chain>-<color>` → `net-vrsc-blue`, `net-vdex-blue` |
| Data directory layout | PBaaS hex ID nested, VRSC flat |
| Known PBaaS hex IDs | vARRR `e9e109...`, vDEX `53fe39...`, CHIPS `f31536...` |

### Documented Bugs & Pitfalls (from ansible-provisioning skill)

The existing skill file catalogs ~15 hard-won bugs. The LangGraph layer should encode pre-flight checks that catch these before they happen:

1. **`None != ''` truthiness** → bootstrap detection wrongly reports clean shutdown on empty debug.log
2. **`***` → `-1` in Jinja2** → password placeholder renders as arithmetic result, not literal
3. **`{{ pg_password.stdout }}` undefined at parse time** → Jinja2 evaluates `line:` before task runs
4. **Caddy `/config/caddy` read-only** → `docker cp` fails silently; always edit host file + reload
5. **`docker compose up -d` blocks Ansible** → shell never exits; use `async: 1 poll: 0` or background
6. **Container name mismatch** → idempotency check pattern `_vdex-vdex-1$` vs real `mains_blue-vdex-1`
7. **Caddyfile corruption on re-run** → orphaned blocks, duplicate domains; remove-then-add is the correct pattern
8. **`-e @group_vars/production-local.yml` flag missing** → VRSC playbook silently deploys to VRSCTEST directory
9. **Postgres provisioning env bug** → provisioning container missing `env_file: .env` and explicit `DATABASE_URL`
10. **`REGISTRAR_API_KEYS` double quotes** → quotes become part of the value
11. **SSH key path** → `~/.ssh/dream-hermes-agent_id_25519`, not `~/.ssh/bwd`
12. **BWD images are local only** → `docker compose pull` fails with access denied; use `--no-pull`
13. **s-nomp git+ssh deps** → npm install must run on host, not inside Docker
14. **Playbook docstrings trigger secret scans** → never hardcode IPs in docstrings or comments
15. **`set_fact` with `select()` returns list in Ansible 2.16+** → use `regex_search` instead

---

## 4. Project Structure

```
dream-pbaas-provisioning/
├── playbooks/                          # Existing — untouched
├── group_vars/                         # Existing — untouched
├── inventory.ini                       # Existing — untouched
├── SPEC-*.md                           # Existing — untouched
├── LANGGRAPH_INITIAL.md                # THIS FILE
├── langgraph/                          # NEW — LangGraph orchestration
│   ├── pyproject.toml                  # deps: langgraph, pydantic, ansible-runner
│   ├── src/
│   │   ├── __init__.py
│   │   ├── runner.py                   # Shared: calls ansible-playbook, parses recap
│   │   ├── state.py                    # Pydantic state models for each graph
│   │   ├── graphs/
│   │   │   ├── __init__.py
│   │   │   ├── sync_status.py          # v1 graph
│   │   │   └── idcreate_deploy.py      # v2 graph
│   │   └── cli.py                      # CLI entry points
│   └── tests/
│       ├── test_runner.py
│       ├── test_sync_status.py
│       └── test_idcreate_deploy.py
├── repos/operations/                    # Existing runbooks — untouched
│   └── runbooks/
│       ├── sync-status.md
│       ├── idcreate-vrsctest-deploy.md
│       ├── idcreate-vrsc-deploy.md
│       └── ... (9 more)
└── .github/workflows/                   # Future: cron-driven graphs
    └── langgraph-sync-status.yml        # (example) hourly sync health
```

### Stack

| Component | Choice | Rationale |
|-----------|--------|-----------|
| Graph framework | **LangGraph** (Python SDK) | State machine with conditional edges, subgraph composition, persistence |
| State models | **Pydantic v2** | Typed, validated state per graph; serializable for persistence |
| Playbook execution | **`subprocess.run`** or **`ansible-runner`** | Prefer raw subprocess for simplicity initially; migrate to ansible-runner for richer event capture later |
| CLI | **`argparse`** (no extra dep) | `python -m langgraph.cli sync-status --chain vrsctest` |

---

## 5. Implementation Principles

| # | Principle | Rationale |
|---|-----------|-----------|
| 1 | **Playbooks are sacred** | The graph never bypasses a playbook. If a playbook doesn't exist for a step, the graph fails explicitly — it does NOT invent a raw SSH command |
| 2 | **Nodes are single-responsibility** | Each node wraps one playbook (or one small group like clone+build for atomicity). If a playbook fails, the error is captured and surfaced, not silently retried by the LLM |
| 3 | **State is explicit** | All decision state (`cloned`, `built`, `deployed`, `routed`) lives in the graph's typed state object, not in an LLM's ephemeral reasoning |
| 4 | **Output is structured** | Every graph returns a typed summary dict — not prose — suitable for CLI display, cron delivery, or downstream automation |
| 5 | **Composability** | Graphs should be usable as sub-nodes inside larger graphs later (e.g., `graph_idcreate_deploy` inside a "full VRSC infra deploy" graph) |
| 6 | **Learn from the bug log** | The ansible-provisioning skill has ~15 documented bugs. The LangGraph layer adds pre-flight checks that catch these before they happen, and structured error messages when they do |
| 7 | **Idempotency respected** | The graph calls idempotent playbooks unconditionally — they skip safely. Only expensive operations (image build, git clone) get explicit skip logic in the graph |
| 8 | **Error edges to structured handling** | Each node has an error edge to a `handle_error` or `remediate` node, not a fallback to LLM reasoning |

---

## 6. Suggested First Two Versions

### v1: Sync Status (`graph_sync_status`)

**Why this comes first:**

1. **Simple** — One playbook (`15-sync-status.yml` or `15b-sync-status-vrsctest.yml`). No branching, no preconditions, no state to manage.
2. **High frequency** — This is the most-requested operation. A deterministic "how synced are we" answer is immediately useful.
3. **Tests the infrastructure** — Gets the project scaffolded (runner, state, output format, edge routing) with minimal surface area.
4. **Cron target** — A scheduled LangGraph run that checks sync and alerts on drift is the autonomous ops MVP.

**Graph design:**

```
                    ┌──────────────┐
                    │  parse_input  │  (validate chain + host params)
                    └──────┬───────┘
                           │
                    ┌──────▼───────┐
                    │ run_sync_check│  (ansible-playbook 15-sync-status.yml
                    │              │   or 15b if vrsctest)
                    └──────┬───────┘
                           │
                    ┌──────▼───────┐
                    │ parse_results │  (extract per-chain status from output)
                    └──────┬───────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
       ┌──────▼────┐ ┌────▼─────┐ ┌────▼──────┐
       │ all_synced │ │ partial  │ │ chain_    │
       │            │ │ sync     │ │ offline   │
       └──────┬─────┘ └────┬─────┘ └────┬──────┘
              │            │            │
       ┌──────▼────┐ ┌────▼─────┐ ┌────▼──────┐
       │ summarize │ │summarize │ │ summarize  │
       │ "+0 OK"   │ │ gap + N  │ │ offline    │
       └───────────┘ └──────────┘ └───────────┘
```

**State:** `{ chain, target, blocks, tip, gap, peers, error? }`

**Output:** Structured JSON → formatted for CLI or Discord.

**Playbooks consumed:** 15-sync-status.yml, 15b-sync-status-vrsctest.yml

**Estimated size:** ~100 lines graph code, 2-3 node functions, 1 shared ansible runner helper

---

### v2: idcreate VRSCTEST Full Deploy (`graph_idcreate_deploy`)

**Why this comes second:**

1. **Well-documented** — Five SPEC files plus two detailed runbooks plus PLAYBOOK_CONVENTIONS.md section. Every decision point and gotcha is already written down.
2. **Complex enough to prove the pattern** — 6-7 sequential playbooks with multiple decision points (clone vs skip, build vs cached, .env exists vs fresh, keys already set, Caddy route present) and cross-subsystem interactions (Caddy route management).
3. **Dual-chain value** — VRSCTEST and VRSC variants differ only in parameters. A parameterized graph deploys both from the same code, proving LangGraph's abstraction power.
4. **Real production value** — This is the most complex day-to-day deployment workflow on BWD. Deterministic automation eliminates the most common source of operator drift.

**Graph design:**

```
                    ┌──────────────┐
                    │ parse_input  │  (chain, rebuild?, api_key?, source_of_funds?)
                    └──────┬───────┘
                           │
                    ┌──────▼───────┐
              ┌─────│ prereq_check │  (VRSC daemon running? network exists?
              │     └──────┬───────┘   RPC allowip set? inventory reachable?)
              │            │
              │     ┌──────▼───────┐
              │     │  clone_repo  │  (39 / 39b — idempotent, skip if already cloned)
              │     └──────┬───────┘
              │            │
              │     ┌──────▼───────┐
              │     │  build_image │  (40 / 40b — skip if cached && !rebuild)
              │     └──────┬───────┘
              │            │
              │     ┌──────▼───────┐
              │     │ deploy_stack │  (41 / 41b — full compose up, writes .env)
              │     └──────┬───────┘
              │            │
              │     ┌──────▼───────┐
              │     │  verify_pg   │  (pg_isready health check from graph)
              │     └──────┬───────┘
              │            │
              │     ┌──────▼───────┐
              │   ┌─│add_caddy_route│  (42 / 42b — idempotent, detect existing)
              │   │ └──────┬───────┘
              │   │        │
              │   │ ┌──────▼───────┐
              │   │ │ verify_https │  (curl from internet, confirm TLS)
              │   │ └──────┬───────┘
              │   │        │
              │   │ ┌──────▼───────┐
              │   │ │  gen_api_key │  (43 / 43b — skip if REGISTRAR_API_KEYS in .env)
              │   │ └──────┬───────┘
              │   │        │
              │   │ ┌──────▼───────┐
              │   │ │set_source_of_│  (44 / 44b — only if user passed address)
              │   │ │  funds       │
              │   │ └──────┬───────┘
              │   │        │
              │   │ ┌──────▼───────┐
              │   │ │restart_contain│  (47 / 47b — pick up new env vars)
              │   │ │  ers          │
              │   │ └──────┬───────┘
              │   │        │
              │   └─────┐  │
              │         │  │
              │  ┌──────▼──▼───────┐
              │  │  final_verify   │  (health + URL + worker logs)
              │  └──────┬──────────┘
              │         │
              │  ┌──────▼──────────┐
              │  │ generate_summary│  (structured deploy report)
              │  └─────────────────┘
              │
              └── Each node has an error edge to a remediation router
```

**Branching logic:**

| Node | Skip condition |
|------|----------------|
| `clone_repo` | Repo directory exists |
| `build_image` | Image exists AND `rebuild=false` |
| `deploy_stack` | Never skipped — idempotent playbook |
| `add_caddy_route` | Domain block already in Caddyfile |
| `gen_api_key` | `REGISTRAR_API_KEYS` already in `.env` |
| `set_source_of_funds` | User didn't provide `source_of_funds_address` |
| `restart_containers` | Only if API key or env vars were changed |

**Playbooks consumed:** 39, 40, 41, 42, 43, 44, 47 (or `b`-series for VRSC mainnet)

**Estimated size:** ~300 lines graph code, 8-10 node functions, 6 ansible-runner calls, 2-3 conditional branches

---

## 7. Comparison: v1 vs v2

| Aspect | v1: Sync Status | v2: idcreate Deploy |
|--------|----------------|---------------------|
| **Playbooks used** | 1 (15 / 15b) | 6-7 (39-47 / 39b-47b) |
| **Graph nodes** | 4-5 | 8-10 |
| **Decision branches** | 2 (synced / behind / offline) | 6+ (skip checks, param overrides) |
| **State complexity** | Trivial (3 fields) | Moderate (12+ fields + flags) |
| **Risk** | Very low (read-only) | Low (idempotent playbooks, graph guards re-runs) |
| **Production value** | Immediate (health monitoring) | Immediate (deployment automation) |
| **Infrastructure proof** | Validates runner, state, output | Validates branching, skip logic, error handling |
| **Cron-ready** | Yes — heartbeat + alert on drift | No — one-shot deploy only (cron would re-deploy) |

---

## 8. Future Extensions (Post v1 + v2)

| Graph | Playbooks | Complexity | When |
|-------|-----------|------------|------|
| `graph_vrsc_daemon_restart` | 10 (stop) + 07 (setup) + 08 (start) | Medium | After v2 |
| `graph_pbaas_start_stop` | 12 (clean) + 13 (start) / 14 (stop) | Medium | After daemon restart |
| `graph_idcreate_update` | 45 (pull+rebuild+restart) | Low (single playbook) | When update flow needs params |
| `graph_full_infra_bootstrap` | 00-06 chain | High (many deps) | Last — rare need |
| `graph_caddy_route_add` | 42/42b pattern (generic IP+domain) | Low | Reusable subgraph |
| `graph_sync_status_cron` | 15/15b on schedule + alert | Very low | Wraps v1 in cron |

---

## 9. Integration with Hermes Agent

Once a graph exists, Hermes calls it instead of reasoning over playbooks:

```python
# Current (non-deterministic):
# Hermes reasons: "which playbook? what params? what order?"

# Future (deterministic):
import subprocess
result = subprocess.run([
    "python3", "-m", "langgraph.cli", "idcreate-deploy",
    "--chain", "vrsctest",
    "--rebuild"
], capture_output=True, text=True)
# Parse structured JSON output from result.stdout
```

This means Hermes still handles:
- **Initial request routing** ("Mylo wants to deploy idcreate on VRSCTEST")
- **Parameter gathering** ("What source of funds address? Any API keys?")
- **Success/failure communication** ("Deploy complete, here's the URL")
- **Exception handling** ("Graph stopped at `verify_https` — Caddy route exists but cert not issued")

But the *execution* is deterministic. Hermes reads the output, doesn't choose the steps.

---

## 10. Key Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| **Ansible output parsing is fragile** | Parse `PLAY RECAP` section with regex; capture `rc` and `stdout`. Unit-test against sample outputs from real runs |
| **Playbook changes break graph** | Graphs are in same repo. When playbooks change, update related graphs in same PR |
| **LangGraph dependency adds complexity** | Keep graphs small (v1 = ~100 lines). Pure Python + subprocess — no framework magic |
| **State loss between run segments** | Graphs are single-shot (no checkpoints needed for v1/v2). State persists in-memory for the duration |
| **User expects agent to fix playbook failures** | Graph fails explicitly with structured error. Hermes can delegate a repair subagent, but the graph itself does NOT attempt self-healing — that's the boundary |

---

*Plan authored 2026-06-21 by Hermes Agent after full project assessment (70+ playbooks, 7 SPECs, 11 runbooks, PLAYBOOK_CONVENTIONS.md, and the ansible-provisioning skill containing ~15 documented bugs).*
