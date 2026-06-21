"""
LangGraph: Sync Status Check (v1)

Runs ``15-sync-status.yml`` (or ``15b`` for VRSCTEST), parses the ASCII
table, and returns a structured status per chain.

Graph topology::

    parse_input → run_playbook → parse_output → route_status → summarize

                    ┌──────────┐       ┌──────────┐
                    │ all ok   │       │ behind   │
                    └────┬─────┘       └────┬─────┘
                         │                  │
                    ┌────▼─────┘       ┌────▼─────┐
                    │ synced   │       │ behind   │
                    └──────────┘       └──────────┘
                              ┌──────────┐
                              │ offline  │
                              └──────────┘
"""

from __future__ import annotations

import logging
from typing import Literal, TYPE_CHECKING

from langgraph.graph import END, StateGraph

from ..state import ChainStatus, NodeResult, SyncStatus, SyncStatusInput, SyncStatusState
from ..runner import extract_debug_msg, parse_sync_table, run_playbook

if TYPE_CHECKING:
    pass

log = logging.getLogger(__name__)


# ── Playbook map ───────────────────────────────────────────────────────

_PLAYBOOK_MAP: dict[str, str] = {
    "vrsc": "playbooks/15-sync-status.yml",
    "vdex": "playbooks/15-sync-status.yml",
    "vrsctest": "playbooks/15b-sync-status-vrsctest.yml",
}
"""Maps chain name to the playbook that checks it."""


# ── Nodes ──────────────────────────────────────────────────────────────


def node_parse_input(state: SyncStatusState) -> dict:
    """
    Validate input parameters. If no specific chain is requested, we run
    the VRSC+vDEX playbook (15-sync-status.yml) by default.
    """
    inp = state.input
    errors: list[str] = []

    if inp.chain and inp.chain.value not in _PLAYBOOK_MAP:
        errors.append(
            f"Unsupported chain '{inp.chain.value}' — supported: {list(_PLAYBOOK_MAP)}"
        )

    return {
        "playbook_errors": errors,
        "node_results": {
            **state.node_results,
            "parse_input": NodeResult.OK if not errors else NodeResult.FAILED,
        },
    }


def node_run_playbook(state: SyncStatusState) -> dict:
    """
    Execute the appropriate sync-status playbook.
    """
    chain = state.input.chain
    if chain:
        pb = _PLAYBOOK_MAP.get(chain.value, "playbooks/15-sync-status.yml")
    else:
        pb = "playbooks/15-sync-status.yml"

    result = run_playbook(playbook=pb, inventory=state.input.inventory)

    updates: dict = {
        "playbook_output": result.stdout,
        "playbook_rc": result.rc,
    }

    if result.failed or result.unreachable:
        updates["playbook_errors"] = state.playbook_errors + [
            f"Playbook {pb} failed (rc={result.rc}, "
            f"failed={result.failed}, unreachable={result.unreachable})"
        ]
        updates["node_results"] = {
            **state.node_results,
            "run_playbook": NodeResult.FAILED,
        }
    else:
        updates["node_results"] = {
            **state.node_results,
            "run_playbook": NodeResult.OK,
        }

    return updates


def node_parse_output(state: SyncStatusState) -> dict:
    """
    Extract the debug message table from Ansible stdout and parse it
    into per-chain status dicts.
    """
    if not state.playbook_output:
        return {
            "playbook_errors": state.playbook_errors + ["No playbook output to parse"],
            "node_results": {
                **state.node_results,
                "parse_output": NodeResult.FAILED,
            },
        }

    msg = extract_debug_msg(state.playbook_output)
    if not msg:
        return {
            "playbook_errors": state.playbook_errors
            + ["Could not extract debug msg from playbook output"],
            "node_results": {
                **state.node_results,
                "parse_output": NodeResult.FAILED,
            },
        }

    raw = parse_sync_table(msg)
    chains: dict[str, ChainStatus] = {}

    for name, data in raw.items():
        if data["offline"]:
            status = SyncStatus.OFFLINE
        elif data["gap"] == 0:
            status = SyncStatus.SYNCED
        else:
            status = SyncStatus.BEHIND

        chains[name] = ChainStatus(
            name=name,
            status=status,
            blocks=data["blocks"],
            longestchain=data["longestchain"],
            gap=data["gap"],
            peers=data["peers"],
            tls=data["tls"],
        )

    return {
        "chains": chains,
        "node_results": {
            **state.node_results,
            "parse_output": NodeResult.OK,
        },
    }


def node_summarize(state: SyncStatusState) -> dict:
    """
    Build a human-readable summary string from the per-chain statuses.
    """
    if not state.chains:
        # If there's already an error, report it
        if state.playbook_errors:
            summary = "Error: " + "; ".join(state.playbook_errors)
        else:
            summary = "No chain status data available."
        return {
            "summary": summary,
            "node_results": {
                **state.node_results,
                "summarize": NodeResult.OK,
            },
        }

    lines: list[str] = []
    all_ok = True
    chain_list = sorted(state.chains.values(), key=lambda c: c.name)

    for c in chain_list:
        if c.status == SyncStatus.SYNCED:
            lines.append(
                f"  {c.name:<10} synced     "
                f"{c.blocks:>7} / {c.longestchain:<7}  "
                f"+{c.gap} gap  {c.peers} peers/{c.tls} tls"
            )
        elif c.status == SyncStatus.BEHIND:
            all_ok = False
            lines.append(
                f"  {c.name:<10} BEHIND     "
                f"{c.blocks:>7} / {c.longestchain:<7}  "
                f"+{c.gap} gap  {c.peers} peers/{c.tls} tls"
            )
        elif c.status == SyncStatus.OFFLINE:
            all_ok = False
            lines.append(f"  {c.name:<10} OFFLINE    — daemon not reachable")

    if all_ok:
        header = "All chains synced — no gaps."
    else:
        header = "Issues detected:"

    summary = header + "\n" + "\n".join(lines)

    if state.playbook_errors:
        summary += "\n\nErrors:\n" + "\n".join(f"  - {e}" for e in state.playbook_errors)

    return {
        "summary": summary,
        "node_results": {
            **state.node_results,
            "summarize": NodeResult.OK,
        },
    }


# ── Conditional edge routers ────────────────────────────────────────────


def route_after_parse_input(
    state: SyncStatusState,
) -> Literal["run_playbook", "summarize"]:
    """If input validation fails, skip to summarize to report the error."""
    if state.playbook_errors:
        return "summarize"
    return "run_playbook"


def route_after_playbook(
    state: SyncStatusState,
) -> Literal["parse_output", "summarize"]:
    """If the playbook itself failed, skip to summarize to report the error."""
    nr = state.node_results.get("run_playbook")
    if nr == NodeResult.FAILED:
        return "summarize"
    return "parse_output"


def route_after_parse(
    state: SyncStatusState,
) -> Literal["summarize", "__end__"]:
    """If parsing failed, jump to summarize (it will report the error)."""
    nr = state.node_results.get("parse_output")
    if nr == NodeResult.FAILED:
        return "summarize"
    return "summarize"  # always summarize; parse success or failure both go there


# ── Graph construction ─────────────────────────────────────────────────


def build_sync_status_graph() -> StateGraph:
    """
    Build and return the uncompiled sync_status ``StateGraph``.

    The caller may compile it (e.g. with a checkpointer) or call it
    directly via ``graph.invoke()``.
    """
    workflow = StateGraph(state_schema=SyncStatusState)

    workflow.add_node("parse_input", node_parse_input)
    workflow.add_node("run_playbook", node_run_playbook)
    workflow.add_node("parse_output", node_parse_output)
    workflow.add_node("summarize", node_summarize)

    workflow.set_entry_point("parse_input")

    workflow.add_conditional_edges(
        "parse_input",
        route_after_parse_input,
        {"run_playbook": "run_playbook", "summarize": "summarize"},
    )
    workflow.add_conditional_edges(
        "run_playbook",
        route_after_playbook,
        {"parse_output": "parse_output", "summarize": "summarize"},
    )
    workflow.add_conditional_edges(
        "parse_output",
        route_after_parse,
        {"summarize": "summarize", END: END},
    )
    workflow.add_edge("summarize", END)

    return workflow


def run_sync_status(inp: SyncStatusInput) -> SyncStatusState:
    """
    Convenience: build, compile, and invoke the sync_status graph in one call.
    """
    graph = build_sync_status_graph()
    compiled = graph.compile()
    initial_state = SyncStatusState(input=inp)
    return compiled.invoke(initial_state)