"""
Pydantic state models for LangGraph provisioning graphs.

Shared across all graphs (sync_status, idcreate_deploy, etc.).
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ── Enums ──────────────────────────────────────────────────────────────

class Chain(str, Enum):
    """Verus PBaaS chains we provision against."""
    VRSC = "vrsc"
    VRSCTEST = "vrsctest"
    VDEX = "vdex"
    VARRR = "varrr"
    CHIPS = "chips"


class SyncStatus(str, Enum):
    SYNCED = "synced"        # blocks == longestchain, gap == 0
    BEHIND = "behind"        # blocks < longestchain, gap > 0
    OFFLINE = "offline"      # no JSON response from daemon
    UNKNOWN = "unknown"      # couldn't determine


class NodeResult(str, Enum):
    """Result of a single graph node execution."""
    OK = "ok"
    FAILED = "failed"
    SKIPPED = "skipped"


# ── Per-chain status ───────────────────────────────────────────────────

class ChainStatus(BaseModel):
    """Sync status for a single chain."""
    name: str
    status: SyncStatus = SyncStatus.UNKNOWN
    blocks: int = 0
    longestchain: int = 0
    gap: int = 0
    peers: int = 0
    tls: int = 0
    tiptime: int = 0
    error: str | None = None


# ── Sync status graph models ───────────────────────────────────────────

class SyncStatusInput(BaseModel):
    """User-supplied parameters for a sync-status run."""
    target: str = Field(default="production", description="Ansible host group")
    chain: Chain | None = Field(default=None, description="Specific chain or None for all")
    playbook_dir: str = Field(default="playbooks", description="Path to playbooks dir")
    inventory: str = Field(default="inventory.ini", description="Path to inventory")


class SyncStatusState(BaseModel):
    """Runtime state passed through the sync_status graph nodes."""
    input: SyncStatusInput
    chains: dict[str, ChainStatus] = Field(default_factory=dict)
    playbook_output: str | None = None
    playbook_rc: int | None = None
    playbook_errors: list[str] = Field(default_factory=list)
    node_results: dict[str, NodeResult] = Field(default_factory=dict)
    summary: str | None = None


# ── Shared ─────────────────────────────────────────────────────────────

class PlaybookResult(BaseModel):
    """Captured output from a single ansible-playbook invocation."""
    rc: int
    stdout: str
    stderr: str
    failed: bool = False
    unreachable: bool = False
    playbook_name: str = ""
    """Structured attributes parsed from output, if applicable."""
    parsed: dict[str, Any] = Field(default_factory=dict)
