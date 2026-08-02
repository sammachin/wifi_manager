"""Receive WiFi profiles over BLE from a desktop WebBluetooth sender.

The badge acts as a BLE **peripheral / GATT server**: it advertises a custom
service with one writable characteristic. A desktop browser (see
`web/index.html`) is the BLE **central** — WebBluetooth can only be a central —
so it scans, connects, and writes the profile to us. The badge never BLE-sends;
badge-to-badge sharing stays ESP-NOW only (`wifim_espnow`).

Payloads are the shared tagged-JSON blobs from `wifim_share`, newline-framed on
the wire so the transfer is MTU-agnostic: the sender may deliver the whole blob
in one write or in many small chunks, and we accumulate bytes until we see the
`\\n` terminator before decoding.

Public API mirrors `wifim_espnow.Receiver` on purpose (`start()` / `stop()` /
`on_profile` callback) so `app.py` can drive both transports the same way. The
`on_profile` callback runs from the BLE IRQ (a scheduler callback), so it must
be cheap — stash the profile for the UI loop, don't open a dialog inline.

SECURITY: the GATT write is unencrypted (no pairing/bonding), so the profile
crosses in plaintext — the same trade-off as the ESP-NOW path. Don't use it to
move secrets you care about.
"""

# BLE is compiled into the Tildagon firmware, but guard the import so this
# module still loads off-badge (CPython) and so the app can degrade to
# ESP-NOW-only if BLE is ever unavailable.
try:
    import bluetooth
    AVAILABLE = True
except ImportError:  # pragma: no cover - only off-badge
    bluetooth = None
    AVAILABLE = False

try:
    from . import wifim_share as share
except ImportError:  # loaded flat (app dir on sys.path)
    import wifim_share as share

# Fixed custom 128-bit UUIDs. These MUST match web/index.html.
_SERVICE_UUID_STR = "f0a2b100-8c1d-4b6e-9a2f-1e3c5d7f9b01"
_CHAR_UUID_STR = "f0a2b101-8c1d-4b6e-9a2f-1e3c5d7f9b01"

_LOCAL_NAME = "WiFiMgr"
_ADV_INTERVAL_US = 250_000  # 250 ms

# IRQ event codes and characteristic flags are not exported by the `bluetooth`
# module; define the ones we use (standard MicroPython values).
_IRQ_CENTRAL_CONNECT = 1
_IRQ_CENTRAL_DISCONNECT = 2
_IRQ_GATTS_WRITE = 3

_FLAG_WRITE = 0x0008
_FLAG_WRITE_NO_RESPONSE = 0x0004

_TERMINATOR = b"\n"  # frame delimiter
_MAX_FRAME = 512     # guard against a peer streaming without a terminator


def _adv_payload(name=None, service_uuid=None):
    """Build a BLE advertising / scan-response payload (list of AD structures)."""
    payload = bytearray()

    def _append(adv_type, value):
        payload.append(len(value) + 1)
        payload.append(adv_type)
        payload.extend(value)

    _append(0x01, b"\x06")  # Flags: LE General Discoverable, BR/EDR not supported
    if service_uuid is not None:
        b = bytes(service_uuid)
        if len(b) == 16:
            _append(0x07, b)  # Complete list of 128-bit service UUIDs
        elif len(b) == 2:
            _append(0x03, b)  # Complete list of 16-bit service UUIDs
    if name:
        _append(0x09, name.encode())  # Complete local name
    return payload


class Receiver:
    """BLE GATT server that calls `on_profile(profile)` for each profile written.

    `on_profile` runs from the BLE IRQ, so keep it cheap.
    """

    def __init__(self, app, on_profile):
        self.app = app
        self.on_profile = on_profile
        self._ble = None
        self._handle = None
        self._buf = bytearray()
        self.error = None  # last IRQ exception message, for the UI to surface

    # ---- lifecycle --------------------------------------------------------

    def start(self):
        if not AVAILABLE:
            raise RuntimeError("BLE not available")
        if self._ble is not None:
            return
        ble = bluetooth.BLE()
        ble.active(True)
        ble.irq(self._irq)

        service = (
            bluetooth.UUID(_SERVICE_UUID_STR),
            ((bluetooth.UUID(_CHAR_UUID_STR),
              _FLAG_WRITE | _FLAG_WRITE_NO_RESPONSE),),
        )
        ((self._handle,),) = ble.gatts_register_services((service,))
        # Accept a whole payload in one write if the central negotiated a large
        # MTU; small chunked writes still work via our own buffer below.
        try:
            ble.gatts_set_buffer(self._handle, _MAX_FRAME, False)
        except (AttributeError, OSError):  # older firmware / not fatal
            pass

        self._ble = ble
        self._buf = bytearray()
        self._advertise()

    def stop(self):
        if self._ble is None:
            return
        try:
            self._ble.gap_advertise(None)  # stop advertising
        except OSError:
            pass
        try:
            self._ble.irq(None)
        except (AttributeError, OSError):
            pass
        try:
            self._ble.active(False)  # free the radio for ESP-NOW / WiFi
        except OSError:
            pass
        self._ble = None
        self._handle = None
        self._buf = bytearray()

    def _advertise(self):
        uuid = bluetooth.UUID(_SERVICE_UUID_STR)
        adv = _adv_payload(service_uuid=uuid)
        resp = _adv_payload(name=_LOCAL_NAME)
        self._ble.gap_advertise(_ADV_INTERVAL_US, adv_data=adv, resp_data=resp)

    # ---- IRQ --------------------------------------------------------------

    def _irq(self, event, data):
        # This runs in the BLE stack's callback context; an exception here
        # would surface only as an opaque "Unhandled exception in IRQ callback
        # handler". Catch everything and stash it so the UI loop can show it.
        try:
            if event == _IRQ_GATTS_WRITE:
                _, value_handle = data
                if value_handle == self._handle:
                    self._on_write(self._ble.gatts_read(self._handle))
            elif event == _IRQ_CENTRAL_DISCONNECT:
                # Advertising stops once a central connects; restart it and drop
                # any partial frame so the next sender starts clean.
                self._buf = bytearray()
                if self._ble is not None:
                    self._advertise()
            elif event == _IRQ_CENTRAL_CONNECT:
                self._buf = bytearray()
        except Exception as e:  # noqa: BLE001 - keep the BLE stack alive
            self.error = repr(e)

    def _on_write(self, chunk):
        if not chunk:
            return
        self._buf.extend(chunk)
        # Process every complete newline-terminated frame in the buffer. Rebuild
        # the buffer by slicing (MicroPython bytearray has no slice `del`).
        while True:
            nl = self._buf.find(_TERMINATOR)
            if nl < 0:
                break
            frame = bytes(self._buf[:nl])
            self._buf = bytearray(self._buf[nl + 1:])
            self._deliver(frame)
        # A frame that runs away without a terminator shouldn't grow forever.
        if len(self._buf) > _MAX_FRAME:
            self._buf = bytearray()

    def _deliver(self, frame):
        if not frame:
            return
        profile = share.decode(frame)
        if profile and profile.get("ssid"):
            self.on_profile(profile)
