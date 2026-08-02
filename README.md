# WiFi Manager

A [Tildagon](https://tildagon.badge.emfcamp.org/) app to store,
manage, activate and share Wi-Fi profiles on your badge.

The badge normally holds a single Wi-Fi credential in its system settings, so
switching networks means retyping the SSID and password. WiFi Manager keeps a
library of named profiles and lets you activate any of them with a couple of
button presses — and share them badge-to-badge over ESP-NOW.

[![Install to Tildagon badge](https://s3.sammachin.com/sideload/badge.svg)](https://s3.sammachin.com/sideload)

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
- **Receive over ESP-NOW *and* Bluetooth** — *Receive* mode listens on both
  transports at once, so a profile can arrive from another badge (ESP-NOW) or
  from a desktop browser (Web Bluetooth). The badge only ever *receives* over
  BLE; badge-to-badge sending stays ESP-NOW.
- **Send from a desktop browser** — [`web/index.html`](web/index.html) is a
  standalone Web Bluetooth page: type a network in Chrome/Edge/Vivaldi and push it
  straight to a badge that's in *Receive* mode. No app install.

## Usage

1. Open **WiFi Manager** from the badge menu.
2. The main list shows your saved profiles followed by:
   - `Add network` — enter SSID, password, and (optionally) an enterprise
     identity.
   - `Import` — save the badge's current network as a profile.
   - `Receive` — listen for a profile from another badge (ESP-NOW) *or* a
     desktop browser (Bluetooth), at the same time.
3. Select a profile to **Activate / Share / Edit / Rename / Delete** it.
4. To share: on badge A pick a profile → *Share via ESP-NOW*; on badge B pick
   *Receive shared...*. Badge B will prompt to save what it receives.

Buttons: up/down to move, **CONFIRM** to select, **CANCEL** to go back (and to
leave Share/Receive mode).

### Send from a desktop browser (Web Bluetooth)

1. Put the badge into **Receive**.
2. Open [`web/index.html`](web/index.html) in **Chrome, Edge or Opera** on the
   desktop. Web Bluetooth needs a secure context, so serve it over **HTTPS** or
   from **`localhost`** — opening the file directly (`file://`) won't work.
   A quick local option:

   ```bash
   python3 -m http.server 8000
   ```

   then browse to `http://localhost:8000/web/`.
3. Fill in the network, click **Connect & send**, and pick your badge (it
   advertises as **WiFiMgr**) in the browser's device chooser.
4. The badge prompts to save the network, just like an ESP-NOW share.

Firefox and Safari don't support Web Bluetooth.

## ⚠️ Security note

Profiles are shared as **plaintext** — over ESP-NOW broadcast *and* over the
Bluetooth (GATT) connection, which is unencrypted (no pairing/bonding). Anyone
in radio range can read the SSID and password while you are sharing or sending.
This is intentional for the badge's social, share-with-friends use case — but
don't use it to move credentials you actually care about protecting.

A future version could add a short PIN to lightly obfuscate the payload.

## Files

| File | Purpose |
|------|---------|
| `app.py` | Entry point + UI state machine (`WiFiManager`) |
| `wifim_store.py` | Profile persistence (JSON at `/wifi_manager.json`) |
| `wifim_wifi.py` | Activate a profile / import current settings |
| `wifim_share.py` | Shared tagged-JSON wire codec (ESP-NOW + BLE + web) |
| `wifim_espnow.py` | ESP-NOW broadcast send + receive |
| `wifim_ble.py` | BLE GATT server that receives a profile from a browser |
| `web/index.html` | Standalone desktop Web Bluetooth sender page |
| `tildagon.toml` | App manifest |

Helper modules are prefixed `wifim_` so they never shadow the firmware's own
`wifi` module.


## License

MIT
