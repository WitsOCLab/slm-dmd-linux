"""`python -m slmscreen`: the connected outputs with the EDID names to put in a config."""

from .displays import list_outputs, session_is_wayland

print(f"session: {'Wayland' if session_is_wayland() else 'X11'}")
for o in list_outputs():
    flags = ("primary " if o.primary else "") + (f"scale {o.scale:g}x " if o.scale != 1.0 else "")
    print(f"  {o.connector:10} edid_name={o.edid_name!r:22} serial={o.edid_serial}  {o.width}x{o.height}+{o.x}+{o.y}  {flags}")
