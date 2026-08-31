from __future__ import annotations

from pathlib import Path


ALLOWED_INTERVALS = (0, 5, 10, 15, 30, 60)


def next_run_after(now_epoch: float, interval_minutes: int) -> float | None:
    if interval_minutes not in ALLOWED_INTERVALS or interval_minutes <= 0:
        return None
    return now_epoch + interval_minutes * 60


def is_due(now_epoch: float, next_run_epoch: float | int | None, interval_minutes: int) -> bool:
    return interval_minutes in ALLOWED_INTERVALS[1:] and bool(next_run_epoch) and now_epoch >= float(next_run_epoch)


def system_boot_id(path: str = "/proc/sys/kernel/random/boot_id") -> str:
    try:
        return Path(path).read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError):
        return ""


def should_run_initial_test(interval_minutes: int, current_boot_id: str, tested_boot_id: str) -> bool:
    return (
        interval_minutes in ALLOWED_INTERVALS[1:]
        and bool(current_boot_id)
        and current_boot_id != tested_boot_id
    )
