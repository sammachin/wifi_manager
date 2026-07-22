"""Activate a profile as the badge's WiFi, and import the current settings.

Wraps the firmware's `wifi` and `settings` modules. On the badge, WiFi
credentials live in three settings keys:

    wifi_ssid            - network name
    wifi_password        - PSK, or the EAP password for enterprise networks
    wifi_wpa2ent_username- EAP identity/username (None => plain WPA2-PSK)

`wifi.save_defaults(ssid, password, username)` writes and saves all three, and
`wifi.connect()` (no args) reconnects using the saved defaults. `connect()` is
non-blocking, so this is safe to call from the UI update loop.
"""

import settings
import wifi


def activate(profile):
    """Write the profile to the badge settings and reconnect immediately."""
    ssid = profile.get("ssid", "")
    password = profile.get("password", "")
    username = profile.get("username") or None  # None => not enterprise

    # Persists wifi_ssid / wifi_password / wifi_wpa2ent_username and saves.
    wifi.save_defaults(ssid, password, username)

    # Drop any existing association, then reconnect with the new defaults.
    try:
        wifi.disconnect()
    except Exception:
        pass
    wifi.connect()  # reads the freshly-saved defaults, incl. EAP identity


def import_current():
    """Return the badge's current WiFi settings as a profile dict."""
    ssid = settings.get("wifi_ssid", "") or ""
    return {
        "name": ssid or "Current",
        "ssid": ssid,
        "password": settings.get("wifi_password", "") or "",
        "username": settings.get("wifi_wpa2ent_username", "") or "",
    }
