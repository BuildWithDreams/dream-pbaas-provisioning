"""
pytest configuration for langgraph provisioning tests.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure the src/ directory is on the Python path
SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))