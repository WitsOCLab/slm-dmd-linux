"""`slmscreen`: the outputs from the shell - list them, put a pattern on one."""

from __future__ import annotations

import argparse
import sys
import time


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="slmscreen", description="SLMs and DMDs as displays.")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="connected outputs with their EDID names")
    s = sub.add_parser("show", help="hold a pattern on an output until Ctrl-C (or --seconds)")
    s.add_argument("output", help="EDID name, e.g. 'HE PLUTO-2.1', or connector, e.g. DP-6")
    s.add_argument("pattern", help="blank | crosshair | disc | blazed | binary_grating | oam | lee | checker | file.npy")
    s.add_argument("params", nargs="*", help="pattern parameters as key=value, e.g. period_px=16 angle_deg=45")
    s.add_argument("--seconds", type=float, help="how long to hold it; default until Ctrl-C")
    return p


def main(argv: list[str] | None = None) -> int:
    from . import patterns
    from .displays import Display, find_output, list_outputs, session_is_wayland
    args = build_parser().parse_args(argv)
    if args.command == "list":
        print(f"session: {'Wayland' if session_is_wayland() else 'X11'}")
        for o in list_outputs():
            print(f"  {o.connector:10} edid_name={o.edid_name!r:22} serial={o.edid_serial}  "
                  f"{o.width}x{o.height}+{o.x}+{o.y}{'  scale ' + format(o.scale, 'g') + 'x' if o.scale != 1.0 else ''}")
        return 0
    try:
        try:
            output = find_output(edid_name=args.output)
        except LookupError:
            output = find_output(connector=args.output)
    except LookupError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    if args.pattern.endswith(".npy"):
        import numpy as np
        frame = np.load(args.pattern)
    else:
        kv = {}
        for item in args.params:
            k, v = item.split("=", 1)
            kv[k] = float(v) if "." in v or "e" in v.lower() else int(v)
        frame = patterns.render(args.pattern, output.width, output.height, **kv)
    with Display("slmscreen", output) as display:
        info = display.show(frame)
        print(f"{args.pattern} on {output.connector} ({output.edid_name}) at {info}")
        try:
            time.sleep(args.seconds if args.seconds else 10 ** 9)
        except KeyboardInterrupt:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
