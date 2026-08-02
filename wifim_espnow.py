"""Share WiFi profiles between badges over ESP-NOW broadcast.

Built on the firmware's `espnow_service` (a wrapper around AIOESPNow) and the
eventbus. Payloads are the shared tagged-JSON blobs produced by `wifim_share`,
well under the 250-byte ESP-NOW limit.

SECURITY: profiles are broadcast in plaintext. Any badge in receive mode within
radio range can read the SSID and password. This is intentional for the badge
social use case; do not use it to move secrets you care about.
"""

from system.espnow import espnow_service, EspNowReceiveEvent, BROADCAST_MAC
from system.eventbus import eventbus

# Helper modules work whether the app is loaded as a package or flat.
try:
    from . import wifim_share as share
except ImportError:  # loaded flat (app dir on sys.path)
    import wifim_share as share


def broadcast(profile):
    """Send one broadcast advertisement of the given profile."""
    espnow_service.send(share.encode(profile), mac=BROADCAST_MAC)


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
        profile = share.decode(event.msg)
        if profile and profile.get("ssid"):
            self.on_profile(profile)

    def start(self):
        if self._sub is None:
            self._sub = espnow_service.subscribe(self._handle, self.app)

    def stop(self):
        if self._sub is not None:
            eventbus.remove(EspNowReceiveEvent, self._sub, self.app)
            self._sub = None
