# Speedtest+

Speedtest+ is an enhanced GPL-3.0 fork of the original
[StreamController Speedtest plugin](https://github.com/StreamController/Speedtest).

Its original gauge-and-plus icon is designed for Speedtest+ and does not copy
Ookla's trademarked logo.

It puts the latest test time, ping, download speed, and upload speed on a
Stream Deck key. Press the key to run a test, or schedule a test every 5, 10,
15, 30, or 60 minutes.

## Features

- Uses Speedtest.net servers
- Automatic best-server selection
- Search servers worldwide by city, country, US state name/abbreviation, provider, or server ID
- Enter a known Speedtest.net server ID for an advanced fixed-server override
- Remembers the selected server for each action
- Background testing so the StreamController interface stays responsive
- Automatic 5, 10, 15, 30, or 60 minute schedules
- One immediate automatic test after each Linux system boot when scheduling is enabled
- Optional CSV history with a user-selected destination
- Preserves decimal results rather than rounding to whole Mbps
- Colour-coded key display: light-blue time/ping, yellow download, and red upload
- Automatic label fitting for different key sizes and result lengths
- Larger speed labels without repeated unit suffixes; download/upload are always Mbps
- Short press runs a test; long hold opens the latest result in the default browser

## Official Ookla CLI

Speedtest+ uses only Ookla's official measurement engine. It does not
redistribute Ookla's proprietary executable. After the user accepts Ookla's
terms in the action settings, the plugin can download the correct Linux archive
directly from Ookla, verify it, and install a private copy in the user's app-data
folder. This needs no administrator password and does not modify the operating
system. An existing official system installation is also detected.

The Ookla CLI is offered for personal, non-commercial use. Automatic selection
is performed by Ookla. A worldwide search can instead remember a specific
Speedtest.net server for the action.

## CSV columns

`timestamp`, `ping_ms`, `download_mbps`, `upload_mbps`, `server_id`,
`server_name`, `server_location`, `result_url`, and `engine`.

## Licence and attribution

Speedtest+ remains licensed under GPL-3.0. The original plugin was created by
Core447 for StreamController. Enhancements and ongoing maintenance are by
Larkum. Speedtest is a trademark of Ookla; this community plugin is not
affiliated with or endorsed by Ookla.
