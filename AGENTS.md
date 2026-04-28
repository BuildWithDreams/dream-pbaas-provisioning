# Agent Operating Principles

## Core Rule: Playbook-First DevOps

Every remote operation MUST go through a playbook before any other method.

1. **Check playbooks first** — `~/provisioning/playbooks/` and `~/provisioning/repos/dream-pbaas-provisioning/playbooks/`
2. **Run the playbook** — `ansible-playbook -i ~/provisioning/inventory.ini playbooks/<n>-*.yml`
3. **If no playbook exists:**
   - **Stop.** Do not proceed with raw SSH or manual commands.
   - **Notify the operator** in the current channel with: what task requires manual work, why no playbook exists, and what the desired outcome is.
   - **Wait for express consent** before creating any GitHub issue.
   - When proposing a GitHub issue, **sanitize all sensitive data** — no IP addresses, usernames, hostnames, keys, or server-specific identifiers.
   - Submit issue only after the operator approves the sanitized content.

## Two-Agent Architecture

Every remote operation uses a **planner** + **executor** pattern. This enforces the playbook-first rule architecturally — not just by memory or instruction.

### Roles

| Agent | Role | What it does |
|---|---|---|
| **Planner (main agent)** | Receives requests, checks playbooks, handles consent, creates issues | All reasoning, gap detection, operator communication |
| **Executor (sub-agent)** | `role='leaf'`, `toolsets=['terminal']` only | Runs only the `ansible-playbook` command it receives — nothing else |

### Executor Constraints (hard-coded, non-negotiable)

- Cannot call `delegate_task` — `role='leaf'` enforces this
- Only `terminal` tool available — no raw SSH, no browser, no file write outside playbook context
- Goal specifies exact playbook command to run
- If no playbook exists → executor cannot act, must return to planner

### Workflow

```
Operator request
    ↓
Planner: checks playbooks
    ↓
  [Playbook exists?] ──no──→ Notify operator, create issue (with consent), wait
    ↓ yes
Spawn executor sub-agent
  goal: ansible-playbook -i ~/provisioning/inventory.ini playbooks/<n>-*.yml
  role: leaf
  toolsets: ['terminal']
    ↓
Executor: runs command, returns output
    ↓
Planner: surfaces results to operator
```

### Spawning the Executor

```python
delegate_task(
    goal="ansible-playbook -i ~/provisioning/inventory.ini ~/provisioning/repos/dream-pbaas-provisioning/playbooks/<playbook>.yml",
    context="Provisioning repo: ~/provisioning/repos/dream-pbaas-provisioning/\nInventory: ~/provisioning/inventory.ini\nHosts: production\n\nRun this exact playbook and return the PLAY RECAP output.",
    tasks=[{
        "goal": "ansible-playbook -i ~/provisioning/inventory.ini ~/provisioning/repos/dream-pbaas-provisioning/playbooks/<playbook>.yml",
        "context": "Run this exact command. No modifications. No other operations.",
        "role": "leaf",
        "toolsets": ["terminal"]
    }]
)
```

## Sensitive Data — Never Post

- IP addresses, hostnames, usernames
- SSH keys, credentials, tokens
- Container names, network details tied to specific infrastructure

## Why This Matters

This repo exists to build an idempotent, playbook-driven infrastructure model. Manual work without a gap issue creates knowledge that lives only in one session. Every gap captured is a stronger playbook library for every future operator.
