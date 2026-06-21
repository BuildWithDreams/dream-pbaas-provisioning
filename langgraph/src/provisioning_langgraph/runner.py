"""
Ansible playbook execution and output parsing.

Provides the single `run_playbook()` function that all graph nodes use
to invoke ansible-playbook and parse the results.
"""

from __future__ import annotations

import re
import subprocess
import json
from pathlib import Path
from typing import Any

from .state import PlaybookResult, SyncStatusInput


# Regex: extract "msg" content from a debug task block in Ansible output.
# The debug module prints:
#   TASK [...]
#   ok: [hostname] => {
#       "msg": "..."
#   }
_DEBUG_MSG_RE = re.compile(
    r'"msg":\s*"((?:[^"\\]|\\.)*)"',
    re.DOTALL,
)

# Regex: extract raw inner text from debug msg that spans multiple lines
# (Ansible's YAML debug output may show the msg as a multiline block).
_DEBUG_MSG_BLOCK_RE = re.compile(
    r'"msg":\s*\|?\n?\s{2,}((?:.+\n?)+?)(?=\n\S|\Z)',
    re.DOTALL,
)

# Regex: parse PLAY RECAP line(s) for per-host stats.
# Format: hostname : ok=N changed=N unreachable=N failed=N skipped=N ...
_PLAY_RECAP_RE = re.compile(
    r":\s+(?=.*ok=)(?=.*failed=)(?=.*unreachable=)"
    r"(?P<fields>(?:ok|changed|unreachable|failed|skipped|rescued|ignored)=\d+\s*)+",
)

# Regex: extract individual counters from PLAY RECAP fields.
_RECAP_FIELD_RE = re.compile(r"(ok|changed|unreachable|failed|skipped|rescued|ignored)=(\d+)")

# Regex: extract the ASCII sync table from debug output.
# Looks for the box-drawing header ╔══ ... ╚══ pattern.
_SYNC_TABLE_RE = re.compile(
    r"╔[╦═]+╗\n(?:.*\n)*?╚[╩═]+╝",
)

# Regex: parse a single row from the sync status table.
_ROW_RE = re.compile(
    r"║\s*(\S+)\s*║\s*(?:(offline)\s*║\s*(—)\s*║\s*(—)\s*║|"
    r"(\d+)\s*/\s*(\d+)\s*║\s*([+-]?\d+)\s*║\s*(\d+)\s*/\s*(\d+)\s*║)",
)


def run_playbook(
    playbook: str,
    inventory: str = "inventory.ini",
    extra_args: list[str] | None = None,
    workdir: str | Path | None = None,
    timeout: int = 120,
) -> PlaybookResult:
    """
    Execute ``ansible-playbook`` and capture the result.

    Parameters
    ----------
    playbook : str
        Path to the playbook YAML file (relative to ``workdir``).
    inventory : str
        Path to the Ansible inventory file (relative to ``workdir``).
    extra_args : list[str] | None
        Additional ``-e`` arguments, e.g. ``["var=val"]``.
    workdir : str | Path | None
        Working directory. Defaults to the provisioning repo root
        (parent of the langgraph/ directory).
    timeout : int
        Maximum wait in seconds.

    Returns
    -------
    PlaybookResult with stdout, rc, and structured failure info.
    """
    if workdir is None:
        workdir = _find_provisioning_root()
    workdir = Path(workdir)

    cmd = [
        "ansible-playbook",
        "-i", str(workdir / inventory),
        str(workdir / playbook),
    ]
    if extra_args:
        cmd.extend(f"-e={a}" for a in extra_args)

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=workdir,
        )
    except subprocess.TimeoutExpired:
        return PlaybookResult(
            rc=-1,
            stdout="",
            stderr=f"Playbook timed out after {timeout}s",
            failed=True,
            playbook_name=playbook,
        )
    except FileNotFoundError:
        return PlaybookResult(
            rc=-1,
            stdout="",
            stderr="ansible-playbook not found — is ansible installed?",
            failed=True,
            playbook_name=playbook,
        )

    result = PlaybookResult(
        rc=proc.returncode,
        stdout=proc.stdout,
        stderr=proc.stderr,
        playbook_name=playbook,
    )

    # Parse PLAY RECAP for failure/unreachable count
    for m in _RECAP_FIELD_RE.finditer(proc.stdout or ""):
        key, val = m.group(1), int(m.group(2))
        if key == "failed" and val > 0:
            result.failed = True
        if key == "unreachable" and val > 0:
            result.unreachable = True

    return result


def extract_debug_msg(stdout: str) -> str | None:
    """
    Extract the *last* debug ``msg`` string from Ansible stdout.

    Falls back to a block-style capture if the inline pattern fails.
    JSON-escaped sequences (``\\n``, ``\\t``) are unescaped automatically.
    """
    matches = _DEBUG_MSG_RE.findall(stdout)
    raw: str | None = None
    if matches:
        raw = matches[-1]
    else:
        block_matches = _DEBUG_MSG_BLOCK_RE.findall(stdout)
        if block_matches:
            raw = block_matches[-1].strip()

    if raw is None:
        return None

    # Unescape common JSON string escapes (\\n → \\n, \\t → \\t, \\" → ", \\\\ → \\)
    # Targeted replacement avoids corrupting UTF-8 multi-byte characters
    # (box-drawing chars like ╔, ║, ╚ etc.) that unicode_escape would mangle.
    replacements = {
        "\\n": "\n",
        "\\r": "\r",
        "\\t": "\t",
        '\\"': '"',
        "\\\\": "\\",
    }
    for escaped, actual in replacements.items():
        raw = raw.replace(escaped, actual)

    return raw


def parse_sync_table(table_text: str) -> dict[str, dict[str, Any]]:
    """
    Parse the ASCII sync-status table into a dict of ChainStatus-like dicts.

    Input format (from playbook debug output)::

        ║ VRSC          ║ 4056739 / 4056739 ║      +0 ║   5 / 5       ║
        ║ vDEX          ║    offline    ║    —     ║       —        ║

    Returns {chain_name: {blocks, longestchain, gap, peers, tls, offline}}
    """
    chains: dict[str, dict[str, Any]] = {}

    for line in table_text.split("\n"):
        m = _ROW_RE.search(line)
        if not m:
            continue

        name = m.group(1).strip()
        offline = m.group(2) is not None

        if offline:
            chains[name] = {
                "blocks": 0,
                "longestchain": 0,
                "gap": 0,
                "peers": 0,
                "tls": 0,
                "offline": True,
            }
        else:
            # Online alternative: groups 5-9
            chains[name] = {
                "blocks": int(m.group(5)),
                "longestchain": int(m.group(6)),
                "gap": int(m.group(7)),
                "peers": int(m.group(8)),
                "tls": int(m.group(9)),
                "offline": False,
            }

    return chains


def _find_provisioning_root() -> Path:
    """
    Walk upward from the langgraph/ package to find the provisioning repo root
    (the directory containing ``playbooks/`` and ``inventory.ini``).
    """
    candidate = Path(__file__).resolve()
    for parent in [candidate] + list(candidate.parents):
        if (parent / "playbooks").is_dir() and (parent / "inventory.ini").is_file():
            return parent
    # Fallback: use the cwd
    return Path.cwd()