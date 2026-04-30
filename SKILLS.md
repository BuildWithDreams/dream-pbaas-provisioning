# Skills

This repo contains **two forms of documentation** that should always stay in sync:

## `SKILL.md` — Hermes Agent Skill

`SKILL.md` in the repo root is the canonical skill document for the Hermes AI agent framework. It is:

- The **source of truth** for the agent's knowledge of this project
- **Embedded in the repo** so documentation and code cannot drift apart
- Referenced from `~/.hermes/skills/ansible-provisioning/` as a local skill (sourced from `SKILL.md` here)

### Skill Architecture

```
BuildWithDreams/dream-pbaas-provisioning/
├── SKILL.md          ← canonical skill (here, in the repo)
├── playbooks/
├── group_vars/
└── ...

~/.hermes/skills/
└── ansible-provisioning/   → sourced from ~/dream-pbaas-provisioning/SKILL.md
```

**Why embedded in the repo and not in the skills hub?**
- The skill documents the infrastructure code; keeping them together prevents drift
- Changes to playbooks, variables, or provisioning steps are reflected immediately in the skill
- A single clone gives the agent everything it needs
- Auditable via git history — who changed what and why
- Secrets scan CI runs on every push, preventing credential leaks
- Skills hub publishing happens only after workflow is verified

**Workflow:** playbook first → skill update after verification → publish to hub when stable

## `README.md` — Human Documentation

The human-facing setup guide lives in `README.md` and should contain only what a human operator needs: prerequisites, configuration steps, playbook ordering.

## Keeping Them in Sync

When making changes to the project:
1. Update the playbook or variable
2. Update `SKILL.md` with the change
3. Update `README.md` if the human-facing steps changed
4. Commit together — they form one logical change

## Secrets Hygiene

Credentials live in `group_vars/production-local.yml` (gitignored). `production.yml` contains only placeholders. CI runs a secrets scan on every push to block accidental credential commits. See `.github/workflows/secrets-scan.yml`.
