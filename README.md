# Infrastructure Provisioning Blueprint

> **Philosophy:** This is not a one-off server setup. It is a self-documenting, repeatable Autonomous Infrastructure model. Every action is a playbook, every decision is codified, and future agents (or us from a fresh session) can reproduce the entire infrastructure by reading the playbooks and skills.

## Founding Principles

1. **No manual operations** — If it can't be automated, it shouldn't exist in this repo
2. **Every action is a playbook** — One-off SSH commands don't survive beyond the session they were run in
3. **Every decision is codified** — IP conventions, network topology, bootstrap logic, container configs — all in version control
4. **Secrets are variables, not constants** — Target IPs, usernames, keys live in `group_vars/production.yml`, never hardcoded in playbooks
5. **Skills are the canonical reference** — The `docker-verusd` skill reflects how things actually work, updated as the system evolves
6. **Reproducible by anyone** — Clone the repo, fill in `group_vars/production.yml`, run the playbooks — the system reproduces itself

## File Tree

```
provisioning/
├── README.md              # This file
├── ansible.cfg            # Ansible configuration
├── inventory.ini           # ⚠️ Edit YOUR_TARGET_IP before running
├── playbooks/
│   ├── 00-ping.yml       # Connectivity verification (run first)
│   ├── 01-docker.yml      # Docker installation
│   ├── 02-clone-repos.yml # Clone repositories
│   └── 03-docker-networks.yml # Create Docker networks
├── host_vars/             # (optional) host-specific overrides
│   └── YOUR_TARGET_IP.yml
└── group_vars/
    └── production.yml      # ⚠️ Edit: target IP, SSH user, SSH key path
```

## Prerequisites

- Python 3 on control node
- `pip install ansible --break-system-packages` on control node
- SSH key at the path configured in `group_vars/production.yml`
- Target user with sudo privileges on the target host

## Configuration

All configurable values live in `group_vars/production.yml`:

```yaml
# Target host IP
target_host: YOUR_TARGET_IP

# SSH connection
ansible_user: YOUR_SSH_USER
ansible_ssh_private_key_file: ~/.ssh/YOUR_SSH_KEY

# Users to add to the docker group
docker_users:
  - YOUR_SSH_USER
```

Copy the workflow by editing `group_vars/production.yml` with your own target IP,
SSH user, key path, and docker group users.

## Quick Start

```bash
# Navigate to provisioning directory
cd provisioning

# ⚠️ Step 1: Edit inventory.ini — replace YOUR_TARGET_IP
# ⚠️ Step 2: Edit group_vars/production.yml — set target IP, user, SSH key

# Verify connectivity (run this first)
ansible-playbook -i inventory.ini playbooks/00-ping.yml

# Install Docker
ansible-playbook -i inventory.ini playbooks/01-docker.yml

# Clone repositories
ansible-playbook -i inventory.ini playbooks/02-clone-repos.yml

# Create Docker networks for Verus chains
ansible-playbook -i inventory.ini playbooks/03-docker-networks.yml
```

## Playbook Naming Convention

Playbooks are numbered to indicate execution order:
- `00-*.yml` - Infrastructure verification
- `01-*.yml` - Base system setup (Docker installation)
- `02-*.yml` - Clone repositories
- `03-*.yml` - Docker networks for Verus chains

## Managed User

The target user (UID 1001) is used for all SSH operations.
It has sudo privileges on the target for package installation.

## Troubleshooting

### Issue: `~` does not expand under sudo

**Error:** `bash: ~user/path/to/script: No such file or directory`

**Cause:** When Ansible runs a shell task with `become: true` (sudo), `~` is not shell-expanded — it stays literal. The `~` works for the ansible user but not when sudo switches context.

**Fix:** Always use absolute paths in shell/command tasks:
```yaml
# Wrong — fails under sudo
cmd: bash "~{{ ansible_user }}/docker-verusd/infrastructure/init_network.sh"

# Correct — always expands
cmd: bash "/home/{{ ansible_user }}/docker-verusd/infrastructure/init_network.sh"
```

### Issue: Template file not found

**Error:** `Could not find or access 'template.j2'`

**Cause:** Ansible's `template` module searches relative to the playbook directory, not the `ansible.cfg` directory or the project root. It looks in `<playbook_dir>/templates/` first.

**Fix:** Either place templates in `playbooks/templates/` alongside the playbooks, or use `ansible.builtin.copy` with inline `content:` instead of `src:` to avoid file path issues entirely.

### Issue: Template created with wrong ownership

**Error:** Files created by `ansible.builtin.copy` or `template` are owned by `root:root` when `become: true`.

**Cause:** Privilege escalation (`become: true`) means Ansible operates as root, so all file operations write as root. The target user (e.g. `YOUR_SSH_USER`) then cannot read/modify them.

**Fix:** Add `owner` and `mode` to the task, or add a `file` task to fix ownership after creation:
```yaml
- name: Fix ownership
  ansible.builtin.file:
    path: "{{ dest }}"
    owner: "{{ ansible_user }}"
    group: "{{ ansible_user }}"
    mode: '0644'
```

### Issue: `community.general.yaml` callback plugin removed

**Error:**
```
The 'community.general.yaml' callback plugin has been removed.
The plugin has been superseded by the option `result_format=yaml`
in callback plugin ansible.builtin.default from ansible-core 2.13 onwards.
```

**Fix:** In `ansible.cfg`, replace `stdout_callback = yaml` with:
```ini
callbacks_enabled = timer, profile_tasks, ansible.builtin.default
result_format = yaml
```

### Issue: `gather_subset: minimal` is not a valid subset

**Error:**
```
Bad subset 'minimal' given to Ansible. gather_subset options allowed: all,
all_ipv4_addresses, all_ipv6_addresses, apparmor, architecture...
```

**Fix:** In `playbooks/00-ping.yml`, remove the `gather_subset` parameter
from the `ansible.builtin.setup` task. The default gather is sufficient
for basic connectivity checks.

### Issue: Ansible not installed

**Fix:**
```bash
pip install ansible --break-system-packages
```

### Issue: SSH host key not in known_hosts

**Fix:**
```bash
ssh-keyscan YOUR_TARGET_IP >> ~/.ssh/known_hosts 2>/dev/null
```

### Issue: SSH permission denied for key

**Error:**
```
Identity file ... not accessible: Permission denied
```

**Fix:** Ensure the private key is readable:
```bash
chmod 600 ~/.ssh/YOUR_SSH_KEY
```

### Issue: `ansible.cfg` path mismatch

**Error:**
```
the playbook: provisioning/playbooks/00-ping.yml could not be found
```

**Fix:** Ensure `ansible.cfg` uses relative path to inventory from the
directory where ansible-playbook is run, or use `-i` flag with the
full path to `inventory.ini`.

### Issue: `INJECT_FACTS_AS_VARS` deprecation warning

**Warning:**
```
[DEPRECATION WARNING]: INJECT_FACTS_AS_VARS default to `True` is deprecated,
top-level facts will not be auto injected after the change.
```

**Fix:** This is a deprecation warning, not an error. To silence it, add
to `ansible.cfg` under `[defaults]`:
```ini
inject_facts_as_vars = False
```

### Issue: Using `ansible_` prefix for variables

**Warning:**
```
Use `ansible_facts["fact_name"]` (no `ansible_` prefix) instead.
```

**Fix:** In playbooks, use `ansible_facts["distribution_release"]` instead
of `ansible_distribution_release`. This is a deprecation warning — works
now but will break in Ansible 2.24+. For now the playbook runs correctly
with these warnings present.
