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

## Sensitive Data — Never Post

- IP addresses, hostnames, usernames
- SSH keys, credentials, tokens
- Container names, network details tied to specific infrastructure

## Why This Matters

This repo exists to build an idempotent, playbook-driven infrastructure model. Manual work without a gap issue creates knowledge that lives only in one session. Every gap captured is a stronger playbook library for every future operator.
