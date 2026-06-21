"""
Tests for the Ansible runner — playbook execution, output parsing.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from provisioning_langgraph.runner import (
    _find_provisioning_root,
    _RECAP_FIELD_RE,
    _SYNC_TABLE_RE,
    extract_debug_msg,
    parse_sync_table,
    run_playbook,
)
from provisioning_langgraph.state import SyncStatusInput


# ── Fixtures ────────────────────────────────────────────────────────────

SAMPLE_ANSI_OUTPUT = """
TASK [Query VRSC getinfo] ******************************************************
changed: [135.181.136.105]

TASK [Query vDEX getinfo] ******************************************************
changed: [135.181.136.105]

TASK [Parse VRSC blocks] *******************************************************
ok: [135.181.136.105]

TASK [Calculate sync gaps] *****************************************************
ok: [135.181.136.105]

TASK [Display sync status report] **********************************************
ok: [135.181.136.105] => {
    "msg": "╔═══════════════════════════════════════════════════════════╗\\n║           PBaaS Chain Sync Status — BWD                  ║\\n╠══════════════╦═══════════════╦══════════╦═══════════════╣\\n║ Chain         ║ Local / Tip   ║ Gap      ║ Peers / TLS    ║\\n╠══════════════╬═══════════════╬══════════╬═══════════════╣\\n║ VRSC          ║ 4056739 / 4056739 ║      +0 ║   5 / 5       ║\\n║ vDEX          ║ 0897765 / 0897765 ║      +0 ║   5 / 5       ║\\n╚══════════════╩═══════════════╩══════════╩═══════════════╝"
}

PLAY RECAP *********************************************************************
135.181.136.105            : ok=5    changed=2    unreachable=0    failed=0    skipped=1    rescued=0    ignored=0
"""

SAMPLE_OFFLINE_OUTPUT = """
TASK [Query VRSC getinfo] ******************************************************
changed: [135.181.136.105]

TASK [Display sync status report] **********************************************
ok: [135.181.136.105] => {
    "msg": "╔═══════════════════════════════════════════════════════════╗\\n║           PBaaS Chain Sync Status — BWD                  ║\\n╠══════════════╦═══════════════╦══════════╦═══════════════╣\\n║ Chain         ║ Local / Tip   ║ Gap      ║ Peers / TLS    ║\\n╠══════════════╬═══════════════╬══════════╬═══════════════╣\\n║ VRSC          ║    offline    ║    —     ║       —        ║\\n║ vDEX          ║    offline    ║    —     ║       —        ║\\n╚══════════════╩═══════════════╩══════════╩═══════════════╝"
}

PLAY RECAP *********************************************************************
135.181.136.105            : ok=3    changed=2    unreachable=0    failed=0    skipped=1    rescued=0    ignored=0
"""

SAMPLE_VRSCTEST_OUTPUT = """
TASK [Query VRSCTEST getinfo] **************************************************
changed: [135.181.136.105]

TASK [Display sync status report] **********************************************
ok: [135.181.136.105] => {
    "msg": "╔═══════════════════════════════════════════════════════════╗\\n║         VRSCTEST Testnet Sync Status — BWD                  ║\\n╠══════════════╦═══════════════╦══════════╦═══════════════════╣\\n║ Chain        ║ Local / Tip   ║ Gap      ║ Peers / TLS       ║\\n╠══════════════╬═══════════════╬══════════╬═══════════════════╣\\n║ VRSCTEST     ║ 0040090 / 0040090 ║      +0 ║   2 / 0         ║\\n╚══════════════╩═══════════════╩══════════╩═══════════════════╝\\nTip timestamp: 2026-06-21 12:34:56"
}

PLAY RECAP *********************************************************************
135.181.136.105            : ok=3    changed=1    unreachable=0    failed=0    skipped=0    rescued=0    ignored=0
"""


# ── Tests: debug msg extraction ─────────────────────────────────────────


class TestExtractDebugMsg:
    def test_extract_from_normal_output(self):
        msg = extract_debug_msg(SAMPLE_ANSI_OUTPUT)
        assert msg is not None
        assert "PBaaS Chain Sync Status" in msg
        assert "VRSC" in msg
        assert "vDEX" in msg

    def test_extract_from_offline_output(self):
        msg = extract_debug_msg(SAMPLE_OFFLINE_OUTPUT)
        assert msg is not None
        assert "offline" in msg.lower()

    def test_extract_vrsctest_output(self):
        msg = extract_debug_msg(SAMPLE_VRSCTEST_OUTPUT)
        assert msg is not None
        assert "VRSCTEST" in msg
        assert "40090" in msg

    def test_extract_empty_output(self):
        msg = extract_debug_msg("")
        assert msg is None

    def test_extract_no_debug_block(self):
        msg = extract_debug_msg("PLAY RECAP ****\nhost : ok=1 failed=0")
        assert msg is None


# ── Tests: table parsing ────────────────────────────────────────────────


class TestParseSyncTable:
    def test_parse_vrsc_vdex_synced(self):
        msg = extract_debug_msg(SAMPLE_ANSI_OUTPUT)
        assert msg is not None
        table = parse_sync_table(msg)

        assert "VRSC" in table
        assert "vDEX" in table

        v = table["VRSC"]
        assert v["blocks"] == 4056739
        assert v["longestchain"] == 4056739
        assert v["gap"] == 0
        assert v["peers"] == 5
        assert v["tls"] == 5
        assert v["offline"] is False

        d = table["vDEX"]
        assert d["blocks"] == 897765
        assert d["gap"] == 0
        assert d["offline"] is False

    def test_parse_both_offline(self):
        msg = extract_debug_msg(SAMPLE_OFFLINE_OUTPUT)
        assert msg is not None
        table = parse_sync_table(msg)

        assert "VRSC" in table
        assert "vDEX" in table
        assert table["VRSC"]["offline"] is True
        assert table["vDEX"]["offline"] is True
        assert table["VRSC"]["blocks"] == 0

    def test_parse_vrsctest(self):
        msg = extract_debug_msg(SAMPLE_VRSCTEST_OUTPUT)
        assert msg is not None
        table = parse_sync_table(msg)

        assert "VRSCTEST" in table
        v = table["VRSCTEST"]
        assert v["blocks"] == 40090
        assert v["longestchain"] == 40090
        assert v["gap"] == 0
        assert v["peers"] == 2
        assert v["tls"] == 0

    def test_parse_empty_table(self):
        result = parse_sync_table("No data here")
        assert result == {}

    def test_parse_malformed(self):
        result = parse_sync_table("║ wei║rd stuff ║")
        assert result == {}
        result = parse_sync_table("")
        assert result == {}

    def test_parse_partial_table(self):
        """A single-chain table (VRSCTEST) should still parse."""
        msg = extract_debug_msg(SAMPLE_VRSCTEST_OUTPUT)
        assert msg is not None
        table = parse_sync_table(msg)
        assert len(table) == 1
        assert "VRSCTEST" in table


# ── Tests: PLAY RECAP parsing ───────────────────────────────────────────


class TestPlayRecapParsing:
    def test_recap_regex_success(self):
        line = "host : ok=5 changed=2 unreachable=0 failed=0 skipped=1 rescued=0 ignored=0"
        matches = _RECAP_FIELD_RE.findall(line)
        assert len(matches) == 7
        fields = dict(matches)
        assert fields["ok"] == "5"
        assert fields["failed"] == "0"
        assert fields["unreachable"] == "0"

    def test_recap_regex_failure(self):
        line = "host : ok=5 changed=2"
        matches = _RECAP_FIELD_RE.findall(line)
        fields = dict(matches)
        assert fields["ok"] == "5"
        assert fields.get("failed") is None  # not present


# ── Tests: provisioning root discovery ──────────────────────────────────


class TestProvisioningRoot:
    def test_find_root(self):
        """The test runner is inside langgraph/tests/; root should be two levels up."""
        root = _find_provisioning_root()
        assert root is not None
        assert (root / "playbooks").is_dir()
        assert (root / "inventory.ini").is_file()
        assert root.name == "dream-pbaas-provisioning"


# ── Integration test (requires Ansible + SSH to BWD) ────────────────────


class TestRunPlaybookIntegration:
    @pytest.mark.integration
    def test_ping_playbook(self):
        """
        Run the 00-ping playbook to verify ansible is installed and
        the control node can parse its own output.
        """
        result = run_playbook("playbooks/00-ping.yml")
        assert result.rc == 0, f"Ping playbook failed: {result.stderr}"
        assert "PLAY RECAP" in result.stdout

    @pytest.mark.integration
    def test_sync_status_playbook(self):
        """
        Run the actual sync-status playbook against BWD.
        Requires the control node to have SSH access to the BWD server.
        """
        result = run_playbook("playbooks/15-sync-status.yml")
        assert result.rc == 0, f"Sync playbook failed: {result.stderr}"

        msg = extract_debug_msg(result.stdout)
        assert msg is not None, "No debug msg in output"
        table = parse_sync_table(msg)
        assert "VRSC" in table or "vDEX" in table

    @pytest.mark.integration
    def test_sync_status_vrsctest_playbook(self):
        """Same as above but for VRSCTEST testnet."""
        result = run_playbook("playbooks/15b-sync-status-vrsctest.yml")
        assert result.rc == 0, f"VRSCTEST sync playbook failed: {result.stderr}"

        msg = extract_debug_msg(result.stdout)
        assert msg is not None
        table = parse_sync_table(msg)
        assert "VRSCTEST" in table