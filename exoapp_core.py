#!/usr/bin/env python3
"""ExoApp core: RGB, DPI and profile control for the EXO Rifter
(Sinowealth 258a:0029) mouse, on Linux (hidraw) and Windows (hidapi).

OpenRGB detects this mouse as "Everest GT-100" and drives it with the
Glorious Model O protocol, which sends colours as R,B,G.  This mouse wants
R,G,B, so OpenRGB's colours come out wrong (yellow -> pink).  The config
layout is otherwise the same: read the 520-byte feature report 0x04 after
sending command 0x11 on report 0x05, patch it, and write it back with
byte 0x03 = 0x7B.  Settings are stored in the mouse and survive replugging.

Profiles are JSON files in the ExoApp config dir holding the same state
dict that Mouse.get_state() returns and Mouse.apply() takes.

On Windows the vendor interface shows up as three separate HID collections
(usage page 0xFF00) holding the command report, the config report and the
DPI input report; like OpenRGB we probe each one to find which is which.
"""

import argparse
import glob
import json
import os
import sys
import time

if sys.platform.startswith("linux"):
    import fcntl

VID, PID = 0x258A, 0x0029
CONFIG_SIZE = 520
CMD_SIZE = 6

MODES = {
    "off": 0x00,
    "rainbow": 0x01,
    "static": 0x02,
    "spectrum-breathing": 0x03,
    "tail": 0x04,
    "spectrum-cycle": 0x05,
    "multicolor": 0x06,
    "rave": 0x07,
    "epilepsy": 0x08,
    "wave": 0x09,
}
MODE_NAMES = {v: k for k, v in MODES.items()}
# The mouse firmware has no working single-colour breathing (0x0A stays
# dark), so "breathing" is spectrum-breathing with one colour in all slots.
ALIASES = {"breathing": "spectrum-breathing"}

# Byte offsets of each mode's "brightness<<4 | speed" byte.
LEVEL_OFFSET = {
    "rainbow": 0x36,
    "static": 0x38,
    "spectrum-breathing": 0x3C,
    "tail": 0x53,
    "spectrum-cycle": 0x54,
    "multicolor": 0x55,
    "rave": 0x74,
    "epilepsy": 0x7B,
    "wave": 0x7C,
}
# Where each mode keeps its colours, and how many it takes.
COLOR_OFFSET = {
    "static": (0x39, 1),
    "spectrum-breathing": (0x3E, 7),
    "multicolor": (0x56, 7),
    "rave": (0x75, 2),
}
MODE_OFFSET = 0x35
DIRECTION_OFFSET = 0x37  # rainbow only: 0 = down, 1 = up
SPECTRUM_COUNT_OFFSET = 0x3D

# DPI layout (same as gloriousctl's Model O struct).
XY_OFFSET = 0x0A          # bit 0x80: separate X/Y values per stage
DPI_COUNT_OFFSET = 0x0B   # low nibble: stage count, high nibble: active stage (1-based)
DPI_DISABLED_OFFSET = 0x0C  # bit set = stage disabled
DPI_OFFSET = 0x0D         # one byte per stage: dpi / 100 - 1
DPI_COLOR_OFFSET = 0x1D   # RGB per stage, flashed when switching
DPI_STAGES = 6
DPI_MIN, DPI_MAX, DPI_STEP = 100, 5000, 100  # PixArt PMW3325

BRIGHTNESS = {"low": 1, "normal": 2, "high": 4}
SPEED = {"slow": 1, "normal": 2, "fast": 3}

NAMED_COLORS = {
    "red": "ff0000", "green": "00ff00", "blue": "0000ff", "white": "ffffff",
    "yellow": "ffff00", "cyan": "00ffff", "magenta": "ff00ff", "pink": "ff3080",
    "orange": "ff6000", "purple": "8000ff", "black": "000000",
}

if sys.platform == "win32":
    CONFIG_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "ExoApp")
else:
    CONFIG_DIR = os.path.join(
        os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")), "ExoApp")
PROFILE_DIR = os.path.join(CONFIG_DIR, "profiles")


def _ioc(n, size):
    # _IOC(_IOC_READ|_IOC_WRITE, 'H', n, size)
    return (3 << 30) | (size << 16) | (ord("H") << 8) | n


def HIDIOCSFEATURE(size):
    return _ioc(0x06, size)


def HIDIOCGFEATURE(size):
    return _ioc(0x07, size)


def parse_color(text):
    text = NAMED_COLORS.get(text.lower(), text).lstrip("#").lower()
    if len(text) != 6 or any(c not in "0123456789abcdef" for c in text):
        raise ValueError(f"bad colour: {text!r} (use e.g. ff8800 or 'orange')")
    return text


def rgb(hexc):
    return bytes.fromhex(hexc)


class HidrawTransport:
    """Linux: all collections share one hidraw node; talk to it with ioctls."""

    def __init__(self, path=None):
        self.path = path or self.find()
        if not self.path:
            raise RuntimeError("EXO Rifter / Sinowealth 258a:0029 mouse not found")
        self.fd = os.open(self.path, os.O_RDWR)
        self.event_fd = os.open(self.path, os.O_RDONLY | os.O_NONBLOCK)

    @staticmethod
    def find():
        """Return the hidraw node of the mouse's vendor (config) interface."""
        want = f"0003:{VID:08X}:{PID:08X}"
        for node in sorted(glob.glob("/sys/class/hidraw/hidraw*")):
            try:
                with open(f"{node}/device/uevent") as f:
                    if f"HID_ID={want}" not in f.read():
                        continue
                with open(f"{node}/device/report_descriptor", "rb") as f:
                    desc = f.read()
            except OSError:
                continue
            # The config interface declares feature report ID 0x04 (85 04).
            if b"\x85\x04" in desc:
                return "/dev/" + os.path.basename(node)
        return None

    def send_feature(self, data):
        fcntl.ioctl(self.fd, HIDIOCSFEATURE(len(data)), bytearray(data))

    def get_feature(self, report_id, size):
        buf = bytearray(size)
        buf[0] = report_id
        fcntl.ioctl(self.fd, HIDIOCGFEATURE(size), buf)
        return buf

    def read_events(self):
        out = []
        while True:
            try:
                data = os.read(self.event_fd, 64)
            except BlockingIOError:
                return out
            if not data:
                return out
            out.append(data)

    def close(self):
        os.close(self.fd)
        os.close(self.event_fd)


class HidapiTransport:
    """Windows/macOS: one hidapi handle per vendor collection, found by probing."""

    def __init__(self, path=None):
        import hid
        self.hid = hid
        self.cmd_dev = self.data_dev = None
        self.devs = []
        paths = [d["path"] for d in hid.enumerate(VID, PID)
                 if d.get("usage_page") == 0xFF00 or path == d["path"]]
        if not paths:
            raise RuntimeError("EXO Rifter / Sinowealth 258a:0029 mouse not found")
        for p in paths:
            dev = hid.device()
            try:
                dev.open_path(p)
            except OSError:
                continue
            dev.set_nonblocking(1)
            self.devs.append(dev)
        # Never probe more than one report at a time; responses can get mixed up.
        cmd = bytes([0x05, 0x11, 0, 0, 0, 0])
        for dev in self.devs:
            try:
                if dev.send_feature_report(cmd) >= 0:
                    self.cmd_dev = dev
                    break
            except (OSError, ValueError):
                pass
        for dev in self.devs:
            try:
                if len(dev.get_feature_report(0x04, CONFIG_SIZE)) > 0:
                    self.data_dev = dev
                    break
            except (OSError, ValueError):
                pass
        if not (self.cmd_dev and self.data_dev):
            self.close()
            raise RuntimeError("mouse found, but its config interface did not answer")
        self.path = paths[0].decode(errors="replace") if isinstance(paths[0], bytes) else paths[0]

    def send_feature(self, data):
        # Command reports (0x05) live on one collection, config (0x04) on another.
        dev = self.cmd_dev if data[0] == 0x05 else self.data_dev
        if dev.send_feature_report(bytes(data)) < 0:
            raise OSError("send_feature_report failed")

    def get_feature(self, report_id, size):
        dev = self.cmd_dev if report_id == 0x05 else self.data_dev
        data = dev.get_feature_report(report_id, size)
        if not data:
            raise OSError("get_feature_report failed")
        buf = bytearray(size)
        buf[:len(data)] = bytes(data)
        return buf

    def read_events(self):
        out = []
        for dev in self.devs:
            while True:
                data = dev.read(64)
                if not data:
                    break
                out.append(bytes(data))
        return out

    def close(self):
        for dev in self.devs:
            dev.close()
        self.devs = []


def open_transport(path=None):
    if sys.platform.startswith("linux"):
        return HidrawTransport(path)
    return HidapiTransport(path)


def decode(cfg):
    """Turn a raw config report into a state dict."""
    mode = MODE_NAMES.get(cfg[MODE_OFFSET], "unknown")
    light = {"mode": mode, "brightness": 4, "speed": 2, "direction": "down", "colors": []}
    if mode in LEVEL_OFFSET:
        lvl = cfg[LEVEL_OFFSET[mode]]
        light["brightness"] = (lvl >> 4) or 4
        light["speed"] = (lvl & 0x0F) or 2
    if mode in COLOR_OFFSET:
        off, n = COLOR_OFFSET[mode]
        light["colors"] = [cfg[off + 3 * i: off + 3 * i + 3].hex() for i in range(n)]
    if mode == "spectrum-breathing" and len(set(light["colors"])) == 1:
        light["mode"] = "breathing"
        light["colors"] = light["colors"][:1]
    light["direction"] = "up" if cfg[DIRECTION_OFFSET] else "down"

    xy = bool(cfg[XY_OFFSET] & 0x80)
    stages = []
    for i in range(DPI_STAGES):
        if cfg[DPI_DISABLED_OFFSET] & (1 << i):
            break
        val = cfg[DPI_OFFSET + (2 * i if xy else i)]
        color = cfg[DPI_COLOR_OFFSET + 3 * i: DPI_COLOR_OFFSET + 3 * i + 3].hex()
        stages.append({"dpi": (val + 1) * 100, "color": color})
    active = (cfg[DPI_COUNT_OFFSET] >> 4) - 1
    return {"lighting": light, "dpi": {"stages": stages, "active": min(max(active, 0), max(len(stages) - 1, 0))}}


def encode(cfg, state):
    """Patch a raw config report with a state dict (either part may be missing)."""
    cfg = bytearray(cfg)
    light = state.get("lighting")
    if light:
        mode = ALIASES.get(light["mode"], light["mode"])
        if mode not in MODES:
            raise ValueError(f"unknown mode {light['mode']!r}")
        cfg[MODE_OFFSET] = MODES[mode]
        if mode in LEVEL_OFFSET:
            # Static has no speed; its low nibble stays zero.
            spd = 0 if mode == "static" else light.get("speed", 2)
            cfg[LEVEL_OFFSET[mode]] = ((light.get("brightness", 4) & 0xF) << 4) | (spd & 0xF)
        colors = light.get("colors")
        if mode in COLOR_OFFSET and colors:
            off, n = COLOR_OFFSET[mode]
            for i in range(n):
                # Fewer colours than slots: repeat the list.
                cfg[off + 3 * i: off + 3 * i + 3] = rgb(colors[i % len(colors)])
            if mode == "spectrum-breathing":
                cfg[SPECTRUM_COUNT_OFFSET] = 0x07
        if mode == "rainbow":
            cfg[DIRECTION_OFFSET] = 1 if light.get("direction") == "up" else 0

    dpi = state.get("dpi")
    if dpi:
        stages = dpi["stages"]
        if not 1 <= len(stages) <= DPI_STAGES:
            raise ValueError(f"need 1-{DPI_STAGES} DPI stages")
        cfg[XY_OFFSET] &= ~0x80 & 0xFF
        cfg[DPI_OFFSET:DPI_OFFSET + 16] = bytes(16)
        disabled = 0xFF
        for i, st in enumerate(stages):
            d = int(st["dpi"])
            if not DPI_MIN <= d <= DPI_MAX:
                raise ValueError(f"DPI {d} outside {DPI_MIN}-{DPI_MAX}")
            cfg[DPI_OFFSET + i] = round(d / DPI_STEP) - 1
            cfg[DPI_COLOR_OFFSET + 3 * i: DPI_COLOR_OFFSET + 3 * i + 3] = rgb(st["color"])
            disabled &= ~(1 << i)
        active = min(max(int(dpi.get("active", 0)), 0), len(stages) - 1)
        cfg[DPI_DISABLED_OFFSET] = disabled
        cfg[DPI_COUNT_OFFSET] = ((active + 1) << 4) | len(stages)
    return cfg


class Mouse:
    def __init__(self, path=None):
        self.t = open_transport(path)
        self.path = self.t.path

    def close(self):
        self.t.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def read_config(self):
        self.t.send_feature(bytes([0x05, 0x11, 0, 0, 0, 0]))
        return self.t.get_feature(0x04, CONFIG_SIZE)

    def write_config(self, buf):
        buf = bytearray(buf)
        buf[0] = 0x04
        buf[0x03] = 0x7B
        self.t.send_feature(buf)
        # A read straight after a write returns zeros from 0x2C onward
        # (noted in OpenRGB); give the mouse time before the next read.
        time.sleep(0.1)

    def firmware(self):
        try:
            self.t.send_feature(bytes([0x05, 0x01, 0, 0, 0, 0]))
            buf = self.t.get_feature(0x05, CMD_SIZE)
        except OSError:
            return ""
        return bytes(buf[2:]).split(b"\0")[0].decode(errors="replace")

    def get_state(self):
        return decode(self.read_config())

    def apply(self, state):
        cfg = self.read_config()
        if cfg[0x2C:0x80] == bytes(0x80 - 0x2C):
            raise RuntimeError("config read back empty; refusing to write zeros to the mouse")
        self.write_config(encode(cfg, state))

    def dpi_events(self):
        """Non-blocking: DPI button events received since the last call."""
        return [ev for ev in map(parse_dpi_event, self.t.read_events()) if ev]


def parse_dpi_event(data):
    """Input report 0x07 is sent when the DPI button switches stage.

    Byte 2's low nibble is the new stage, 1-based; byte 3 its DPI value.
    """
    if len(data) >= 5 and data[0] == 0x07:
        return {"active": (data[2] & 0x0F) - 1, "dpi": (data[3] + 1) * 100}
    return None


def profile_path(name):
    if not name or "/" in name or name.startswith("."):
        raise ValueError(f"bad profile name {name!r}")
    return os.path.join(PROFILE_DIR, name + ".json")


def list_profiles():
    try:
        return sorted(f[:-5] for f in os.listdir(PROFILE_DIR) if f.endswith(".json"))
    except FileNotFoundError:
        return []


def load_profile(name):
    with open(profile_path(name)) as f:
        return json.load(f)


def save_profile(name, state):
    os.makedirs(PROFILE_DIR, exist_ok=True)
    with open(profile_path(name), "w") as f:
        json.dump(state, f, indent=2)


def delete_profile(name):
    os.remove(profile_path(name))


def format_state(st):
    light, dpi = st["lighting"], st["dpi"]
    line = light["mode"]
    if ALIASES.get(light["mode"], light["mode"]) in LEVEL_OFFSET:
        line += f"  brightness={light['brightness']}"
        if light["mode"] != "static":
            line += f" speed={light['speed']}"
    if light["mode"] == "rainbow":
        line += f"  direction={light['direction']}"
    if light["colors"]:
        line += "  colours=" + " ".join(light["colors"])
    stages = []
    for i, s in enumerate(dpi["stages"]):
        mark = "*" if i == dpi["active"] else ""
        stages.append(f"{mark}{s['dpi']}({s['color']})")
    return line + "\nDPI: " + " ".join(stages)


def main(argv=None):
    p = argparse.ArgumentParser(prog="exoapp", description="ExoApp: EXO Rifter mouse RGB/DPI control")
    p.add_argument("--device", help="hidraw node (default: autodetect)")
    sub = p.add_subparsers(dest="cmd")

    sub.add_parser("status", help="show lighting and DPI")
    sub.add_parser("modes", help="list effects")

    s = sub.add_parser("set", help="set an effect")
    s.add_argument("mode", choices=list(MODES) + list(ALIASES))
    s.add_argument("colors", nargs="*", help="hex (ff8800) or name (orange)")
    s.add_argument("-b", "--brightness", choices=list(BRIGHTNESS), default="high")
    s.add_argument("-s", "--speed", choices=list(SPEED), default="normal")
    s.add_argument("-d", "--direction", choices=["up", "down"], default="down")

    d = sub.add_parser("dpi", help="show or set DPI stages")
    d.add_argument("values", nargs="*", type=int, help=f"1-{DPI_STAGES} DPI values")
    d.add_argument("-a", "--active", type=int, help="active stage (1-based)")
    d.add_argument("-c", "--colors", nargs="+", help="stage colours")

    pr = sub.add_parser("profile", help="manage saved profiles")
    pr.add_argument("action", choices=["list", "save", "load", "delete", "show"])
    pr.add_argument("name", nargs="?")

    b = sub.add_parser("backup", help="save the raw mouse config to a file")
    b.add_argument("file")
    r = sub.add_parser("restore", help="write a saved raw config back")
    r.add_argument("file")

    args = p.parse_args(argv)
    if args.cmd == "modes":
        for name in MODES:
            extra = ""
            if name in COLOR_OFFSET:
                extra = f"  ({COLOR_OFFSET[name][1]} colour{'s' if COLOR_OFFSET[name][1] > 1 else ''})"
            print(name + extra)
        print("breathing  (1 colour; = spectrum-breathing with one colour)")
        return 0

    try:
        if args.cmd == "profile" and args.action in ("list", "show", "delete"):
            if args.action == "list":
                print("\n".join(list_profiles()) or "(no profiles)")
            elif args.action == "show":
                print(format_state(load_profile(args.name)))
            else:
                delete_profile(args.name)
                print(f"deleted {args.name}")
            return 0

        with Mouse(args.device) as m:
            if args.cmd == "set":
                light = {"mode": args.mode, "brightness": BRIGHTNESS[args.brightness],
                         "speed": SPEED[args.speed], "direction": args.direction,
                         "colors": [parse_color(c) for c in args.colors]}
                m.apply({"lighting": light})
                print(format_state(m.get_state()))
            elif args.cmd == "dpi":
                cur = m.get_state()["dpi"]
                if args.values or args.active or args.colors:
                    stages = cur["stages"]
                    if args.values:
                        old = stages
                        stages = [{"dpi": v, "color": old[i]["color"] if i < len(old) else "ffffff"}
                                  for i, v in enumerate(args.values)]
                    for i, c in enumerate(args.colors or []):
                        if i < len(stages):
                            stages[i]["color"] = parse_color(c)
                    active = args.active - 1 if args.active else cur["active"]
                    m.apply({"dpi": {"stages": stages, "active": active}})
                print(format_state(m.get_state()).split("\n")[1])
            elif args.cmd == "profile":
                if args.action == "save":
                    save_profile(args.name, m.get_state())
                    print(f"saved {args.name}")
                else:
                    m.apply(load_profile(args.name))
                    print(format_state(m.get_state()))
            elif args.cmd == "backup":
                with open(args.file, "wb") as f:
                    f.write(m.read_config())
                print(f"saved {args.file}")
            elif args.cmd == "restore":
                with open(args.file, "rb") as f:
                    data = f.read()
                if len(data) != CONFIG_SIZE or data[0] != 0x04:
                    print("not a config dump", file=sys.stderr)
                    return 1
                m.write_config(data)
                print("restored")
            else:
                print(f"{m.path}  firmware {m.firmware() or '?'}")
                print(format_state(m.get_state()))
    except (RuntimeError, ValueError, OSError, KeyError, json.JSONDecodeError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
