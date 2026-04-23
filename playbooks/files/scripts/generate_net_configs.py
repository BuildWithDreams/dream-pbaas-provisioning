#!/usr/bin/env python3
"""Parse env.sample files and generate .env.{network} files + YAML group_vars."""
import re, os, sys

CHAINS = [
    ("mainnet",  "mainnet/env.sample"),
    ("varrr",    "pbaas/varrr/env.sample"),
    ("vdex",     "pbaas/vdex/env.sample"),
    ("chips",    "pbaas/chips/env.sample"),
    ("vrsctest", "vrsctest/env.sample"),
]

def parse_env(path):
    vals = {}
    if os.path.exists(path):
        for line in open(path):
            m = re.match(r'^([A-Z_]+)=(.*)$', line.strip())
            if m:
                vals[m.group(1)] = m.group(2).strip()
    return vals

def derive_bridge(subnet):
    """SP + first3octets-of-subnet .1 with dots removed.
    e.g. 10.201.0.0/24 → 10.201.0.1 → SP1020101
         192.168.5.0/24 → 192.168.5.1 → SP19216851
    """
    clean = re.sub(r'/.*', '', subnet)
    octets = clean.split('.')
    gateway = f"{octets[0]}.{octets[1]}.{octets[2]}.1"
    return "SP" + gateway.replace('.', '')

def main():
    base = sys.argv[1]
    infra = sys.argv[2]
    os.makedirs(infra, exist_ok=True)

    yaml_lines = ["verus_networks:"]
    for chain_name, rel in CHAINS:
        path = os.path.join(base, rel)
        vals = parse_env(path)
        subnet  = vals.get('DOCKER_NETWORK_SUBNET', '')
        netname = vals.get('DOCKER_NETWORK_NAME', '')
        bridge  = vals.get('BRIDGE_CUSTOM_NAME', '')
        if not bridge and subnet:
            bridge = derive_bridge(subnet)
        if netname:
            with open(os.path.join(infra, f".env.{netname}"), 'w') as f:
                f.write(f"DOCKER_NETWORK_SUBNET={subnet}\nBRIDGE_CUSTOM_NAME={bridge}\nDOCKER_NETWORK_NAME={netname}\n")
        yaml_lines.append(f"  - name: {netname}")
        yaml_lines.append(f"    subnet: {subnet}")
        yaml_lines.append(f"    bridge_suffix: {bridge}")
        print(f"CHAIN={netname} SUBNET={subnet} BRIDGE={bridge}")

    with open(os.path.join(infra, ".env.verus_networks.yml"), 'w') as f:
        f.write('\n'.join(yaml_lines) + '\n')

if __name__ == "__main__":
    main()
