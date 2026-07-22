"""Share WiFi profiles between badges over ESP-NOW broadcast.

Built on the firmware's `espnow_service` (a wrapper around AIOESPNow) and the
eventbus. Payloads are small tagged JSON blobs, well under the 250-byte ESP-NOW
limit (SSID <=32, password <=63).

SECURITY: profiles are broadcast in plaintext. Any badge in receive mode within
radio range can read the SSID and password. This is intentional for the badge
social use case; do not use it to move secrets you care about.
"""

import json

from system.espnow import espnow_service, EspNowReceiveEvent, BROADCAST_MAC
from system.eventbus import eventbus

_TAG = "wfm"      # identifies our packets
_VERSION = 1


def _encode(profile):
    payload = {
        "t": _TAG,
        "v": _VERSION,
        "n": profile.get("name", ""),
        "s": profile.get("ssid", ""),
        "p": profile.get("password", ""),
    }
    username = profile.get("username")
    if username:
        payload["u"] = username
    return json.dumps(payload).encode()


def _decode(msg):
    """Return a profile dict for a valid packet, else None."""
    try:
        data = json.loads(bytes(msg))
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict) or data.get("t") != _TAG:
        return None
    return {
        "name": data.get("n", "") or data.get("s", ""),
        "ssid": data.get("s", ""),
        "password": data.get("p", ""),
        "username": data.get("u", "") or "",
    }


def broadcast(profile):
    """Send one broadcast advertisement of the given profile."""
    espnow_service.send(_encode(profile), mac=BROADCAST_MAC)


class Receiver:
    """Listens for shared profiles and calls `on_profile(profile)` for each.

    The callback runs on the eventbus, so it should be cheap (e.g. stash the
    profile for the UI loop to pick up rather than opening a dialog directly).
    """

    def __init__(self, app, on_profile):
        self.app = app
        self.on_profile = on_profile
        self._sub = None

    def _handle(self, event):
        profile = _decode(event.msg)
        if profile and profile.get("ssid"):
            self.on_profile(profile)

    def start(self):
        if self._sub is None:
            self._sub = espnow_service.subscribe(self._handle, self.app)

    def stop(self):
        if self._sub is not None:
            eventbus.remove(EspNowReceiveEvent, self._sub, self.app)
            self._sub = None
