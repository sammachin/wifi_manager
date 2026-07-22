"""Persistence for WiFi Manager profiles.

A profile is a dict:
    {"name": str, "ssid": str, "password": str, "username": str}

`username` is the WPA2-Enterprise (EAP) identity. An empty string means the
profile is a plain WPA2-PSK network. Profiles are stored as a single JSON blob
on the badge flash root.

This module deliberately imports only the standard library (json/os) so it can
be exercised off-badge with CPython.
"""

import json

try:
    import os
except ImportError:  # pragma: no cover - MicroPython always has os
    os = None

# Flash root is writable on the badge (that's where /settings.json lives).
PATH = "/wifi_manager.json"

# Field length limits (802.11 / firmware constraints).
SSID_MAX = 32
PASSWORD_MAX = 63
NAME_MAX = 32
USERNAME_MAX = 64


def _blank(profile=None):
    profile = profile or {}
    return {
        "name": str(profile.get("name", ""))[:NAME_MAX],
        "ssid": str(profile.get("ssid", ""))[:SSID_MAX],
        "password": str(profile.get("password", ""))[:PASSWORD_MAX],
        "username": str(profile.get("username", ""))[:USERNAME_MAX],
    }


def load():
    """Return the list of stored profiles (empty list if none / unreadable)."""
    try:
        with open(PATH) as f:
            data = json.load(f)
    except (OSError, ValueError):
        return []
    profiles = data.get("profiles", []) if isinstance(data, dict) else []
    return [_blank(p) for p in profiles if isinstance(p, dict)]


def save(profiles):
    """Persist the given list of profiles."""
    with open(PATH, "w") as f:
        json.dump({"profiles": [_blank(p) for p in profiles]}, f)


def add(profiles, name, ssid, password, username=""):
    """Append a new profile and persist. Returns the updated list."""
    profiles.append(_blank({
        "name": name or ssid,
        "ssid": ssid,
        "password": password,
        "username": username,
    }))
    save(profiles)
    return profiles


def update(profiles, idx, ssid=None, password=None, username=None, name=None):
    """Update fields of an existing profile in place and persist."""
    if 0 <= idx < len(profiles):
        p = profiles[idx]
        if name is not None:
            p["name"] = str(name)[:NAME_MAX]
        if ssid is not None:
            p["ssid"] = str(ssid)[:SSID_MAX]
        if password is not None:
            p["password"] = str(password)[:PASSWORD_MAX]
        if username is not None:
            p["username"] = str(username)[:USERNAME_MAX]
        save(profiles)
    return profiles


def rename(profiles, idx, name):
    return update(profiles, idx, name=name)


def delete(profiles, idx):
    """Remove a profile by index and persist. Returns the updated list."""
    if 0 <= idx < len(profiles):
        del profiles[idx]
        save(profiles)
    return profiles


def find_by_ssid(profiles, ssid):
    """Return the index of the first profile with this SSID, or -1."""
    for i, p in enumerate(profiles):
        if p.get("ssid") == ssid:
            return i
    return -1


def upsert(profiles, profile):
    """Add `profile`, or overwrite the existing one with the same SSID.

    Prevents duplicate copies of the same network (e.g. when a badge is shared
    repeatedly). Returns (profiles, updated) where `updated` is True if an
    existing entry was replaced. A blank incoming name keeps the stored name.
    """
    incoming = _blank(profile)
    idx = find_by_ssid(profiles, incoming["ssid"])
    if idx >= 0:
        if not incoming["name"]:
            incoming["name"] = profiles[idx].get("name", "")
        profiles[idx] = incoming
        save(profiles)
        return profiles, True
    profiles.append(incoming)
    save(profiles)
    return profiles, False


def is_enterprise(profile):
    return bool(profile.get("username"))
