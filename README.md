# Speedtest+

![Speedtest+ banner](store/Thumbnail.png)

Speedtest+ puts a complete Speedtest.net result on a StreamController key. Run a test on demand or automatically, choose the server you want, keep a CSV history, and open the latest shareable result in your browser.

Speedtest+ is an enhanced GPL-3.0 fork of the original [StreamController Speedtest plugin](https://github.com/StreamController/Speedtest) by Core447.

## Features

- Official Ookla Speedtest CLI measurement engine
- Ping, download speed, upload speed, and test time on one key
- Download and upload results displayed in decimal Mbps; ping displayed in ms
- Worldwide server search by city, country, US state, provider, or server ID
- Automatic best-server selection or a remembered server for each action
- Manual tests with a short key press
- Latest Speedtest.net result opened with a long key hold
- Automatic tests every 5, 10, 15, 30, or 60 minutes
- An initial test after Linux starts when automatic testing is enabled
- Optional CSV history saved to a destination you choose
- Background testing that keeps StreamController responsive
- Colour-coded, automatically fitted key labels

## Requirements

- Linux
- StreamController 1.5.0-beta.16 or newer
- An internet connection
- Acceptance of Ookla's CLI terms for personal, non-commercial use

The built-in installer supports x86_64/AMD64, ARM64/AArch64, ARMv7, ARMv6, and 32-bit x86 Linux systems.

## Manual installation

Use these instructions to test Speedtest+ before it is available in the StreamController Store.

### Download the ZIP

1. Open the [Speedtest+ GitHub repository](https://github.com/larkum/StreamController-SpeedtestPlus).
2. Select **Code**, then **Download ZIP**.
3. Extract the downloaded ZIP file.
4. Rename the extracted `StreamController-SpeedtestPlus-main` folder to `com_larkum_SpeedtestPlus`.
5. Copy that entire folder into StreamController's plugin directory.

For the Flatpak version of StreamController, the finished location must be:

```text
~/.var/app/com.core447.StreamController/data/plugins/com_larkum_SpeedtestPlus
```

Make sure `manifest.json` is directly inside `com_larkum_SpeedtestPlus`; an extra nested folder will prevent StreamController from finding the plugin. Completely close and reopen StreamController after copying it, then add **Speedtest+ → Speedtest+** to a key.

### Install with Git

Alternatively, close StreamController and run:

```bash
git clone https://github.com/larkum/StreamController-SpeedtestPlus.git \
  ~/.var/app/com.core447.StreamController/data/plugins/com_larkum_SpeedtestPlus
```

Reopen StreamController when the download finishes. To update this Git installation later, close StreamController and run `git pull` inside the `com_larkum_SpeedtestPlus` folder.

If a previous manual copy is already installed, close StreamController and replace that plugin folder with the newly downloaded version. Your key settings are stored by StreamController and are separate from the plugin files.

## Set up Speedtest+

1. Open **Settings → Plugins → Speedtest+ → Open Settings**.
2. Select **View terms**, read Ookla's terms, and enable **I accept Ookla's CLI terms** if you agree.
3. Select **Install** beside **Ookla CLI not installed**.
4. Add **Speedtest+ → Speedtest+** to a key.
5. Leave the server set to **Auto-select the best server**, or search for a specific server in the action settings.
6. Briefly press the key to run your first test.

The terms choice and CLI installation are global and shared by every Speedtest+ action. Each action starts with a setup-status row and a **Global Settings** button, so incomplete setup is clearly identified and can be opened directly from the action panel.

The installer downloads the official Ookla CLI directly from Ookla, verifies the download, and keeps a private copy in your user data. It does not need an administrator password and does not modify the operating system. If the official CLI is already installed on the system, Speedtest+ can use it.

## Choose a server

Automatic selection lets Ookla choose a suitable nearby server. To select your own:

1. Enter a city, country, US state or abbreviation, provider, or server ID in **Find servers worldwide**.
2. Select the refresh button and wait for the matching servers to appear.
3. Choose a server from **Speedtest.net server**.

The selection is remembered for that action. Choose **Auto-select the best server** to return to automatic selection. If you already know a Speedtest.net server ID, you can enter it in the advanced **Specific server ID** field.

Examples of useful searches include `Texas`, `TX`, `Dallas`, `United Kingdom`, `London`, a provider name, or a numeric server ID.

## Key controls and display

- **Short press:** run a new speed test.
- **Long hold:** open the latest shareable result on Speedtest.net in the default browser.

The key shows the test time, ping, download speed, and upload speed. Time and ping use light blue, download uses yellow, and upload uses red. Text automatically becomes smaller when needed to fit the key.

Before the first successful test, the key displays the Speedtest+ logo with **Press to Run** at the bottom.

Download and upload are always measured in **Mbps**. The unit is omitted from the key to leave more room for the result.

## Automatic testing

Use **Automatic testing** to select 5, 10, 15, 30, or 60 minutes. When enabled, Speedtest+ runs one initial test after each Linux system boot and then continues at the chosen interval.

Select **Manual only** to disable scheduled tests. A short press still starts a test at any time.

Automatic speed tests can use significant bandwidth, particularly on fast connections or short schedules. Choose an interval that suits your connection and data allowance.

## Save results to CSV

Open **Settings → Plugins → Speedtest+ → Open Settings**, enable **Save results to CSV**, and choose the **CSV file location** folder. Speedtest+ creates files there when successful tests finish and appends each later result.

Enable **Save each action to an individual CSV file** to use each action's **Action name** as its filename—for example `Home.csv`, `Office.csv`, and `Automatic.csv`. When the option is disabled, every action appends to `speedtest-results.csv` in the selected folder. Each file can be imported into LibreOffice Calc, Google Sheets, or another spreadsheet application.

The CSV contains:

| Column | Description |
| --- | --- |
| `timestamp` | Date and time reported by the test |
| `ping_ms` | Ping latency in milliseconds |
| `download_mbps` | Download speed in decimal megabits per second |
| `upload_mbps` | Upload speed in decimal megabits per second |
| `server_id` | Speedtest.net server ID |
| `server_name` | Server provider or sponsor |
| `server_location` | Server city and country |
| `result_url` | Shareable Speedtest.net result link, when available |
| `engine` | Measurement engine used for the test |

## Privacy and network use

Tests connect to Speedtest.net and the selected test server. Server discovery also contacts Speedtest.net. If CSV logging is enabled, results are stored only in the local file you select. Speedtest+ does not upload the CSV file.

## Troubleshooting

- **The key asks me to accept the terms:** open **Settings → Plugins → Speedtest+ → Open Settings**, or use **Global Settings** at the top of the action panel.
- **The CLI will not install:** confirm the internet connection and that the processor is listed under Requirements, then try **Install** or **Reinstall** again.
- **A server search returns no results:** try a broader city, region, country, provider, or state abbreviation, then press refresh again.
- **A remembered server stops working:** select automatic server choice or search for another server; individual Speedtest.net servers can become unavailable.
- **No CSV row appears:** choose a writable **CSV file location** and make sure **Save results to CSV** is enabled in global plugin settings. Only successful tests are saved.
- **A long hold does nothing:** run a successful test first. Only valid HTTPS result links on Speedtest.net are opened.

## Licence and attribution

Speedtest+ is licensed under [GPL-3.0](LICENSE). The original StreamController Speedtest plugin was created by Core447; Speedtest+ enhancements and maintenance are by Larkum.

Speedtest is a trademark of Ookla. Speedtest+ is an independent community plugin and is not affiliated with or endorsed by Ookla. Its original gauge-and-plus artwork does not copy Ookla's logo, and the plugin does not redistribute Ookla's proprietary executable.
