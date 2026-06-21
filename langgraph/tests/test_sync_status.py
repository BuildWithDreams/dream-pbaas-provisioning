"""
Tests for the sync_status LangGraph — node functions, edge routing, full invoke.

These tests mock the playbook runner so they don't need Ansible/SSH.
Integration tests that hit the real BWD server are in test_runner.py
(marked @pytest.mark.integration).
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from provisioning_langgraph.state import (
    Chain,
    ChainStatus,
    NodeResult,
    SyncStatus,
    SyncStatusInput,
    SyncStatusState,
)
from provisioning_langgraph.graphs.sync_status import (
    build_sync_status_graph,
    node_parse_input,
    node_parse_output,
    node_run_playbook,
    node_summarize,
    route_after_parse,
    route_after_parse_input,
    route_after_playbook,
    run_sync_status,
)
from provisioning_langgraph.runner import PlaybookResult

# ── Sample sync table text (as it appears in a debug msg) ──────────────

SYNCED_TABLE = (
    "╔═══════════════════════════════════════════════════════════╗\n"
    "║           PBaaS Chain Sync Status — BWD                  ║\n"
    "╠══════════════╦═══════════════╦══════════╦═══════════════╣\n"
    "║ Chain         ║ Local / Tip   ║ Gap      ║ Peers / TLS    ║\n"
    "╠══════════════╬═══════════════╬══════════╬═══════════════╣\n"
    "║ VRSC          ║ 4056739 / 4056739 ║      +0 ║   5 / 5       ║\n"
    "║ vDEX          ║ 0897765 / 0897765 ║      +0 ║   5 / 5       ║\n"
    "╚══════════════╩═══════════════╩══════════╩═══════════════╝"
)

BEHIND_TABLE = (
    "╔═══════════════════════════════════════════════════════════╗\n"
    "║           PBaaS Chain Sync Status — BWD                  ║\n"
    "╠══════════════╦═══════════════╦══════════╦═══════════════╣\n"
    "║ Chain         ║ Local / Tip   ║ Gap      ║ Peers / TLS    ║\n"
    "╠══════════════╬═══════════════╬══════════╬═══════════════╣\n"
    "║ VRSC          ║ 4056700 / 4056739 ║     -39 ║   5 / 5       ║\n"
    "║ vDEX          ║ 0897700 / 0897765 ║     -65 ║   4 / 4       ║\n"
    "╚══════════════╩═══════════════╩══════════╩═══════════════╝"
)

OFFLINE_TABLE = (
    "╔═══════════════════════════════════════════════════════════╗\n"
    "║           PBaaS Chain Sync Status — BWD                  ║\n"
    "╠══════════════╦═══════════════╦══════════╦═══════════════╣\n"
    "║ Chain         ║ Local / Tip   ║ Gap      ║ Peers / TLS    ║\n"
    "╠══════════════╬═══════════════╬══════════╬═══════════════╣\n"
    "║ VRSC          ║    offline    ║    —     ║       —        ║\n"
    "║ vDEX          ║    offline    ║    —     ║       —        ║\n"
    "╚══════════════╩═══════════════╩══════════╩═══════════════╝"
)


# ── Helper: wrap tables as Ansible-style debug output ──────────────────


def _wrap_as_playbook_output(table_text: str) -> str:
    """Wrap a sync table in the Ansible TASK [Display] format so
    extract_debug_msg can find it."""
    # Escape newlines for JSON format (like real ansible output)
    escaped = table_text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return (
        'TASK [Display sync status report] **************************************\n'
        'ok: [host] => {\n'
        f'    "msg": "{escaped}"\n'
        '}\n'
        'PLAY RECAP ************************************************************\n'
        'host : ok=5 changed=0 unreachable=0 failed=0 skipped=0 rescued=0 ignored=0\n'
    )


# ── Fixtures: default state factories ──────────────────────────────────


def make_input(**kwargs) -> SyncStatusInput:
    defaults = dict(target="production", playbook_dir="playbooks", inventory="inventory.ini")
    return SyncStatusInput(**{**defaults, **kwargs})


def make_state(**overrides) -> SyncStatusState:
    defaults = {
        "input": make_input(),
        "chains": {},
        "playbook_output": None,
        "playbook_rc": None,
        "playbook_errors": [],
        "node_results": {},
        "summary": None,
    }
    return SyncStatusState(**{**defaults, **overrides})


# ── Tests: node_parse_input ─────────────────────────────────────────────


class TestParseInput:
    def test_valid_chain(self):
        state = make_state(input=make_input(chain=Chain.VRSC))
        result = node_parse_input(state)
        assert result["playbook_errors"] == []
        assert result["node_results"]["parse_input"] == NodeResult.OK

    def test_valid_vrsctest(self):
        state = make_state(input=make_input(chain=Chain.VRSCTEST))
        result = node_parse_input(state)
        assert result["playbook_errors"] == []

    def test_no_chain(self):
        state = make_state(input=make_input(chain=None))
        result = node_parse_input(state)
        assert result["playbook_errors"] == []
        assert result["node_results"]["parse_input"] == NodeResult.OK


# ── Tests: route_after_parse_input ──────────────────────────────────────


class TestRouteParseInput:
    def test_ok_goes_to_playbook(self):
        state = make_state()
        assert route_after_parse_input(state) == "run_playbook"

    def test_errors_go_to_end(self):
        state = make_state(playbook_errors=["Something wrong"])
        assert route_after_parse_input(state) == "summarize"


# ── Tests: node_run_playbook ────────────────────────────────────────────


class TestRunPlaybook:
    @patch("provisioning_langgraph.graphs.sync_status.run_playbook")
    def test_playbook_success(self, mock_run):
        mock_run.return_value = PlaybookResult(
            rc=0,
            stdout=_wrap_as_playbook_output(SYNCED_TABLE),
            stderr="",
        )
        state = make_state(input=make_input(chain=Chain.VRSC))
        result = node_run_playbook(state)
        assert result["playbook_rc"] == 0
        assert result["node_results"]["run_playbook"] == NodeResult.OK

    @patch("provisioning_langgraph.graphs.sync_status.run_playbook")
    def test_playbook_rc_failure(self, mock_run):
        mock_run.return_value = PlaybookResult(
            rc=1,
            stdout="",
            stderr="Something broke",
            failed=True,
        )
        state = make_state(input=make_input(chain=Chain.VRSC))
        result = node_run_playbook(state)
        assert result["node_results"]["run_playbook"] == NodeResult.FAILED
        assert len(result["playbook_errors"]) > 0


# ── Tests: route_after_playbook ─────────────────────────────────────────


class TestRoutePlaybook:
    def test_ok_goes_to_parse(self):
        state = make_state(node_results={"run_playbook": NodeResult.OK})
        assert route_after_playbook(state) == "parse_output"

    def test_failed_goes_to_summarize(self):
        state = make_state(node_results={"run_playbook": NodeResult.FAILED})
        assert route_after_playbook(state) == "summarize"


# ── Tests: node_parse_output ────────────────────────────────────────────


class TestParseOutput:
    def test_parse_synced(self):
        state = make_state(playbook_output=_wrap_as_playbook_output(SYNCED_TABLE))
        result = node_parse_output(state)
        assert result["node_results"]["parse_output"] == NodeResult.OK

        chains = result["chains"]
        assert "VRSC" in chains
        assert "vDEX" in chains
        assert chains["VRSC"].status == SyncStatus.SYNCED
        assert chains["VRSC"].blocks == 4056739
        assert chains["vDEX"].status == SyncStatus.SYNCED

    def test_parse_behind(self):
        state = make_state(playbook_output=_wrap_as_playbook_output(BEHIND_TABLE))
        result = node_parse_output(state)
        assert result["node_results"]["parse_output"] == NodeResult.OK

        chains = result["chains"]
        assert chains["VRSC"].status == SyncStatus.BEHIND
        assert chains["VRSC"].gap == -39
        assert chains["vDEX"].status == SyncStatus.BEHIND

    def test_parse_offline(self):
        state = make_state(playbook_output=_wrap_as_playbook_output(OFFLINE_TABLE))
        result = node_parse_output(state)
        assert result["node_results"]["parse_output"] == NodeResult.OK

        chains = result["chains"]
        assert chains["VRSC"].status == SyncStatus.OFFLINE
        assert chains["VRSC"].blocks == 0
        assert chains["vDEX"].status == SyncStatus.OFFLINE

    def test_no_output(self):
        state = make_state(playbook_output=None)
        result = node_parse_output(state)
        assert result["node_results"]["parse_output"] == NodeResult.FAILED

    def test_empty_output(self):
        state = make_state(playbook_output="")
        result = node_parse_output(state)
        assert result["node_results"]["parse_output"] == NodeResult.FAILED


# ── Tests: route_after_parse ────────────────────────────────────────────


class TestRouteParse:
    def test_ok_goes_to_summarize(self):
        state = make_state(node_results={"parse_output": NodeResult.OK})
        assert route_after_parse(state) == "summarize"

    def test_failed_goes_to_summarize(self):
        state = make_state(node_results={"parse_output": NodeResult.FAILED})
        assert route_after_parse(state) == "summarize"


# ── Tests: node_summarize ───────────────────────────────────────────────


class TestSummarize:
    def test_all_synced(self):
        chains = {
            "VRSC": ChainStatus(name="VRSC", status=SyncStatus.SYNCED, blocks=100, longestchain=100),
            "vDEX": ChainStatus(name="vDEX", status=SyncStatus.SYNCED, blocks=50, longestchain=50),
        }
        state = make_state(chains=chains)
        result = node_summarize(state)
        assert "All chains synced" in result["summary"]
        assert "VRSC" in result["summary"]
        assert "vDEX" in result["summary"]

    def test_behind(self):
        chains = {
            "VRSC": ChainStatus(name="VRSC", status=SyncStatus.BEHIND, blocks=100, longestchain=150),
        }
        state = make_state(chains=chains)
        result = node_summarize(state)
        assert "Issues detected" in result["summary"]
        assert "BEHIND" in result["summary"]

    def test_offline(self):
        chains = {
            "vDEX": ChainStatus(name="vDEX", status=SyncStatus.OFFLINE),
        }
        state = make_state(chains=chains)
        result = node_summarize(state)
        assert "Issues detected" in result["summary"]
        assert "OFFLINE" in result["summary"]

    def test_mixed(self):
        chains = {
            "VRSC": ChainStatus(name="VRSC", status=SyncStatus.SYNCED, blocks=100, longestchain=100),
            "vDEX": ChainStatus(name="vDEX", status=SyncStatus.OFFLINE),
        }
        state = make_state(chains=chains)
        result = node_summarize(state)
        assert "Issues detected" in result["summary"]
        assert "synced" in result["summary"]
        assert "OFFLINE" in result["summary"]

    def test_no_chains(self):
        state = make_state(chains={})
        result = node_summarize(state)
        assert "No chain status" in result["summary"]

    def test_no_chains_with_errors(self):
        state = make_state(chains={}, playbook_errors=["Playbook crashed"])
        result = node_summarize(state)
        assert "Error" in result["summary"]
        assert "Playbook crashed" in result["summary"]


# ── Integration: full graph invoke (with mocked runner) ─────────────────


class TestGraphIntegration:
    @patch("provisioning_langgraph.graphs.sync_status.run_playbook")
    def test_full_sync(self, mock_run):
        """End-to-end: both chains synced."""
        mock_run.return_value = PlaybookResult(
            rc=0,
            stdout=_wrap_as_playbook_output(SYNCED_TABLE),
            stderr="",
        )
        inp = SyncStatusInput(target="production", chain=None)
        result = run_sync_status(inp)
        assert len(result["chains"]) == 2
        assert result["chains"]["VRSC"].status == SyncStatus.SYNCED
        assert result["chains"]["vDEX"].status == SyncStatus.SYNCED
        assert "All chains synced" in (result.get("summary") or "")
        assert result["playbook_errors"] == []

    @patch("provisioning_langgraph.graphs.sync_status.run_playbook")
    def test_full_behind(self, mock_run):
        """End-to-end: chains behind."""
        mock_run.return_value = PlaybookResult(
            rc=0,
            stdout=_wrap_as_playbook_output(BEHIND_TABLE),
            stderr="",
        )
        inp = SyncStatusInput(target="production", chain=None)
        result = run_sync_status(inp)
        assert result["chains"]["VRSC"].status == SyncStatus.BEHIND
        assert "Issues detected" in (result.get("summary") or "")

    @patch("provisioning_langgraph.graphs.sync_status.run_playbook")
    def test_full_offline(self, mock_run):
        """End-to-end: both chains offline."""
        mock_run.return_value = PlaybookResult(
            rc=0,
            stdout=_wrap_as_playbook_output(OFFLINE_TABLE),
            stderr="",
        )
        inp = SyncStatusInput(target="production", chain=None)
        result = run_sync_status(inp)
        assert result["chains"]["VRSC"].status == SyncStatus.OFFLINE
        assert result["chains"]["vDEX"].status == SyncStatus.OFFLINE

    @patch("provisioning_langgraph.graphs.sync_status.run_playbook")
    def test_playbook_failure(self, mock_run):
        """End-to-end: playbook fails, graph should end early."""
        mock_run.return_value = PlaybookResult(
            rc=1,
            stdout="",
            stderr="SSH connection refused",
            failed=True,
        )
        inp = SyncStatusInput(target="production", chain=Chain.VRSC)
        result = run_sync_status(inp)
        assert len(result["playbook_errors"]) > 0
        assert result.get("summary") is not None

    @patch("provisioning_langgraph.graphs.sync_status.run_playbook")
    def test_vrsctest_playbook_output(self, mock_run):
        """End-to-end: VRSCTEST single chain."""
        vrsctest_table = (
            "╔═══════════════════════════════════════════════════════╗\n"
            "║  VRSCTEST Testnet Sync Status — BWD                 ║\n"
            "╠══════════════╦═══════════════╦══════════╦═══════════╣\n"
            "║ Chain        ║ Local / Tip   ║ Gap      ║ P/TLS     ║\n"
            "╠══════════════╬═══════════════╬══════════╬═══════════╣\n"
            "║ VRSCTEST     ║ 0040090 / 0040090 ║  +0 ║   2 / 0   ║\n"
            "╚══════════════╩═══════════════╩══════════╩═══════════╝"
        )
        mock_run.return_value = PlaybookResult(
            rc=0,
            stdout=_wrap_as_playbook_output(vrsctest_table),
            stderr="",
        )
        inp = SyncStatusInput(target="production", chain=Chain.VRSCTEST)
        result = run_sync_status(inp)
        assert len(result["chains"]) == 1
        assert "VRSCTEST" in result["chains"]
        assert result["chains"]["VRSCTEST"].status == SyncStatus.SYNCED
        assert result["chains"]["VRSCTEST"].blocks == 40090


# ── Tests: CLI exit codes ───────────────────────────────────────────────


class TestCliExitCodes:
    @patch("provisioning_langgraph.cli.run_sync_status")
    def test_synced_exit_zero(self, mock_run):
        """All synced → exit 0."""
        state = SyncStatusState(
            input=SyncStatusInput(),
            chains={
                "VRSC": ChainStatus(name="VRSC", status=SyncStatus.SYNCED),
            },
        )
        mock_run.return_value = state
        from provisioning_langgraph.cli import sync_status_main
        rc = sync_status_main(["--json"])
        assert rc == 0

    @patch("provisioning_langgraph.cli.run_sync_status")
    def test_behind_exit_one(self, mock_run):
        """Any chain behind → exit 1."""
        state = SyncStatusState(
            input=SyncStatusInput(),
            chains={
                "VRSC": ChainStatus(name="VRSC", status=SyncStatus.BEHIND, blocks=100, longestchain=200),
            },
        )
        mock_run.return_value = state
        from provisioning_langgraph.cli import sync_status_main
        rc = sync_status_main(["--json"])
        assert rc == 1

    @patch("provisioning_langgraph.cli.run_sync_status")
    def test_offline_exit_one(self, mock_run):
        """Any chain offline → exit 1."""
        state = SyncStatusState(
            input=SyncStatusInput(),
            chains={
                "VRSC": ChainStatus(name="VRSC", status=SyncStatus.OFFLINE),
            },
        )
        mock_run.return_value = state
        from provisioning_langgraph.cli import sync_status_main
        rc = sync_status_main(["--json"])
        assert rc == 1

    @patch("provisioning_langgraph.cli.run_sync_status")
    def test_errors_exit_one(self, mock_run):
        """Playbook errors → exit 1 even if all chains synced."""
        state = SyncStatusState(
            input=SyncStatusInput(),
            chains={
                "VRSC": ChainStatus(name="VRSC", status=SyncStatus.SYNCED),
            },
            playbook_errors=["Something went wrong"],
        )
        mock_run.return_value = state
        from provisioning_langgraph.cli import sync_status_main
        rc = sync_status_main(["--json"])
        assert rc == 1

    def test_invalid_chain_exit_one(self):
        """Invalid chain arg → exit 1."""
        from provisioning_langgraph.cli import sync_status_main
        rc = sync_status_main(["--chain", "nosuch"])
        assert rc == 1