from __future__ import annotations

import csv
from pathlib import Path

try:
    from .speedtest_backend import SpeedtestResult
except ImportError:  # Allows the module to be tested directly from the plugin root.
    from speedtest_backend import SpeedtestResult


CSV_FIELDS = [
    "timestamp",
    "ping_ms",
    "download_mbps",
    "upload_mbps",
    "server_id",
    "server_name",
    "server_location",
    "result_url",
    "engine",
]

CSV_TEXT_FIELDS = ("server_id", "server_name", "server_location", "result_url", "engine")


def spreadsheet_safe_text(value: object) -> str:
    """Prevent imported text fields from being interpreted as spreadsheet formulas."""
    text = str(value or "")
    stripped = text.lstrip()
    if text.startswith(("\t", "\r", "\n")) or stripped.startswith(("=", "+", "-", "@")):
        return f"'{text}"
    return text


def append_result(path: str, result: SpeedtestResult) -> None:
    destination = Path(path).expanduser()
    if not destination.parent.exists():
        raise FileNotFoundError(f"The selected folder does not exist: {destination.parent}")

    write_header = not destination.exists() or destination.stat().st_size == 0
    with destination.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        if write_header:
            writer.writeheader()
        row = result.to_dict()
        row["ping_ms"] = f"{result.ping_ms:.2f}"
        row["download_mbps"] = f"{result.download_mbps:.2f}"
        row["upload_mbps"] = f"{result.upload_mbps:.2f}"
        for field in CSV_TEXT_FIELDS:
            row[field] = spreadsheet_safe_text(row.get(field, ""))
        writer.writerow(row)
