"""Shared wire codec for sharing WiFi profiles off-badge.

A profile travels as a small tagged-JSON blob, identical whether it is carried
over ESP-NOW (`wifim_espnow`) or BLE (`wifim_ble`), and the desktop WebBluetooth
sender (`web/index.html`) produces the exact same shape. Keeping one codec here
means the three endpoints can never drift apart.

Payload keys are terse to stay well under the 250-byte ESP-NOW limit
(SSID <=32, password <=63):

    {"t": "wfm", "v": 1, "n": name, "s": ssid, "p": password, "u": username}

`u` is omitted for plain WPA2-PSK networks (no enterprise identity).

This module imports only the standard library (json) so it can be exercised
off-badge with CPython, like `wifim_store`.
"""

import json

TAG = "wfm"       # identifies our packets
VERSION = 1


def encode(profile):
    """Serialise a profile dict to the wire bytes."""
    payload = {
        "t": TAG,
        "v": VERSION,
        "n": profile.get("name", ""),
        "s": profile.get("ssid", ""),
        "p": profile.get("password", ""),
    }
    username = profile.get("username")
    if username:
        payload["u"] = username
    return json.dumps(payload).encode()


def decode(data):
    """Return a profile dict for a valid packet, else None.

    `data` may be anything bytes-like (bytes, bytearray, memoryview).
    """
    try:
        parsed = json.loads(bytes(data))
    except (ValueError, TypeError):
        return None
    if not isinstance(parsed, dict) or parsed.get("t") != TAG:
        return None
    return {
        "name": parsed.get("n", "") or parsed.get("s", ""),
        "ssid": parsed.get("s", ""),
        "password": parsed.get("p", ""),
        "username": parsed.get("u", "") or "",
    }
