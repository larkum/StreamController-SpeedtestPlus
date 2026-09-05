import os
import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk

from src.backend.DeckManagement.InputIdentifier import Input
from src.backend.PluginManager.ActionHolder import ActionHolder
from src.backend.PluginManager.ActionInputSupport import ActionInputSupport
from src.backend.PluginManager.PluginBase import PluginBase

from .actions.speedtest_plus import SpeedtestPlusAction
from .ookla_installer import OoklaInstallError, install_ookla_cli
from .speedtest_backend import find_ookla_command


class SpeedtestPlusPlugin(PluginBase):
    def __init__(self):
        super().__init__(use_legacy_locale=False)
        self.has_plugin_settings = True

        self.add_action_holder(
            ActionHolder(
                plugin_base=self,
                action_core=SpeedtestPlusAction,
                action_id_suffix="SpeedtestPlus",
                action_name=self.locale_manager.get("actions.speedtest_plus.name"),
                icon=Gtk.Picture.new_for_filename(os.path.join(self.PATH, "assets", "speedplus-icon.png")),
                description="Runs a configurable Speedtest.net test and keeps the latest result on the key.",
                requirements="Internet access and acceptance of Ookla's EULA, Terms of Use and Privacy Policy for personal, non-commercial use.",
                settings_schema={
                    "server_id": {"type": "string", "default": ""},
                    "server_label": {"type": "string", "default": "Auto-select"},
                    "interval_minutes": {
                        "type": "integer",
                        "default": 0,
                        "values": [0, 5, 10, 15, 30, 60],
                    },
                    "last_automatic_boot_id": {"type": "string", "default": ""},
                    "action_name": {"type": "string", "default": "Speedtest"},
                },
                action_support={
                    Input.Key: ActionInputSupport.SUPPORTED,
                    Input.Dial: ActionInputSupport.UNSUPPORTED,
                    Input.Touchscreen: ActionInputSupport.UNSUPPORTED,
                },
            )
        )

        self.register(
            plugin_name="Speedtest+",
            github_repo="https://github.com/larkum/StreamController-SpeedtestPlus",
            plugin_version="0.1.0",
            app_version="1.5.0-beta.16",
        )

    def get_settings_area(self):
        group = Adw.PreferencesGroup(
            title="Global Speedtest+ settings",
            description="These choices are shared by every Speedtest+ action.",
        )
        settings = self.get_settings() or {}

        terms_row = Adw.SwitchRow(
            title="I accept Ookla's EULA, Terms of Use and Privacy Policy",
            subtitle="I confirm this is for personal, non-commercial use. Required before installing or running the CLI.",
        )
        terms_row.set_active(bool(settings.get("accept_ookla_policies", False)))
        group.add(terms_row)

        policies_row = Adw.ActionRow(
            title="Read Ookla's policies",
            subtitle="Review all three documents before accepting.",
        )
        for label, uri in (
            ("EULA", "https://www.speedtest.net/about/eula"),
            ("Terms", "https://www.speedtest.net/about/terms"),
            ("Privacy", "https://www.speedtest.net/about/privacy"),
        ):
            button = Gtk.Button(label=label, valign=Gtk.Align.CENTER)
            button.connect("clicked", lambda _button, target=uri: Gio.AppInfo.launch_default_for_uri(target, None))
            policies_row.add_suffix(button)
        group.add(policies_row)

        cli_row = Adw.ActionRow()
        install_button = Gtk.Button(valign=Gtk.Align.CENTER)
        cli_row.add_suffix(install_button)
        group.add(cli_row)

        def refresh_cli_row():
            ready = find_ookla_command() is not None
            cli_row.set_title("Ookla CLI ready" if ready else "Ookla CLI not installed")
            cli_row.set_subtitle(
                "All Speedtest+ actions can use the official Ookla engine."
                if ready
                else "Install a private verified copy; no administrator password is needed."
            )
            install_button.set_label("Reinstall" if ready else "Install")
            install_button.set_sensitive(terms_row.get_active())

        def terms_changed(row, _param):
            updated = dict(self.get_settings() or {})
            updated["accept_ookla_policies"] = row.get_active()
            self.set_settings(updated)
            install_button.set_sensitive(row.get_active())

        def install_clicked(button):
            if not terms_row.get_active():
                cli_row.set_title("Accept Ookla's policies first")
                return
            button.set_sensitive(False)
            cli_row.set_title("Installing Ookla CLI…")
            cli_row.set_subtitle("Downloading and verifying the official archive.")

            def worker():
                error = ""
                try:
                    install_ookla_cli()
                except OoklaInstallError as exc:
                    error = str(exc)
                GLib.idle_add(finish_install, error)

            threading.Thread(target=worker, daemon=True).start()

        def finish_install(error):
            if error:
                cli_row.set_title("Ookla CLI installation failed")
                cli_row.set_subtitle(error)
                install_button.set_label("Try again")
                install_button.set_sensitive(terms_row.get_active())
            else:
                refresh_cli_row()
            return False

        terms_row.connect("notify::active", terms_changed)
        install_button.connect("clicked", install_clicked)
        refresh_cli_row()

        csv_row = Adw.SwitchRow(
            title="Save results to CSV",
            subtitle="Save successful results in the folder below, using one shared file or a file for each action.",
        )
        csv_row.set_active(bool(settings.get("save_csv", False)))

        def csv_changed(row, _param):
            updated = dict(self.get_settings() or {})
            updated["save_csv"] = row.get_active()
            self.set_settings(updated)

        csv_row.connect("notify::active", csv_changed)
        group.add(csv_row)

        location_row = Adw.EntryRow(title="CSV file location")
        location_row.set_text(str(settings.get("csv_location", "")))
        location_button = Gtk.Button.new_from_icon_name("folder-open-symbolic")
        location_button.set_tooltip_text("Choose the folder for CSV files")
        location_button.set_valign(Gtk.Align.CENTER)
        location_row.add_suffix(location_button)
        group.add(location_row)

        def location_changed(row, _param):
            updated = dict(self.get_settings() or {})
            updated["csv_location"] = row.get_text().strip()
            self.set_settings(updated)

        def location_response(dialog, response):
            if response == Gtk.ResponseType.ACCEPT:
                selected = dialog.get_file()
                path = selected.get_path() if selected else None
                if path:
                    location_row.set_text(path)
            self._csv_location_dialog = None

        def choose_location(button):
            root = button.get_root()
            parent = root if isinstance(root, Gtk.Window) else None
            dialog = Gtk.FileChooserNative.new(
                "Choose CSV file location",
                parent,
                Gtk.FileChooserAction.SELECT_FOLDER,
                "Select",
                "Cancel",
            )
            dialog.connect("response", location_response)
            self._csv_location_dialog = dialog
            dialog.show()

        location_row.connect("notify::text", location_changed)
        location_button.connect("clicked", choose_location)

        individual_row = Adw.SwitchRow(
            title="Save each action to an individual CSV file",
            subtitle="Uses each action's name as its filename; otherwise all actions share speedtest-results.csv.",
        )
        individual_row.set_active(bool(settings.get("individual_csv_files", False)))

        def individual_changed(row, _param):
            updated = dict(self.get_settings() or {})
            updated["individual_csv_files"] = row.get_active()
            self.set_settings(updated)

        individual_row.connect("notify::active", individual_changed)
        group.add(individual_row)
        return group

    def open_global_settings(self, parent=None):
        from src.windows.Settings.PluginSettingsWindow.PluginSettingsWindow import (
            PluginSettingsWindow,
        )

        dialog = PluginSettingsWindow(self)
        dialog.present(parent)
        return dialog
