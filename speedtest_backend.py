from __future__ import annotations

import json
import re
import shutil
import subprocess
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Iterable

try:
    from .ookla_installer import managed_cli_path
except ImportError:  # Allows direct tests from the plugin root.
    from ookla_installer import managed_cli_path


US_STATE_NAMES = {
    "al": "alabama", "ak": "alaska", "az": "arizona", "ar": "arkansas",
    "ca": "california", "co": "colorado", "ct": "connecticut", "de": "delaware",
    "fl": "florida", "ga": "georgia", "hi": "hawaii", "id": "idaho",
    "il": "illinois", "in": "indiana", "ia": "iowa", "ks": "kansas",
    "ky": "kentucky", "la": "louisiana", "me": "maine", "md": "maryland",
    "ma": "massachusetts", "mi": "michigan", "mn": "minnesota", "ms": "mississippi",
    "mo": "missouri", "mt": "montana", "ne": "nebraska", "nv": "nevada",
    "nh": "new hampshire", "nj": "new jersey", "nm": "new mexico", "ny": "new york",
    "nc": "north carolina", "nd": "north dakota", "oh": "ohio", "ok": "oklahoma",
    "or": "oregon", "pa": "pennsylvania", "ri": "rhode island", "sc": "south carolina",
    "sd": "south dakota", "tn": "tennessee", "tx": "texas", "ut": "utah",
    "vt": "vermont", "va": "virginia", "wa": "washington", "wv": "west virginia",
    "wi": "wisconsin", "wy": "wyoming", "dc": "district of columbia",
}
BITS_PER_BYTE = 8
BITS_PER_MEGABIT = 1_000_000


class SpeedtestError(RuntimeError):
    pass


@dataclass(frozen=True)
class ServerChoice:
    id: str
    sponsor: str
    name: str
    country: str
    distance_km: float | None = None

    @property
    def label(self) -> str:
        location = ", ".join(part for part in (self.name, self.country) if part)
        owner = f" — {self.sponsor}" if self.sponsor else ""
        return f"{location}{owner} (#{self.id})"


@dataclass(frozen=True)
class SpeedtestResult:
    timestamp: str
    ping_ms: float
    download_mbps: float
    upload_mbps: float
    server_id: str = ""
    server_name: str = ""
    server_location: str = ""
    result_url: str = ""
    engine: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict) -> "SpeedtestResult":
        return cls(
            timestamp=str(value["timestamp"]),
            ping_ms=float(value["ping_ms"]),
            download_mbps=float(value["download_mbps"]),
            upload_mbps=float(value["upload_mbps"]),
            server_id=str(value.get("server_id", "")),
            server_name=str(value.get("server_name", "")),
            server_location=str(value.get("server_location", "")),
            result_url=str(value.get("result_url", "")),
            engine=str(value.get("engine", "")),
        )


def bytes_per_second_to_mbps(bandwidth: float | int) -> float:
    """Convert Ookla's machine-readable bytes/second to decimal megabits/second."""
    return float(bandwidth) * BITS_PER_BYTE / BITS_PER_MEGABIT


def is_speedtest_result_url(value: str) -> bool:
    """Allow only Ookla result links to be opened from saved plugin data."""
    try:
        parsed = urllib.parse.urlparse(str(value).strip())
    except ValueError:
        return False
    hostname = (parsed.hostname or "").casefold()
    return parsed.scheme == "https" and (hostname == "speedtest.net" or hostname.endswith(".speedtest.net"))


def parse_ookla_json(payload: str) -> SpeedtestResult:
    try:
        data = json.loads(payload)
        server = data.get("server") or {}
        result = data.get("result") or {}
        ping = data.get("ping") or {}
        download = data.get("download") or {}
        upload = data.get("upload") or {}

        # Ookla reports bandwidth in bytes per second. Mbps is decimal bits/sec.
        download_mbps = bytes_per_second_to_mbps(download["bandwidth"])
        upload_mbps = bytes_per_second_to_mbps(upload["bandwidth"])
        ping_ms = float(ping["latency"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise SpeedtestError("The Ookla CLI returned an unexpected result.") from exc

    server_location = ", ".join(
        part for part in (str(server.get("location", "")), str(server.get("country", ""))) if part
    )
    return SpeedtestResult(
        timestamp=str(data.get("timestamp") or datetime.now(timezone.utc).isoformat()),
        ping_ms=ping_ms,
        download_mbps=download_mbps,
        upload_mbps=upload_mbps,
        server_id=str(server.get("id", "")),
        server_name=str(server.get("name", "")),
        server_location=server_location,
        result_url=str(result.get("url", "")),
        engine="Ookla CLI",
    )


def filter_servers(servers: Iterable[ServerChoice], query: str, limit: int = 100) -> list[ServerChoice]:
    words = [word.casefold() for word in query.split() if word.strip()]
    matches = []
    for server in servers:
        haystack = " ".join((server.id, server.sponsor, server.name, server.country)).casefold()
        state_abbreviations = re.findall(r",\s*([a-z]{2})(?:\s|$)", server.name.casefold())
        state_names = [US_STATE_NAMES[item] for item in state_abbreviations if item in US_STATE_NAMES]
        if state_names:
            haystack += " " + " ".join(state_names)
        if "united states" in haystack:
            haystack += " usa us america"
        if "united kingdom" in haystack:
            haystack += " uk britain great britain"
        if all(word in haystack for word in words):
            matches.append(server)
    matches.sort(key=lambda server: (server.distance_km is None, server.distance_km or 0, server.label.casefold()))
    return matches[:limit]


def discover_servers(query: str = "") -> list[ServerChoice]:
    try:
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))
        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/128 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
        }
        opener.open(urllib.request.Request("https://www.speedtest.net/", headers=headers), timeout=20).close()
        parameters = {
            "engine": "js",
            "https_functional": "true",
            "limit": "100",
        }
        if query.strip():
            parameters["search"] = query.strip()
        url = "https://www.speedtest.net/api/js/servers?" + urllib.parse.urlencode(parameters)
        request = urllib.request.Request(url, headers={**headers, "Referer": "https://www.speedtest.net/"})
        with opener.open(request, timeout=20) as response:
            items = json.loads(response.read(2 * 1024 * 1024))
        if not isinstance(items, list):
            raise ValueError("unexpected server response")
    except Exception as exc:
        raise SpeedtestError(f"Could not load Speedtest.net servers: {exc}") from exc

    choices: list[ServerChoice] = []
    for item in items:
        try:
            distance = float(item.get("distance")) if item.get("distance") not in (None, "") else None
        except (TypeError, ValueError):
            distance = None
        choices.append(
            ServerChoice(
                id=str(item.get("id", "")),
                sponsor=str(item.get("sponsor", "")),
                name=str(item.get("name", "")),
                country=str(item.get("country") or item.get("cc") or ""),
                distance_km=distance,
            )
        )
    return filter_servers(choices, query)


def _candidate_commands() -> list[list[str]]:
    candidates: list[list[str]] = []
    managed = managed_cli_path()
    if managed.is_file():
        candidates.append([str(managed)])

    direct = shutil.which("speedtest")
    if direct:
        candidates.append([direct])

    flatpak_spawn = shutil.which("flatpak-spawn")
    if flatpak_spawn:
        candidates.append([flatpak_spawn, "--host", "speedtest"])
    return candidates


def find_ookla_command() -> list[str] | None:
    for command in _candidate_commands():
        try:
            completed = subprocess.run(
                [*command, "--version"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        version = f"{completed.stdout}\n{completed.stderr}".casefold()
        if completed.returncode == 0 and "ookla" in version:
            return command
    return None


def run_ookla(server_id: str = "") -> SpeedtestResult:
    command = find_ookla_command()
    if not command:
        raise SpeedtestError("Install the Ookla Speedtest CLI in Settings > Plugins > Speedtest+ before running a test.")

    args = [
        *command,
        "--accept-license",
        "--accept-gdpr",
        "--format=json",
        "--progress=no",
    ]
    if server_id:
        args.append(f"--server-id={server_id}")

    try:
        completed = subprocess.run(args, capture_output=True, text=True, timeout=240, check=False)
    except subprocess.TimeoutExpired as exc:
        raise SpeedtestError("The speed test timed out.") from exc
    except OSError as exc:
        raise SpeedtestError(f"Could not start the Ookla CLI: {exc}") from exc

    if completed.returncode != 0:
        message = (completed.stderr or completed.stdout or "Unknown error").strip().splitlines()[-1]
        raise SpeedtestError(f"Ookla CLI failed: {message}")
    return parse_ookla_json(completed.stdout)


def run_speedtest(settings: dict) -> SpeedtestResult:
    server_id = str(settings.get("server_id", "")).strip()
    accepted = bool(settings.get("accept_ookla_terms", False))
    if not accepted:
        raise SpeedtestError("Accept the Ookla CLI terms in Settings > Plugins > Speedtest+ before running a test.")
    return run_ookla(server_id)
