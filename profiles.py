import json
import math
import os

DEVICE_PROFILES = {
    "kindle_pw_7gen_6": {
        "name": "Kindle PW 7 Gen (6\")",
        "screen_w": 1072,
        "screen_h": 1448,
        "ppi": 300,
        "export_dpi": 300,
        "render_zoom": 2.0,
        "preview_max": (800, 700),
    },
    "kindle_pw_11gen_7": {
        "name": "Kindle PW 11+ Gen (7\")",
        "screen_w": 1264,
        "screen_h": 1680,
        "ppi": 300,
        "export_dpi": 300,
        "render_zoom": 2.5,
        "preview_max": (900, 800),
    },
}

DEFAULT_PROFILE = "kindle_pw_7gen_6"

USER_CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".sheet-music-extractor")
os.makedirs(USER_CONFIG_DIR, exist_ok=True)

CUSTOM_PROFILES_FILE = os.path.join(USER_CONFIG_DIR, "custom_profiles.json")
SETTINGS_FILE = os.path.join(USER_CONFIG_DIR, "settings.json")


def build_profile(name, screen_w, screen_h, diagonal_inches):
    """Derive a full profile dict from screen dimensions and diagonal size."""
    ppi = int(math.hypot(screen_w, screen_h) / diagonal_inches)
    render_zoom = max(2.0, screen_w / 600)
    preview_max = (min(900, screen_w), min(800, screen_h))
    return {
        "name": name,
        "screen_w": screen_w,
        "screen_h": screen_h,
        "ppi": ppi,
        "export_dpi": ppi,
        "render_zoom": round(render_zoom, 2),
        "preview_max": preview_max,
    }


def load_custom_profiles():
    if os.path.exists(CUSTOM_PROFILES_FILE):
        with open(CUSTOM_PROFILES_FILE, "r") as f:
            data = json.load(f)
        for key, vals in data.items():
            vals["preview_max"] = tuple(vals["preview_max"])
            DEVICE_PROFILES[key] = vals


def save_custom_profiles():
    custom = {k: v for k, v in DEVICE_PROFILES.items() if k.startswith("custom_")}
    serializable = {}
    for k, v in custom.items():
        entry = dict(v)
        entry["preview_max"] = list(entry["preview_max"])
        serializable[k] = entry
    with open(CUSTOM_PROFILES_FILE, "w") as f:
        json.dump(serializable, f, indent=2)


def get_last_profile():
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, "r") as f:
            data = json.load(f)
        key = data.get("last_profile")
        if key and key in DEVICE_PROFILES:
            return key
    return DEFAULT_PROFILE


def save_last_profile(key):
    data = {}
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, "r") as f:
            data = json.load(f)
    data["last_profile"] = key
    with open(SETTINGS_FILE, "w") as f:
        json.dump(data, f, indent=2)


load_custom_profiles()
