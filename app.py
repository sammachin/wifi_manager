"""WiFi Manager — store, manage, activate and share Wi-Fi profiles.

A Tildagon (EMF 2024 badge) app. Keeps a library of named Wi-Fi profiles
(WPA2-PSK and WPA2-Enterprise), activates any of them as the badge's own
network, and shares a profile badge-to-badge over ESP-NOW broadcast.

Input model note: both `Menu` and the dialogs subscribe to ButtonDownEvent on
the eventbus, so only one may be alive at a time. Every transition that opens a
dialog first tears the menu down (`_clear_menu`), and dialogs clean themselves
up before firing their callbacks. Menus are drawn directly; dialogs and
notifications are drawn via the overlay list.
"""

import app
from events.input import Buttons, BUTTON_TYPES
from app_components import Menu, TextDialog, YesNoDialog, Notification
from app_components.tokens import clear_background

# Helper modules work whether the app is loaded as a package or flat.
try:
    from . import wifim_store as store
    from . import wifim_wifi as wifi_helper
    from . import wifim_espnow as sharing
except ImportError:  # loaded flat (app dir on sys.path)
    import wifim_store as store
    import wifim_wifi as wifi_helper
    import wifim_espnow as sharing

# Action rows shown after the list of profiles on the main menu.
_ADD = "Add"
_IMPORT = "Import"
_RECEIVE = "Receive"
_MAIN_ACTIONS = [_ADD, _IMPORT, _RECEIVE]

_PROFILE_ACTIONS = ["Activate", "Share", "Edit", "Rename", "Delete", "Back"]

_NOTIFY_MS = 3000
_SHARE_INTERVAL_MS = 1000


class WiFiManager(app.App):
    def __init__(self):
        super().__init__()
        self.button_states = Buttons(self)
        self.profiles = store.load()

        self.state = "MAIN"
        self.sel_idx = 0          # selected profile index
        self._menu = None
        self._dialog = None
        self._notification = None
        self._notif_timer = 0

        self._draft = {}          # profile being built across add/edit dialogs
        self._edit_idx = None     # None => adding, otherwise editing this index

        self._share_accum = 0
        self._receiver = None
        self._received = None     # profile stashed by the ESP-NOW handler
        self._pending_recv = None # profile awaiting the save/discard dialog

        self._show_main()

    # ---- menu / overlay plumbing ------------------------------------------

    def _clear_menu(self):
        if self._menu is not None:
            self._menu._cleanup()
            self._menu = None

    def _set_menu(self, items, select_handler, back_handler, position=0):
        self._clear_menu()
        self._menu = Menu(
            self,
            items,
            select_handler=select_handler,
            back_handler=back_handler,
            position=position,
        )

    def _open_dialog(self, dialog):
        # A dialog owns button input; the menu must not compete for it.
        self._clear_menu()
        self._dialog = dialog
        self.overlays = [dialog]

    def _close_dialog(self):
        self._dialog = None
        self.overlays = []

    def _notify(self, message):
        self._notification = Notification(message)
        self._notif_timer = _NOTIFY_MS
        self.overlays = [self._notification]

    # ---- main menu --------------------------------------------------------

    def _show_main(self):
        self.state = "MAIN"
        self._close_dialog()
        names = [p["name"] or p["ssid"] or "(unnamed)" for p in self.profiles]
        self._set_menu(names + _MAIN_ACTIONS, self._main_select, self.minimise)

    def _main_select(self, item, position):
        n = len(self.profiles)
        if position < n:
            self.sel_idx = position
            self._show_profile()
            return
        action = position - n
        if action == 0:
            self._start_add()
        elif action == 1:
            self._do_import()
        elif action == 2:
            self._start_receive()

    # ---- per-profile menu -------------------------------------------------

    def _profile_label(self):
        p = self.profiles[self.sel_idx]
        return p["name"] or p["ssid"] or "(unnamed)"

    def _show_profile(self):
        self.state = "PROFILE"
        self._close_dialog()
        self._set_menu(_PROFILE_ACTIONS, self._profile_select, self._show_main)

    def _profile_select(self, item, position):
        [
            self._do_activate,
            self._start_share,
            self._start_edit,
            self._start_rename,
            self._confirm_delete,
            self._show_main,
        ][position]()

    # ---- activate / import ------------------------------------------------

    def _do_activate(self):
        p = self.profiles[self.sel_idx]
        try:
            wifi_helper.activate(p)
            self._notify("Activating %s" % (p["name"] or p["ssid"]))
        except Exception as e:  # noqa: BLE001 - surface any firmware error
            self._notify("Activate failed: %s" % e)

    def _do_import(self):
        try:
            p = wifi_helper.import_current()
        except Exception as e:  # noqa: BLE001
            self._notify("Import failed: %s" % e)
            return
        if p.get("ssid"):
            store.add(self.profiles, p["name"], p["ssid"], p["password"], p["username"])
            self._show_main()
            self._notify("Imported %s" % p["ssid"])
        else:
            self._notify("No current Wi-Fi set")

    # ---- add / edit (chained text dialogs) --------------------------------

    def _start_add(self):
        self.state = "ADD"
        self._edit_idx = None
        self._draft = {}
        self._ask_ssid()

    def _start_edit(self):
        self.state = "EDIT"
        self._edit_idx = self.sel_idx
        p = self.profiles[self.sel_idx]
        self._draft = {"name": p["name"]}
        self._ask_ssid()

    def _ask_ssid(self):
        self._open_dialog(TextDialog("SSID:", self,
                                     on_complete=self._got_ssid,
                                     on_cancel=self._cancel_dialog))

    def _got_ssid(self):
        self._draft["ssid"] = self._dialog.text.strip()
        self._open_dialog(TextDialog("Password:", self, masked=True,
                                     on_complete=self._got_password,
                                     on_cancel=self._cancel_dialog))

    def _got_password(self):
        self._draft["password"] = self._dialog.text
        self._open_dialog(TextDialog("Enterprise identity (blank = none):", self,
                                     on_complete=self._got_username,
                                     on_cancel=self._cancel_dialog))

    def _got_username(self):
        self._draft["username"] = self._dialog.text.strip()
        self._save_draft()

    def _save_draft(self):
        d = self._draft
        if not d.get("ssid"):
            self._show_main()
            self._notify("SSID required - not saved")
            return
        if self._edit_idx is None:
            store.add(self.profiles, d.get("name", ""), d["ssid"],
                      d.get("password", ""), d.get("username", ""))
            self._show_main()
            self._notify("Saved %s" % d["ssid"])
        else:
            store.update(self.profiles, self._edit_idx,
                         ssid=d["ssid"], password=d.get("password", ""),
                         username=d.get("username", ""))
            self._show_profile()
            self._notify("Updated %s" % d["ssid"])

    # ---- rename -----------------------------------------------------------

    def _start_rename(self):
        self.state = "RENAME"
        self._open_dialog(TextDialog("New name:", self,
                                     on_complete=self._got_rename,
                                     on_cancel=self._cancel_dialog))

    def _got_rename(self):
        name = self._dialog.text.strip()
        if name:
            store.rename(self.profiles, self.sel_idx, name)
        self._show_profile()
        if name:
            self._notify("Renamed to %s" % name)

    # ---- delete -----------------------------------------------------------

    def _confirm_delete(self):
        self.state = "DELETE"
        self._open_dialog(YesNoDialog("Delete %s?" % self._profile_label(), self,
                                      on_yes=self._do_delete,
                                      on_no=self._show_profile))

    def _do_delete(self):
        name = self._profile_label()
        store.delete(self.profiles, self.sel_idx)
        self.sel_idx = 0
        self._show_main()
        self._notify("Deleted %s" % name)

    def _cancel_dialog(self):
        # Route back to wherever the flow started.
        if self.state in ("EDIT", "RENAME"):
            self._show_profile()
        else:
            self._show_main()

    # ---- share (broadcast) ------------------------------------------------

    def _start_share(self):
        self.state = "SHARE"
        self._clear_menu()
        self._close_dialog()
        self.button_states.clear()
        self._share_accum = _SHARE_INTERVAL_MS  # broadcast on the first tick

    def _stop_share(self):
        self._show_profile()

    # ---- receive ----------------------------------------------------------

    def _start_receive(self):
        self.state = "RECEIVE"
        self._clear_menu()
        self._close_dialog()
        self.button_states.clear()
        self._received = None
        self._pending_recv = None
        try:
            if self._receiver is None:
                self._receiver = sharing.Receiver(self, self._on_received)
            self._receiver.start()
        except Exception as e:  # noqa: BLE001
            self._notify("ESP-NOW error: %s" % e)
            self._show_main()

    def _on_received(self, profile):
        # Runs on the eventbus; keep it cheap. The update loop shows the dialog.
        self._received = profile

    def _prompt_received(self, profile):
        self._pending_recv = profile
        self._open_dialog(YesNoDialog("Save '%s'?" % profile["ssid"], self,
                                      on_yes=self._save_received,
                                      on_no=self._dismiss_received))

    def _save_received(self):
        # Receiving is one-shot: once accepted, stop listening so the sharer's
        # repeated broadcasts can't re-prompt or create duplicate copies.
        p = self._pending_recv
        self._pending_recv = None
        updated = False
        if p:
            _, updated = store.upsert(self.profiles, p)
        self._stop_receive()  # stops the receiver and returns to the profile menu
        if p:
            self._notify("%s %s" % ("Updated" if updated else "Saved", p["ssid"]))

    def _dismiss_received(self):
        # Declining also exits receive mode, so the sharer's next broadcast
        # doesn't immediately re-open the dialog and trap us here.
        self._pending_recv = None
        self._stop_receive()

    def _stop_receive(self):
        if self._receiver is not None:
            self._receiver.stop()
        self._received = None
        self._show_profile()

    # ---- main loop --------------------------------------------------------

    def update(self, delta):
        if self._notification is not None:
            self._notification.update(delta)
            self._notif_timer -= delta
            if self._notif_timer <= 0:
                self._notification = None
                if self._dialog is None:
                    self.overlays = []

        if self._menu is not None:
            self._menu.update(delta)

        if self.state == "SHARE":
            self._share_accum += delta
            if self._share_accum >= _SHARE_INTERVAL_MS:
                self._share_accum = 0
                try:
                    sharing.broadcast(self.profiles[self.sel_idx])
                except Exception:  # noqa: BLE001 - keep the UI alive
                    pass
            if self.button_states.get(BUTTON_TYPES["CANCEL"]):
                self.button_states.clear()
                self._stop_share()

        elif self.state == "RECEIVE":
            if self._dialog is None:
                if self._received is not None:
                    profile = self._received
                    self._received = None
                    self._prompt_received(profile)
                elif self.button_states.get(BUTTON_TYPES["CANCEL"]):
                    self.button_states.clear()
                    self._stop_receive()

        return True  # always redraw (menus/dialogs animate)

    def draw(self, ctx):
        ctx.save()
        clear_background(ctx)
        ctx.text_align = ctx.CENTER
        ctx.text_baseline = ctx.MIDDLE

        if self.state == "SHARE":
            self._draw_lines(ctx, [
                ("Sharing", 0.7),
                (self._profile_label(), 1.0),
                ("", 0.5),
                ("Other badge:", 0.6),
                ("Receive shared", 0.6),
                ("", 0.5),
                ("CANCEL to stop", 0.5),
            ])
        elif self.state == "RECEIVE" and self._dialog is None:
            self._draw_lines(ctx, [
                ("Listening for", 0.7),
                ("shared networks...", 0.7),
                ("", 0.5),
                ("CANCEL to stop", 0.5),
            ])
        elif self._menu is not None:
            self._menu.draw(ctx)

        self.draw_overlays(ctx)
        ctx.restore()

    def _draw_lines(self, ctx, lines):
        line_h = 26
        total = len(lines)
        y0 = -(total - 1) * line_h / 2
        for i, (text, scale) in enumerate(lines):
            if not text:
                continue
            ctx.font_size = int(24 * scale)
            ctx.rgb(0.6, 1.0, 0.6).move_to(0, y0 + i * line_h).text(text)


__app_export__ = WiFiManager
