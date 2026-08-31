import os

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk

from src.backend.DeckManagement.InputIdentifier import Input
from src.backend.PluginManager.ActionHolder import ActionHolder
from src.backend.PluginManager.ActionInputSupport import ActionInputSupport
from src.backend.PluginManager.PluginBase import PluginBase

from .actions.speedtest_plus import SpeedtestPlusAction


class SpeedtestPlusPlugin(PluginBase):
    def __init__(self):
        super().__init__(use_legacy_locale=False)

        self.add_action_holder(
            ActionHolder(
                plugin_base=self,
                action_core=SpeedtestPlusAction,
                action_id_suffix="SpeedtestPlus",
                action_name=self.locale_manager.get("actions.speedtest_plus.name"),
                icon=Gtk.Picture.new_for_filename(os.path.join(self.PATH, "assets", "speedplus-icon.png")),
                description="Runs a configurable Speedtest.net test and keeps the latest result on the key.",
                requirements="Internet access and acceptance of Ookla's CLI terms for personal, non-commercial use.",
                settings_schema={
                    "accept_ookla_terms": {"type": "boolean", "default": False},
                    "server_id": {"type": "string", "default": ""},
                    "server_label": {"type": "string", "default": "Auto-select"},
                    "interval_minutes": {
                        "type": "integer",
                        "default": 0,
                        "values": [0, 5, 10, 15, 30, 60],
                    },
                    "last_automatic_boot_id": {"type": "string", "default": ""},
                    "save_csv": {"type": "boolean", "default": False},
                    "csv_path": {"type": "string", "default": ""},
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
