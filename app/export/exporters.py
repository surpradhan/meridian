"""
Result Exporters

Convert query result rows (list of dicts) to various download formats.
Each function returns raw bytes suitable for a FastAPI Response body.
"""

import csv
import io
import json
import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


def to_json(rows: List[Dict[str, Any]]) -> bytes:
    """Serialize rows to pretty-printed JSON bytes."""
    return json.dumps(rows, indent=2, default=str).encode("utf-8")


def to_csv(rows: List[Dict[str, Any]]) -> bytes:
    """Serialize rows to CSV bytes (UTF-8 with BOM for Excel compatibility)."""
    if not rows:
        return b"\xef\xbb\xbf"  # BOM only

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    return "\xef\xbb\xbf".encode("utf-8") + output.getvalue().encode("utf-8")


def to_excel(rows: List[Dict[str, Any]]) -> bytes:
    """Serialize rows to Excel (.xlsx) bytes using pandas + openpyxl."""
    try:
        import pandas as pd  # already in requirements.txt
    except ImportError as e:
        raise RuntimeError("pandas is required for Excel export") from e

    try:
        import openpyxl  # noqa: F401 — required by pandas xlsx engine
    except ImportError as e:
        raise RuntimeError(
            "openpyxl is required for Excel export. "
            "Install it with: pip install openpyxl"
        ) from e

    buf = io.BytesIO()
    df = pd.DataFrame(rows) if rows else pd.DataFrame()
    df.to_excel(buf, index=False, engine="openpyxl")
    return buf.getvalue()
