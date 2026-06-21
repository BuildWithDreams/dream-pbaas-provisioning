"""
CLI entry points for LangGraph provisioning graphs.

Usage::

    python -m langgraph.cli sync-status --chain vrsctest
    python -m langgraph.cli sync-status                      (all chains)
"""

from __future__ import annotations

import argparse
import json
import sys

from .state import Chain, SyncStatusInput
from .graphs.sync_status import run_sync_status


def sync_status_main(argv: list[str] | None = None) -> int:
    """
    CLI entry point for the sync-status graph.

    Returns exit code 0 on success, 1 on failure.
    """
    parser = argparse.ArgumentParser(
        prog="lg-sync-status",
        description="Check chain sync status via Ansible playbook",
    )
    parser.add_argument(
        "--chain",
        type=str,
        default=None,
        help="Chain to check (vrsc, vrsctest, vdex). Default: all VRSC+vDEX",
    )
    parser.add_argument(
        "--inventory",
        type=str,
        default="inventory.ini",
        help="Path to Ansible inventory (relative to provisioning root)",
    )
    parser.add_argument(
        "--target",
        type=str,
        default="production",
        help="Ansible host group (default: production)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output structured JSON instead of human-readable summary",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Print intermediate state details",
    )

    args = parser.parse_args(argv)

    # Resolve chain
    chain: Chain | None = None
    if args.chain:
        try:
            chain = Chain(args.chain.lower())
        except ValueError:
            print(f"Unsupported chain: {args.chain}", file=sys.stderr)
            return 1

    inp = SyncStatusInput(
        target=args.target,
        chain=chain,
        inventory=args.inventory,
    )

    result = run_sync_status(inp)

    # Helper: access both dict (LangGraph invoke) and model (test mock) results
    def _s(key: str, default=None):
        return result.get(key, default) if isinstance(result, dict) else getattr(result, key, default)

    if args.json:
        chains = _s("chains", {})
        output = {
            "chains": {
                name: c.model_dump() if hasattr(c, "model_dump") else c
                for name, c in chains.items()
            },
            "summary": _s("summary"),
            "errors": _s("playbook_errors", []),
            "node_results": {
                k: v.value if hasattr(v, "value") else v
                for k, v in _s("node_results", {}).items()
            },
        }
        print(json.dumps(output, indent=2))
    else:
        print(_s("summary") or "No output.")

    # Exit code: 0 if no failures, 1 if any chain has issues
    chains = _s("chains", {})
    any_issues = any(
        _get_status(c) in ("behind", "offline", "unknown")
        for c in chains.values()
    )
    return 1 if any_issues or _s("playbook_errors") else 0


def _get_status(c: object) -> str:
    """Get chain status string from either a ChainStatus model or a dict."""
    if isinstance(c, dict):
        return c.get("status", "unknown")
    return c.status.value if c.status else "unknown"


def idcreate_deploy_main(argv: list[str] | None = None) -> int:
    """Placeholder for v2 CLI entry point."""
    print("idcreate-deploy graph not yet implemented (planned for v2).", file=sys.stderr)
    return 1


if __name__ == "__main__":
    # Determine which subcommand was invoked
    if len(sys.argv) > 1 and sys.argv[1] in ("sync-status",):
        cmd = sys.argv.pop(1)
        if cmd == "sync-status":
            sys.exit(sync_status_main())
    # Default: try sync-status
    sys.exit(sync_status_main())