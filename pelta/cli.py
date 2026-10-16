"""Command line interface: `pelta-control <command>`; no command opens the GUI."""

import argparse
import sys

from . import device, eq_presets
from .device import Pelta, PeltaError


def on_off(v):
    if v.lower() in ("on", "1", "true", "yes"):
        return True
    if v.lower() in ("off", "0", "false", "no"):
        return False
    raise argparse.ArgumentTypeError("expected on/off")


def color(v):
    v = v.lstrip("#")
    if len(v) != 6:
        raise argparse.ArgumentTypeError("expected RRGGBB")
    return tuple(int(v[i:i + 2], 16) for i in (0, 2, 4))


def print_status(s):
    if not s.connected:
        print("Headset: off or out of range")
        return
    print(f"Battery:          {s.battery}%{' (charging)' if s.charging else ''}")
    effect = "Off" if s.brightness == 0 else device.EFFECTS.get(s.effect, s.effect)
    print(f"Lighting:         {effect}, {s.brightness}%, #{bytes(s.color).hex()}")
    print(f"Noise reduction:  {'on' if s.noise_reduction else 'off'}")
    print(f"Sidetone:         {'on' if s.sidetone else 'off'} (level {s.sidetone_level}/{device.SIDETONE_MAX})")
    print(f"Connection:       {device.LATENCY.get(s.latency, s.latency)}")
    print(f"Voice prompts:    {device.VOICE_PROMPT.get(s.voice_prompt, s.voice_prompt)}")
    print(f"Auto sleep:       {f'{s.sleep_minutes} min' if s.sleep_minutes else 'never'}")
    print(f"Low battery:      lights below {s.low_battery_level}%, voice {'on' if s.low_battery_voice else 'off'}")
    print(f"Firmware:         {' / '.join(s.firmware)}")


def main(argv):
    p = argparse.ArgumentParser(prog="pelta-control", description="ASUS ROG Pelta control for Linux")
    sub = p.add_subparsers(dest="cmd")
    sub.add_parser("gui", help="open the control panel (default)").add_argument("--tray", action="store_true")
    sub.add_parser("status", help="show headset state")
    sub.add_parser("battery", help="print battery percent only")
    s = sub.add_parser("light", help="set lighting")
    s.add_argument("effect", choices=["static", "breathing", "strobing", "cycle", "off"])
    s.add_argument("--color", type=color, default=(128, 0, 255), help="RRGGBB (default 8000ff)")
    s.add_argument("--brightness", type=int, default=100, choices=range(0, 101, 5), metavar="0-100")
    sub.add_parser("sidetone", help="sidetone on/off").add_argument("state", type=on_off)
    sub.add_parser("sidetone-level", help="sidetone level 0-20").add_argument("level", type=int)
    sub.add_parser("nr", help="AI noise reduction on/off").add_argument("state", type=on_off)
    sub.add_parser("latency", help="connection priority").add_argument("mode", choices=["low", "stable"])
    sub.add_parser("sleep", help="auto sleep minutes (0 = never)").add_argument(
        "minutes", type=int, choices=device.SLEEP_MINUTES)
    sub.add_parser("export-eq", help="write ROG EQ presets for EasyEffects")
    args = p.parse_args(argv)

    if args.cmd in (None, "gui"):
        from .gui import main as gui_main
        return gui_main(sys.argv[:1] + (["--tray"] if getattr(args, "tray", False) else []))
    if args.cmd == "export-eq":
        for path in eq_presets.export():
            print(path)
        return 0

    try:
        with Pelta() as d:
            if args.cmd == "status":
                print_status(d.status())
                return 0
            if not d.headset_connected():
                print("Headset is off or out of range", file=sys.stderr)
                return 2
            if args.cmd == "battery":
                print(d.power_info()[1])
            elif args.cmd == "light":
                effects = {"static": 1, "breathing": 2, "strobing": 3, "cycle": 4}
                if args.effect == "off":
                    d.set_lighting(1, 0, args.color)
                else:
                    d.set_lighting(effects[args.effect], args.brightness, args.color)
            elif args.cmd == "sidetone":
                d.set_sidetone(args.state)
            elif args.cmd == "sidetone-level":
                d.set_sidetone_level(args.level)
            elif args.cmd == "nr":
                d.set_noise_reduction(args.state)
            elif args.cmd == "latency":
                d.set_latency(0x28 if args.mode == "low" else 0x64)
            elif args.cmd == "sleep":
                _, _, level, voice = d.power_info()
                d.set_power(args.minutes, level, voice)
    except PeltaError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    return 0
