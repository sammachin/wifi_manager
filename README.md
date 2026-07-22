# WiFi Manager

A [Tildagon](https://tildagon.badge.emfcamp.org/) (EMF 2024 badge) app to store,
manage, activate and share Wi-Fi profiles on your badge.

The badge normally holds a single Wi-Fi credential in its system settings, so
switching networks means retyping the SSID and password. WiFi Manager keeps a
library of named profiles and lets you activate any of them with a couple of
button presses — and share them badge-to-badge over ESP-NOW.

## Features

- **Multiple profiles** — store as many named Wi-Fi networks as you like.
- **WPA2-PSK and WPA2-Enterprise** — an optional enterprise identity per profile
  (e.g. EMF's `badge`/`badge` RADIUS login). Leave the identity blank for a
  normal home/PSK network.
- **Activate** — writes the badge's `wifi_ssid`, `wifi_password` and
  `wifi_wpa2ent_username` settings and reconnects immediately.
- **Import current Wi-Fi** — capture whatever the badge is currently set to as a
  new profile.
- **Edit / rename / delete** profiles.
- **Share via ESP-NOW** — broadcast a profile; another badge in *Receive* mode is
  prompted to save it. Works badge-to-badge with no pairing (Tildagon OS ≥ 1.9.0).

## Usage

1. Open **WiFi Manager** from the badge menu.
2. The main list shows your saved profiles followed by:
   - `Add network` — enter SSID, password, and (optionally) an enterprise
     identity.
   - `Import` — save the badge's current network as a profile.
   - `Receive` — listen for a profile broadcast by another badge.
3. Select a profile to **Activate / Share / Edit / Rename / Delete** it.
4. To share: on badge A pick a profile → *Share via ESP-NOW*; on badge B pick
   *Receive shared...*. Badge B will prompt to save what it receives.

Buttons: up/down to move, **CONFIRM** to select, **CANCEL** to go back (and to
leave Share/Receive mode).

## ⚠️ Security note

Profiles are shared as **plaintext ESP-NOW broadcasts**. Any badge in receive
mode within radio range can read the SSID and password while you are sharing.
This is intentional for the badge's social, share-with-friends use case — but
don't use it to move credentials you actually care about protecting.

A future version could add a short PIN to lightly obfuscate the payload.

## Files

| File | Purpose |
|------|---------|
| `app.py` | Entry point + UI state machine (`WiFiManager`) |
| `wifim_store.py` | Profile persistence (JSON at `/wifi_manager.json`) |
| `wifim_wifi.py` | Activate a profile / import current settings |
| `wifim_espnow.py` | ESP-NOW broadcast send + receive |
| `tildagon.toml` | App manifest |

Helper modules are prefixed `wifim_` so they never shadow the firmware's own
`wifi` module.

## Install (local / development)

Tildagon OS has no TOML parser, so a locally sideloaded app is discovered via
`metadata.json` (the app store instead generates its manifest from
`tildagon.toml`). This repo ships a ready `metadata.json`:

```json
{ "name": "WiFi Manager", "path": "apps.sammachin_tildagon_wifi_manager.app" }
```

`path` is a Python import path (`apps.<folder>.<module>`), so **the badge folder
must be `wifi_manager`** — underscore, not the repo's hyphenated name (hyphens
are illegal in module names). The loader imports that module and runs the class
named by `__app_export__` (`WiFiManager`).

With the badge connected over USB-C (IN port) and `mpremote` installed:

```bash
mpremote mkdir apps
mpremote mkdir apps/sammachin_tildagon_wifi_manager
mpremote cp app.py wifim_store.py wifim_wifi.py wifim_espnow.py  metadata.json  :/apps/sammachin_tildagon_wifi_manager/
```

Then reboot the badge (hold the reboot button ~2s) and launch **WiFi Manager**
from the menu. Sharing/receiving requires Tildagon OS ≥ 1.9.0 on both badges.

> Remove `metadata.json` before publishing to the app store — it's a
> development-only file; the store uses `tildagon.toml`.

## License

MIT
