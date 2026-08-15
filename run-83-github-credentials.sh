#!/usr/bin/env bash
# Run 83-github-credentials-install.yml, sourcing the token from the LOCAL gh
# config (the same token that authenticates this machine as dream-hermes-agent).
# Avoids ever typing the PAT on a command line (shell history) — it flows via
# ansible extra var from the config read below.
set -euo pipefail

TOKEN="$(python3 -c "
import yaml, os
cfg = yaml.safe_load(open(os.path.expanduser('~/.config/gh/hosts.yml')))
print(cfg['github.com']['oauth_token'])
")"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"
ansible-playbook -i inventory.ini playbooks/83-github-credentials-install.yml \
  -e "github_token=${TOKEN}" "$@"
