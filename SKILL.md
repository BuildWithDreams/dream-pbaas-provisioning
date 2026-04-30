---
name: ansible-provisioning-workflow
description: Ansible playbook-driven provisioning of remote VPS infrastructure from a local control node to Ubuntu 24.04 targets. Covers playbook structure, variable conventions, privilege escalation, and critical gotchas discovered through trial and error.
version: 2.0.0
tags: [ansible, devops, provisioning, infrastructure]
related_skills: [docker-verusd]
---

# Ansible Provisioning Workflow

Ansible playbook-driven infrastructure provisioning — from a local control node to remote Ubuntu 24.04 targets.

## Philosophy

This is a **self-documenting, repeatable Autonomous Infrastructure model**:

- **No manual operations** — If it can't be automated, it shouldn't exist in this repo
- **Every action is a playbook** — One-off SSH commands don't survive beyond the session
- **Secrets are variables, not constants** — Target IPs, usernames, keys live in `group_vars/production.yml`, never hardcoded in playbooks
- **Reproducible by anyone** — Clone, fill in `group_vars/production.yml`, run the playbooks

## File Tree

```
dream-pbaas-provisioning/
├── README.md              # Documentation + founding principles + troubleshooting
├── ansible.cfg            # Ansible configuration
├── inventory.ini          # ⚠️ Replace YOUR_TARGET_IP before running
├── playbooks/
│   ├── 00-ping.yml       # Connectivity verification (run first)
│   ├── 01-docker.yml      # Docker installation
│   ├── 02-clone-repos.yml # Clone repositories
│   └── 03-docker-networks.yml # Create Docker networks
└── group_vars/
    └── production.yml     # ⚠️ All secrets: target IP, SSH user, SSH key
```

## Setup

```bash
# 1. Install Ansible on control node
pip install ansible --break-system-packages

# 2. Edit configuration
#    - inventory.ini: replace YOUR_TARGET_IP
#    - group_vars/production.yml: set target IP, SSH user, SSH key path

# 3. Run playbooks in order
cd dream-pbaas-provisioning
ansible-playbook -i inventory.ini playbooks/00-ping.yml   # verify connectivity
ansible-playbook -i inventory.ini playbooks/01-docker.yml  # install Docker
ansible-playbook -i inventory.ini playbooks/02-clone-repos.yml  # clone repos
ansible-playbook -i inventory.ini playbooks/03-docker-networks.yml # create networks
```

## Configuration

All target-specific values in `group_vars/production.yml`:

```yaml
# ⚠️ EDIT THESE FOR YOUR DEPLOYMENT
target_host: YOUR_TARGET_IP
ansible_user: YOUR_SSH_USER
ansible_ssh_private_key_file: ~/.ssh/YOUR_SSH_KEY

docker_users:
  - YOUR_SSH_USER
```

`inventory.ini` references `{{ target_host }}` — set once in `group_vars/production.yml`.

## Playbook Structure

Each playbook is self-contained and idempotent:
- `become: true` for privilege escalation (package install, docker, network creation)
- `become: false` for read-only operations (git clone)
- Variables from `group_vars/production.yml` — no hardcoded values in playbooks

## Critical Gotchas (Trial and Error)

### `~` does NOT expand under sudo

**Error:** `bash: ~user/path/to/script: No such file or directory`

**Cause:** When Ansible runs a shell task with `become: true`, the shell sees `~` literally. It does NOT expand to the user's home directory.

**Fix:** Always use absolute paths:
```yaml
# Wrong — fails under sudo
cmd: bash "~{{ ansible_user }}/docker-verusd/infrastructure/init_network.sh"

# Correct — always expands regardless of sudo
cmd: bash "/home/{{ ansible_user }}/docker-verusd/infrastructure/init_network.sh"
```

### Files created as root when become:true

**Cause:** With `become: true`, Ansible operates as root for ALL file operations, including `copy`, `template`, and `file` tasks. The target user cannot read files written by root.

**Fix:** Always specify `owner` and `group`:
```yaml
- ansible.builtin.copy:
    content: |
      DOCKER_NETWORK_SUBNET={{ item.subnet }}
    dest: "/home/{{ ansible_user }}/infrastructure/.env.{{ item.name }}"
    owner: "{{ ansible_user }}"   # must match ansible_user
    group: "{{ ansible_user }}"
    mode: '0644'

- ansible.builtin.file:
    path: "/home/{{ ansible_user }}/script.sh"
    mode: '0755'
    owner: "{{ ansible_user }}"
    group: "{{ ansible_user }}"
```

### Template file not found

**Error:** `Could not find or access 'template.j2'`

**Cause:** Ansible's `template` module searches relative to the playbook directory (`<playbook_dir>/templates/`), not the project root or `ansible.cfg` directory.

**Fix:** Either:
1. Place templates in `playbooks/templates/` alongside the playbooks, OR
2. Use `ansible.builtin.copy` with inline `content:` — avoids path issues entirely:
```yaml
# Preferred — no template file needed
- ansible.builtin.copy:
    content: |
      DOCKER_NETWORK_SUBNET={{ item.subnet }}
      BRIDGE_CUSTOM_NAME={{ item.bridge_suffix }}
      DOCKER_NETWORK_NAME={{ item.name }}
    dest: "/home/{{ ansible_user }}/infrastructure/.env.{{ item.name }}"
    owner: "{{ ansible_user }}"
    group: "{{ ansible_user }}"
    mode: '0644'
```

### Docker network inspect format string conflicts with Jinja2

**Error:** `Syntax error in template: unexpected '.'`

**Cause:** Go template syntax (`{{.Name}}`, `{{range .IPAM.Config}}`) in `--format` flags looks like Jinja2 to Ansible's template engine when used inside a Jinja2 expression.

**Fix:** Use `ansible.builtin.command` (not `shell`) and quote the format string so Jinja2 doesn't parse the Go template syntax:
```yaml
# Use command (not shell) with quoted format string
- ansible.builtin.command:
    cmd: "docker network inspect {{ item.name }} --format 'Name={{.Name}} Subnet={{range .IPAM.Config}}{{.Subnet}}{{end}}'"
  register: result
  changed_when: false
```

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `community.general.yaml` callback removed | `ansible.cfg`: `callbacks_enabled = timer, profile_tasks, ansible.builtin.default` + `result_format = yaml` |
| `gather_subset: minimal` invalid | Remove parameter, use default gather |
| SSH host key not in known_hosts | `ssh-keyscan YOUR_TARGET_IP >> ~/.ssh/known_hosts` |
| SSH key permission denied | `chmod 600 ~/.ssh/YOUR_SSH_KEY` |
| `ansible.cfg` path mismatch | Use `-i` flag with full inventory path |
| `INJECT_FACTS_AS_VARS` deprecation | Add `inject_facts_as_vars = False` to `ansible.cfg` |
| Variable `ansible_*` prefix deprecation | Use `ansible_facts["key"]` |
| SCP/rsync blocked by security scan | Use SFTP `put` command for file sync |
| `~` expands to wrong path under sudo | Use absolute path `/home/{{ ansible_user }}/...` |
| Files created as root, not target user | Add `owner/group` to `copy`, `template`, `file` tasks |
| Template file not found | Use `ansible.builtin.copy` with inline `content:` instead |
| Go template syntax in docker inspect conflicts with Jinja2 | Use `ansible.builtin.command` with quoted format string |

## Key Lessons

### Hardcode Ubuntu codename
For idempotent Docker installation, hardcode `noble` instead of `{{ ansible_distribution_release }}`:
```yaml
repo: "deb [arch=amd64 signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu noble stable"
```

### Idempotent network creation
Use `creates:` to make network creation idempotent:
```yaml
- ansible.builtin.shell:
    cmd: bash "/path/to/init_network.sh" "{{ env_file }}"
    creates: "{{ network_name }}"   # skips if network exists
```

### become:true is all-or-nothing
`become: true` on a task or play means ALL operations run as root. To mix:
```yaml
# Root for system operations
- name: Install packages
  become: true
  ansible.builtin.apt:
    name: docker-ce

# User for file operations — override at task level
- name: Create user file
  become: false   # explicitly disable become
  ansible.builtin.copy:
    content: "..."
    dest: "/home/{{ ansible_user }}/file"
```

## Secrets Management

### NEVER commit real credentials to git

The IP address, SSH user, and SSH key paths for target hosts are private. Use a separate `production-local.yml` file:

```
group_vars/
├── production.yml        # placeholders only — SAFE to push to git
└── production-local.yml # real values — NEVER push, add to .gitignore
```

```yaml
# group_vars/production-local.yml — DO NOT COMMIT
target_host: YOUR_TARGET_IP
ansible_user: YOUR_SSH_USER
ansible_ssh_private_key_file: ~/.ssh/YOUR_SSH_KEY
# ... rest of real credentials
```

To use real credentials when running playbooks:
```bash
ansible-playbook -i inventory.ini playbooks/00-ping.yml -e @group_vars/production-local.yml
```

The `.gitignore` in this repo excludes `production-local.yml` and similar files. Always verify with `git status` before pushing.

- `BuildWithDreams/dream-pbaas-provisioning` — Ansible provisioning playbooks (this blueprint)
- `BuildWithDreams/docker-verusd` — Dockerized Verus blockchain node repo
