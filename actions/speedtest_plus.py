from __future__ import annotations

import os
import threading
import time
from datetime import datetime

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk
from loguru import logger as log

from src.backend.PluginManager.ActionCore import ActionCore
from src.backend.PluginManager.EventAssigner import EventAssigner
from src.backend.PluginManager.InputBases import Input as EventInput

from ..csv_logger import append_result
from ..ookla_installer import OoklaInstallError, install_ookla_cli
from ..scheduling import ALLOWED_INTERVALS, is_due, next_run_after, should_run_initial_test, system_boot_id
from ..speedtest_backend import (
    ServerChoice,
    SpeedtestError,
    SpeedtestResult,
    discover_servers,
    find_ookla_command,
    is_speedtest_result_url,
    run_speedtest,
)


TEST_LOCK = threading.Lock()
TIME_PING_COLOR = [135, 206, 250, 255]
DOWNLOAD_COLOR = [255, 215, 0, 255]
UPLOAD_COLOR = [255, 82, 82, 255]
INTERVAL_LABELS = (
    "Manual only",
    "Every 5 minutes",
    "Every 10 minutes",
    "Every 15 minutes",
    "Every 30 minutes",
    "Every 60 minutes",
)


def display_lines(result: SpeedtestResult) -> tuple[str, str, str]:
    try:
        timestamp = datetime.fromisoformat(result.timestamp.replace("Z", "+00:00")).astimezone()
        time_text = timestamp.strftime("%H:%M")
    except (TypeError, ValueError):
        time_text = "--:--"
    return (
        f"{time_text} · Ping {result.ping_ms:.1f} ms",
        f"↓ {result.download_mbps:.1f}",
        f"↑ {result.upload_mbps:.1f}",
    )


def should_claim_image_control(
    image_control_index: int | None, is_multi_action: bool, has_user_asset: bool
) -> bool:
    return image_control_index is None and not is_multi_action and not has_user_asset


class SpeedtestPlusAction(ActionCore):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.has_configuration = True
        self.allow_event_configuration = True
        self._running = False
        self._server_choices: list[ServerChoice | None] = [None]
        self._loading_server_model = False
        self._syncing_server_id = False
        self._file_dialog = None
        self._config_generation = 0
        self.event_manager.add_event_assigner(
            EventAssigner(
                id="run-speedtest",
                ui_label="Run speed test",
                default_event=EventInput.Key.Events.SHORT_UP,
                callback=lambda _event: self._start_test(),
            )
        )
        self.event_manager.add_event_assigner(
            EventAssigner(
                id="open-speedtest-result",
                ui_label="Open latest result in browser",
                default_event=EventInput.Key.Events.HOLD_START,
                callback=lambda _event: self._open_last_result(),
            )
        )

    def on_ready(self):
        settings = self.get_settings() or {}
        interval = int(settings.get("interval_minutes", 0) or 0)
        boot_id = system_boot_id()
        if should_run_initial_test(interval, boot_id, str(settings.get("last_automatic_boot_id", ""))):
            self._update_settings(
                last_automatic_boot_id=boot_id,
                next_run_epoch=next_run_after(time.time(), interval),
            )
            GLib.idle_add(self._start_test)
        elif interval and not settings.get("next_run_epoch"):
            self._update_settings(next_run_epoch=next_run_after(time.time(), interval))
        self._render_saved_result()

    def on_update(self):
        self._render_saved_result()

    def on_tick(self):
        if self._running:
            return
        settings = self.get_settings() or {}
        interval = int(settings.get("interval_minutes", 0) or 0)
        if is_due(time.time(), settings.get("next_run_epoch"), interval):
            self._start_test()

    def _start_test(self):
        if self._running:
            return
        settings = dict(self.get_settings() or {})
        self._running = True
        self.hide_error()
        self.set_media(image=None, update=False)
        self.set_top_label(
            datetime.now().strftime("%H:%M"), color=TIME_PING_COLOR, font_size=11, update=False
        )
        self.set_center_label("Testing…", color=DOWNLOAD_COLOR, font_size=14, update=False)
        self.set_bottom_label("Please wait", color=UPLOAD_COLOR, font_size=9)
        threading.Thread(target=self._run_test_worker, args=(settings,), daemon=True).start()

    def _open_last_result(self):
        raw = (self.get_settings() or {}).get("last_result")
        result_url = str(raw.get("result_url", "")).strip() if isinstance(raw, dict) else ""
        if not is_speedtest_result_url(result_url):
            log.warning("Speedtest+ has no valid saved result URL to open")
            self.show_error()
            GLib.timeout_add_seconds(2, self._hide_transient_error)
            return
        try:
            Gio.AppInfo.launch_default_for_uri(result_url, None)
        except GLib.Error as exc:
            log.error(f"Speedtest+ could not open the result URL: {exc}")
            self.show_error()
            GLib.timeout_add_seconds(2, self._hide_transient_error)

    def _hide_transient_error(self):
        self.hide_error()
        return False

    def _run_test_worker(self, settings: dict):
        if not TEST_LOCK.acquire(blocking=False):
            GLib.idle_add(self._finish_test, None, "Another speed test is already running.", "")
            return
        result = None
        error = ""
        csv_error = ""
        try:
            result = run_speedtest(settings)
            if settings.get("save_csv"):
                csv_path = str(settings.get("csv_path", "")).strip()
                if not csv_path:
                    csv_error = "Choose a CSV destination in the action settings."
                else:
                    try:
                        append_result(csv_path, result)
                    except Exception as exc:
                        csv_error = str(exc)
        except SpeedtestError as exc:
            error = str(exc)
        except Exception as exc:
            log.exception("Unexpected Speedtest+ failure")
            error = f"Unexpected error: {exc}"
        finally:
            TEST_LOCK.release()
        GLib.idle_add(self._finish_test, result, error, csv_error)

    def _finish_test(self, result: SpeedtestResult | None, error: str, csv_error: str):
        self._running = False
        settings = self.get_settings() or {}
        interval = int(settings.get("interval_minutes", 0) or 0)
        updates = {
            "next_run_epoch": next_run_after(time.time(), interval),
            "last_error": error,
            "last_csv_error": csv_error,
        }
        if result is not None:
            updates["last_result"] = result.to_dict()
        self._update_settings(**updates)
        if error:
            self.set_top_label("Speedtest+", color=TIME_PING_COLOR, font_size=11, update=False)
            self.set_center_label("Error", color=UPLOAD_COLOR, font_size=16, update=False)
            self.set_bottom_label(error[:28], color=UPLOAD_COLOR, font_size=7)
            self.show_error()
        elif result is not None:
            self._render_result(result)
            if csv_error:
                log.error(f"Speedtest+ CSV export failed: {csv_error}")
                self.show_error(2)
        return False

    def _render_saved_result(self):
        raw = (self.get_settings() or {}).get("last_result")
        if isinstance(raw, dict):
            try:
                self._render_result(SpeedtestResult.from_dict(raw))
                return
            except (TypeError, ValueError):
                pass
        self.hide_error()
        self._claim_unassigned_image_control()
        self.set_media(
            media_path=os.path.join(self.plugin_base.PATH, "assets", "speedplus-icon.png"),
            size=0.72,
            valign=-0.65,
            update=False,
        )
        self.set_top_label(None, update=False)
        self.set_center_label(None, update=False)
        self.set_bottom_label("Press to Run", color=TIME_PING_COLOR, font_size=9)

    def _claim_unassigned_image_control(self):
        state = self.get_state()
        if state is None:
            return
        permission_manager = getattr(state, "action_permission_manager", None)
        if permission_manager is None:
            return
        image_control_index = permission_manager.get_image_control_index()
        if not should_claim_image_control(
            image_control_index,
            bool(self.get_is_multi_action()),
            bool(self.has_custom_user_asset()),
        ):
            return
        action_index = self.get_own_action_index()
        if action_index is None or action_index < 0:
            return
        permission_manager.set_image_control_index(
            action_index, reload_pages=False, reload_self=False
        )

    def _render_result(self, result: SpeedtestResult):
        top, center, bottom = display_lines(result)
        self.hide_error()
        self.set_media(image=None, update=False)
        self.set_top_label(
            top,
            color=TIME_PING_COLOR,
            font_size=self._fitted_font_size(top, preferred=9, minimum=6),
            update=False,
        )
        self.set_center_label(
            center,
            color=DOWNLOAD_COLOR,
            font_size=self._fitted_font_size(center, preferred=14, minimum=9),
            update=False,
        )
        self.set_bottom_label(
            bottom,
            color=UPLOAD_COLOR,
            font_size=self._fitted_font_size(bottom, preferred=14, minimum=9),
        )

    def _fitted_font_size(self, text, preferred, minimum):
        controller_input = self.get_input()
        key_width = controller_input.get_image_size()[0]
        available_width = max(12, key_width - max(10, round(key_width * 0.14)))

        try:
            from src.backend.DeckManagement.Subclasses.KeyLabel import KeyLabel

            def measure_width(value, font_size):
                try:
                    label = KeyLabel(controller_input=controller_input, text=value, font_size=font_size)
                    left, _, right, _ = label.get_font().getbbox(value)
                    return right - left
                except Exception:
                    return len(value) * font_size * 0.6
        except Exception:
            measure_width = lambda value, font_size: len(value) * font_size * 0.6

        for font_size in range(preferred, minimum - 1, -1):
            if measure_width(text, font_size) <= available_width:
                return font_size
        return minimum

    def _update_settings(self, **values):
        settings = dict(self.get_settings() or {})
        settings.update(values)
        self.set_settings(settings)

    def get_config_rows(self):
        settings = dict(self.get_settings() or {})
        self._config_generation += 1
        generation = self._config_generation

        self.terms_row = Adw.SwitchRow(
            title="I accept Ookla's CLI terms",
            subtitle="Required before downloading or running Ookla's Speedtest CLI.",
        )
        self.terms_row.set_active(bool(settings.get("accept_ookla_terms", False)))
        terms_button = Gtk.Button(label="View terms")
        terms_button.set_valign(Gtk.Align.CENTER)
        terms_button.connect(
            "clicked", lambda *_: Gio.AppInfo.launch_default_for_uri("https://www.speedtest.net/about/eula", None)
        )
        self.terms_row.add_suffix(terms_button)
        self.terms_row.connect("notify::active", self._on_terms_changed)

        cli_ready = find_ookla_command() is not None
        self.cli_status_row = Adw.ActionRow(
            title="Ookla CLI ready" if cli_ready else "Ookla CLI not installed",
            subtitle=(
                "Speedtest+ will use the official Ookla measurement engine."
                if cli_ready
                else "Install a private copy directly from Ookla; no administrator password is needed."
            ),
        )
        self.install_button = Gtk.Button(label="Reinstall" if cli_ready else "Install")
        self.install_button.set_valign(Gtk.Align.CENTER)
        self.install_button.set_sensitive(self.terms_row.get_active())
        self.install_button.connect("clicked", self._on_install_cli, generation)
        self.cli_status_row.add_suffix(self.install_button)

        self.server_search_row = Adw.EntryRow(title="Find servers worldwide by location, provider, or ID")
        self.server_search_row.set_text(str(settings.get("server_search", "")))
        refresh = Gtk.Button.new_from_icon_name("view-refresh-symbolic")
        refresh.set_tooltip_text("Search available Speedtest.net servers")
        refresh.set_valign(Gtk.Align.CENTER)
        refresh.connect("clicked", self._on_find_servers, generation)
        self.server_search_row.add_suffix(refresh)

        selected_id = str(settings.get("server_id", ""))
        selected_label = str(settings.get("server_label", ""))
        labels = ["Auto-select the best server"]
        self._server_choices = [None]
        if selected_id:
            remembered = ServerChoice(selected_id, "", selected_label or "Remembered server", "")
            labels.append(selected_label or remembered.label)
            self._server_choices.append(remembered)
        self.server_row = self._combo_row(
            "Speedtest.net server",
            "Auto-select or search above; your choice is remembered.",
            labels,
            1 if selected_id else 0,
        )
        self.server_row.connect("notify::selected", self._on_server_changed)
        self.server_status_row = Adw.ActionRow(
            title="Worldwide server search ready",
            subtitle="Enter a city, state, country, provider, or server ID and press refresh.",
        )

        self.server_id_row = Adw.EntryRow(title="Specific server ID (optional)")
        self.server_id_row.set_text(selected_id)
        self.server_id_row.add_suffix(self._small_label("Advanced"))
        self.server_id_row.connect("notify::text", self._on_server_id_changed)

        self.units_row = Adw.ActionRow(
            title="Measurement units",
            subtitle="Download and upload are always displayed and saved as Mbps. Ping is shown in ms.",
        )

        self.controls_row = Adw.ActionRow(
            title="Button controls",
            subtitle="Press briefly to run a test. Hold to open the latest result in your browser.",
        )

        interval = int(settings.get("interval_minutes", 0) or 0)
        selected_interval = ALLOWED_INTERVALS.index(interval) if interval in ALLOWED_INTERVALS else 0
        self.interval_row = self._combo_row(
            "Automatic testing",
            "Runs once after each system boot, then at the selected interval. A short press runs it now.",
            list(INTERVAL_LABELS),
            selected_interval,
        )
        self.interval_row.connect("notify::selected", self._on_interval_changed)

        self.csv_switch = Adw.SwitchRow(
            title="Save every result to CSV",
            subtitle="Import the file into LibreOffice Calc, Google Sheets, or another spreadsheet app.",
        )
        self.csv_switch.set_active(bool(settings.get("save_csv", False)))
        self.csv_switch.connect("notify::active", self._on_csv_switch_changed)

        self.csv_path_row = Adw.EntryRow(title="CSV destination")
        self.csv_path_row.set_text(str(settings.get("csv_path", "")))
        browse = Gtk.Button.new_from_icon_name("folder-open-symbolic")
        browse.set_tooltip_text("Choose CSV destination")
        browse.set_valign(Gtk.Align.CENTER)
        browse.connect("clicked", self._on_choose_csv)
        self.csv_path_row.add_suffix(browse)
        self.csv_path_row.connect("notify::text", self._on_csv_path_changed)

        return [
            self.terms_row,
            self.cli_status_row,
            self.server_search_row,
            self.server_row,
            self.server_status_row,
            self.server_id_row,
            self.units_row,
            self.controls_row,
            self.interval_row,
            self.csv_switch,
            self.csv_path_row,
        ]

    @staticmethod
    def _combo_row(title: str, subtitle: str, labels: list[str], selected: int):
        row = Adw.ComboRow(title=title, subtitle=subtitle)
        row.set_model(Gtk.StringList.new(labels))
        row.set_selected(selected)
        return row

    @staticmethod
    def _small_label(text: str):
        label = Gtk.Label(label=text)
        label.add_css_class("dim-label")
        label.set_valign(Gtk.Align.CENTER)
        return label

    def _on_terms_changed(self, row, _param):
        self._update_settings(accept_ookla_terms=row.get_active())
        if hasattr(self, "install_button"):
            self.install_button.set_sensitive(row.get_active())

    def _on_install_cli(self, button, generation):
        if not (self.get_settings() or {}).get("accept_ookla_terms", False):
            self.cli_status_row.set_title("Accept Ookla's terms first")
            return
        button.set_sensitive(False)
        self.cli_status_row.set_title("Installing Ookla CLI…")
        self.cli_status_row.set_subtitle("Downloading securely and verifying the official archive.")

        def worker():
            error = ""
            try:
                install_ookla_cli()
            except OoklaInstallError as exc:
                error = str(exc)
            GLib.idle_add(self._finish_cli_install, error, button, generation)

        threading.Thread(target=worker, daemon=True).start()

    def _finish_cli_install(self, error, button, generation):
        if generation != self._config_generation:
            return False
        button.set_sensitive(self.terms_row.get_active())
        if error:
            button.set_label("Try again")
            self.cli_status_row.set_title("Ookla CLI installation failed")
            self.cli_status_row.set_subtitle(error)
        else:
            button.set_label("Reinstall")
            self.cli_status_row.set_title("Ookla CLI ready")
            self.cli_status_row.set_subtitle("Speedtest+ will use the official Ookla measurement engine.")
        return False

    def _on_find_servers(self, button, generation):
        query = self.server_search_row.get_text().strip()
        self._update_settings(server_search=query)
        button.set_sensitive(False)
        self.server_status_row.set_title("Searching Speedtest.net servers worldwide…")
        self.server_status_row.set_subtitle("This can take a few seconds.")

        def worker():
            choices = []
            error = ""
            try:
                choices = discover_servers(query)
            except SpeedtestError as exc:
                error = str(exc)
            GLib.idle_add(self._finish_server_search, choices, error, button, generation)

        threading.Thread(target=worker, daemon=True).start()

    def _finish_server_search(self, choices, error, button, generation):
        if generation != self._config_generation:
            return False
        button.set_sensitive(True)
        if error:
            self.server_status_row.set_title("Server search failed")
            self.server_status_row.set_subtitle(error)
            return False
        selected_id = str((self.get_settings() or {}).get("server_id", ""))
        self._server_choices = [None, *choices]
        selected_index = next(
            (index for index, choice in enumerate(self._server_choices) if choice and choice.id == selected_id), 0
        )
        self._loading_server_model = True
        try:
            self.server_row.set_model(
                Gtk.StringList.new(["Auto-select the best server", *[choice.label for choice in choices]])
            )
            self.server_row.set_selected(selected_index)
        finally:
            self._loading_server_model = False
        self.server_status_row.set_title(f"{len(choices)} matching servers")
        self.server_status_row.set_subtitle(
            "Select one above, use a known server ID below, or leave automatic selection enabled."
        )
        return False

    def _on_server_changed(self, row, _param):
        if self._loading_server_model:
            return
        index = row.get_selected()
        choice = self._server_choices[index] if index < len(self._server_choices) else None
        self._update_settings(server_id=choice.id if choice else "", server_label=choice.label if choice else "Auto-select")
        if hasattr(self, "server_id_row"):
            self._syncing_server_id = True
            try:
                self.server_id_row.set_text(choice.id if choice else "")
            finally:
                self._syncing_server_id = False

    def _on_server_id_changed(self, row, _param):
        if self._syncing_server_id:
            return
        server_id = row.get_text().strip()
        current = self.get_settings() or {}
        label = current.get("server_label", "") if server_id == str(current.get("server_id", "")) else ""
        self._update_settings(
            server_id=server_id,
            server_label=label or (f"Server #{server_id}" if server_id else "Auto-select"),
        )

    def _on_interval_changed(self, row, _param):
        interval = ALLOWED_INTERVALS[min(row.get_selected(), len(ALLOWED_INTERVALS) - 1)]
        self._update_settings(interval_minutes=interval, next_run_epoch=next_run_after(time.time(), interval))

    def _on_csv_switch_changed(self, row, _param):
        self._update_settings(save_csv=row.get_active())

    def _on_csv_path_changed(self, row, _param):
        self._update_settings(csv_path=row.get_text())

    def _on_choose_csv(self, button):
        root = button.get_root()
        parent = root if isinstance(root, Gtk.Window) else None
        dialog = Gtk.FileChooserNative.new(
            "Choose Speedtest+ CSV destination", parent, Gtk.FileChooserAction.SAVE, "Select", "Cancel"
        )
        dialog.set_current_name("speedtest-results.csv")
        csv_filter = Gtk.FileFilter()
        csv_filter.set_name("CSV files")
        csv_filter.add_pattern("*.csv")
        dialog.add_filter(csv_filter)
        dialog.connect("response", self._on_csv_dialog_response)
        self._file_dialog = dialog
        dialog.show()

    def _on_csv_dialog_response(self, dialog, response):
        if response == Gtk.ResponseType.ACCEPT:
            selected = dialog.get_file()
            path = selected.get_path() if selected else None
            if path:
                if not path.casefold().endswith(".csv"):
                    path += ".csv"
                self.csv_path_row.set_text(path)
                self._update_settings(csv_path=path, save_csv=True)
                self.csv_switch.set_active(True)
        self._file_dialog = None
