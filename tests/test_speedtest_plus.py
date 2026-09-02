import csv
import json
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from csv_logger import append_result
from ookla_installer import OoklaInstallError, archive_details
from scheduling import is_due, next_run_after, should_run_initial_test, system_boot_id
from speedtest_backend import (
    ServerChoice,
    SpeedtestError,
    SpeedtestResult,
    bytes_per_second_to_mbps,
    filter_servers,
    is_speedtest_result_url,
    parse_ookla_json,
    run_speedtest,
)


def _load_should_claim_image_control():
    import ast

    source_path = Path(__file__).parents[1] / "actions" / "speedtest_plus.py"
    module = ast.parse(source_path.read_text(encoding="utf-8"))
    function = next(
        node
        for node in module.body
        if isinstance(node, ast.FunctionDef) and node.name == "should_claim_image_control"
    )
    namespace = {}
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(source_path), "exec"), namespace)
    return namespace["should_claim_image_control"]


class SpeedtestBackendTests(unittest.TestCase):
    def test_speed_units_are_forced_to_decimal_mbps(self):
        self.assertEqual(bytes_per_second_to_mbps(1_000_000), 8.0)

    def test_only_speedtest_result_links_are_openable(self):
        self.assertTrue(is_speedtest_result_url("https://www.speedtest.net/result/c/abc123"))
        self.assertFalse(is_speedtest_result_url("http://www.speedtest.net/result/123"))
        self.assertFalse(is_speedtest_result_url("https://speedtest.net.example.com/result/123"))
        self.assertFalse(is_speedtest_result_url("file:///tmp/result"))

    def test_ookla_bandwidth_is_converted_from_bytes_to_megabits(self):
        payload = json.dumps(
            {
                "timestamp": "2026-08-31T12:34:56Z",
                "ping": {"latency": 12.34},
                "download": {"bandwidth": 12_500_000},
                "upload": {"bandwidth": 3_125_000},
                "server": {
                    "id": 123,
                    "name": "Example ISP",
                    "location": "Dallas, TX",
                    "country": "United States",
                },
                "result": {"url": "https://www.speedtest.net/result/123"},
            }
        )

        result = parse_ookla_json(payload)

        self.assertEqual(result.download_mbps, 100.0)
        self.assertEqual(result.upload_mbps, 25.0)
        self.assertEqual(result.ping_ms, 12.34)
        self.assertEqual(result.server_id, "123")
        self.assertEqual(result.server_location, "Dallas, TX, United States")

    def test_server_filter_matches_location_country_provider_and_id(self):
        servers = [
            ServerChoice("101", "Lone Star Fiber", "Dallas, TX", "United States", 25.0),
            ServerChoice("202", "London Network", "London", "United Kingdom", 7000.0),
        ]

        self.assertEqual(filter_servers(servers, "Texas"), [servers[0]])
        self.assertEqual(filter_servers(servers, "USA"), [servers[0]])
        self.assertEqual(filter_servers(servers, "Dallas United"), [servers[0]])
        self.assertEqual(filter_servers(servers, "Lone Star"), [servers[0]])
        self.assertEqual(filter_servers(servers, "202"), [servers[1]])

    def test_saved_results_round_trip_and_accept_numeric_strings(self):
        saved = {
            "timestamp": "2026-08-31T12:34:56Z",
            "ping_ms": "9.5",
            "download_mbps": "250.25",
            "upload_mbps": "50.75",
        }
        result = SpeedtestResult.from_dict(saved)
        self.assertEqual(result.download_mbps, 250.25)
        self.assertEqual(result.server_id, "")

    @patch("speedtest_backend.run_ookla")
    def test_only_ookla_runs_when_terms_are_accepted(self, ookla):
        expected = SpeedtestResult("now", 1, 2, 3)
        ookla.return_value = expected

        result = run_speedtest({"accept_ookla_terms": True, "server_id": "7"})

        self.assertIs(result, expected)
        ookla.assert_called_once_with("7")

    @patch("speedtest_backend.run_ookla")
    def test_terms_are_required_before_running_ookla(self, ookla):
        with self.assertRaisesRegex(SpeedtestError, "Accept the Ookla CLI terms"):
            run_speedtest({"accept_ookla_terms": False})
        ookla.assert_not_called()

    @patch("speedtest_backend.run_ookla", side_effect=SpeedtestError("not installed"))
    def test_ookla_errors_do_not_fall_back_to_another_engine(self, _ookla):
        with self.assertRaisesRegex(SpeedtestError, "not installed"):
            run_speedtest({"accept_ookla_terms": True})


class OoklaInstallerTests(unittest.TestCase):
    def test_architecture_aliases_select_the_verified_official_archive(self):
        archive_arch, url, checksum = archive_details("amd64")
        self.assertEqual(archive_arch, "x86_64")
        self.assertEqual(
            url, "https://install.speedtest.net/app/cli/ookla-speedtest-1.2.0-linux-x86_64.tgz"
        )
        self.assertEqual(len(checksum), 64)

    def test_unsupported_architecture_is_rejected(self):
        with self.assertRaises(OoklaInstallError):
            archive_details("mips64")


class SchedulingTests(unittest.TestCase):
    def test_supported_interval_schedules_next_run(self):
        self.assertEqual(next_run_after(1000, 15), 1900)
        self.assertFalse(is_due(1899, 1900, 15))
        self.assertTrue(is_due(1900, 1900, 15))

    def test_manual_and_unsupported_intervals_never_schedule(self):
        self.assertIsNone(next_run_after(1000, 0))
        self.assertIsNone(next_run_after(1000, 12))
        self.assertFalse(is_due(9999, 1000, 0))

    def test_automatic_testing_runs_once_for_each_system_boot(self):
        self.assertTrue(should_run_initial_test(15, "boot-two", "boot-one"))
        self.assertFalse(should_run_initial_test(15, "boot-two", "boot-two"))
        self.assertFalse(should_run_initial_test(0, "boot-two", "boot-one"))
        self.assertFalse(should_run_initial_test(15, "", "boot-one"))

    def test_boot_id_reader_is_safe_when_unavailable(self):
        self.assertEqual(system_boot_id("/path/that/does/not/exist"), "")


class CsvTests(unittest.TestCase):
    def test_csv_writes_one_header_and_appends_results(self):
        result = SpeedtestResult(
            "2026-08-31T12:34:56Z",
            12.345,
            100.555,
            20.444,
            server_id="123",
            server_name="Example ISP",
            server_location="Dallas, United States",
            engine="Ookla CLI",
        )
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "results.csv"
            append_result(str(destination), result)
            append_result(str(destination), result)

            with destination.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["download_mbps"], "100.56")
        self.assertEqual(rows[0]["ping_ms"], "12.35")
        self.assertEqual(rows[0]["server_id"], "123")


class ArtworkTests(unittest.TestCase):
    def test_event_ui_replaces_the_redundant_button_controls_annotation(self):
        source = (
            Path(__file__).parents[1] / "actions" / "speedtest_plus.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn('title="Button controls"', source)

    def test_unassigned_image_control_is_claimed_only_on_a_plain_single_action_key(self):
        should_claim = _load_should_claim_image_control()

        self.assertTrue(should_claim(None, False, False))
        self.assertFalse(should_claim(0, False, False))
        self.assertFalse(should_claim(None, True, False))
        self.assertFalse(should_claim(None, False, True))

    def test_action_icon_is_a_deck_sized_rgba_png(self):
        icon_path = Path(__file__).parents[1] / "assets" / "speedplus-icon.png"
        with icon_path.open("rb") as handle:
            self.assertEqual(handle.read(8), b"\x89PNG\r\n\x1a\n")
            self.assertEqual(handle.read(4), b"\x00\x00\x00\r")
            self.assertEqual(handle.read(4), b"IHDR")
            width, height, bit_depth, color_type = struct.unpack(">IIBB", handle.read(10))

        self.assertEqual((width, height), (256, 256))
        self.assertEqual(bit_depth, 8)
        self.assertEqual(color_type, 6)
        self.assertLess(icon_path.stat().st_size, 300_000)


if __name__ == "__main__":
    unittest.main()
