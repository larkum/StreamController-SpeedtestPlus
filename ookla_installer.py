from __future__ import annotations

import hashlib
import os
import platform
import subprocess
import tarfile
import tempfile
import urllib.request
from pathlib import Path


OOKLA_VERSION = "1.2.0"
ARCHIVES = {
    "x86_64": ("x86_64", "5690596c54ff9bed63fa3732f818a05dbc2db19ad36ed68f21ca5f64d5cfeeb7"),
    "amd64": ("x86_64", "5690596c54ff9bed63fa3732f818a05dbc2db19ad36ed68f21ca5f64d5cfeeb7"),
    "aarch64": ("aarch64", "3953d231da3783e2bf8904b6dd72767c5c6e533e163d3742fd0437affa431bd3"),
    "arm64": ("aarch64", "3953d231da3783e2bf8904b6dd72767c5c6e533e163d3742fd0437affa431bd3"),
    "armv7l": ("armhf", "e45fcdebbd8a185553535533dd032d6b10bc8c64eee4139b1147b9c09835d08d"),
    "armv6l": ("armel", "629a455a2879224bd0dbd4b36d8c721dda540717937e4660b4d2c966029466bf"),
    "i386": ("i386", "9ff7e18dbae7ee0e03c66108445a2fb6ceea6c86f66482e1392f55881b772fe8"),
    "i686": ("i386", "9ff7e18dbae7ee0e03c66108445a2fb6ceea6c86f66482e1392f55881b772fe8"),
}


class OoklaInstallError(RuntimeError):
    pass


def managed_cli_path() -> Path:
    data_home = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return data_home / "streamcontroller-speedtest-plus" / "ookla-cli" / "speedtest"


def archive_details(machine: str | None = None) -> tuple[str, str, str]:
    key = (machine or platform.machine()).casefold()
    if key not in ARCHIVES:
        raise OoklaInstallError(f"This processor is not supported by Ookla's Linux CLI: {key or 'unknown'}")
    archive_arch, checksum = ARCHIVES[key]
    url = f"https://install.speedtest.net/app/cli/ookla-speedtest-{OOKLA_VERSION}-linux-{archive_arch}.tgz"
    return archive_arch, url, checksum


def _validate_cli(path: Path) -> None:
    try:
        completed = subprocess.run(
            [str(path), "--version"], capture_output=True, text=True, timeout=10, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise OoklaInstallError("The downloaded Ookla CLI could not be started.") from exc
    output = f"{completed.stdout}\n{completed.stderr}".casefold()
    if completed.returncode != 0 or "ookla" not in output:
        raise OoklaInstallError("The downloaded file is not the official Ookla Speedtest CLI.")


def install_ookla_cli() -> Path:
    _archive_arch, url, expected_checksum = archive_details()
    destination = managed_cli_path()
    destination.parent.mkdir(parents=True, exist_ok=True)

    archive_path: Path | None = None
    candidate_path: Path | None = None
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "StreamController-SpeedtestPlus/0.2"})
        with urllib.request.urlopen(request, timeout=60) as response:
            with tempfile.NamedTemporaryFile(dir=destination.parent, suffix=".tgz", delete=False) as archive:
                archive_path = Path(archive.name)
                digest = hashlib.sha256()
                total = 0
                while chunk := response.read(128 * 1024):
                    total += len(chunk)
                    if total > 10 * 1024 * 1024:
                        raise OoklaInstallError("The Ookla download was unexpectedly large.")
                    digest.update(chunk)
                    archive.write(chunk)
        if digest.hexdigest() != expected_checksum:
            raise OoklaInstallError("The Ookla download failed its security check.")

        with tarfile.open(archive_path, "r:gz") as package:
            try:
                member = package.getmember("speedtest")
            except KeyError as exc:
                raise OoklaInstallError("The Ookla archive did not contain the Speedtest CLI.") from exc
            if not member.isfile():
                raise OoklaInstallError("The Ookla archive contained an invalid Speedtest CLI.")
            source = package.extractfile(member)
            if source is None:
                raise OoklaInstallError("The Ookla CLI could not be extracted.")
            with source, tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as candidate:
                candidate_path = Path(candidate.name)
                while chunk := source.read(128 * 1024):
                    candidate.write(chunk)

        candidate_path.chmod(0o755)
        _validate_cli(candidate_path)
        candidate_path.replace(destination)
        candidate_path = None
        return destination
    except OoklaInstallError:
        raise
    except Exception as exc:
        raise OoklaInstallError(f"Could not install the Ookla CLI: {exc}") from exc
    finally:
        if archive_path is not None:
            archive_path.unlink(missing_ok=True)
        if candidate_path is not None:
            candidate_path.unlink(missing_ok=True)
