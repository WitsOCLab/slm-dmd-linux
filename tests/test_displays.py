"""Parsers for display discovery, with output captured on the rig PC."""

import os
import unittest
from unittest import mock

from slmscreen import displays

COSMIC_RANDR = (
    "\x1b[1mDP-6\x1b[0m \x1b[1;32m(enabled)\x1b[0m\x1b[1;33m\n"
    "  Make: \x1b[0mHoloeye Photonics AG\x1b[1;33m\n"
    "  Model: \x1b[0mHE PLUTO-2.1\x1b[1;33m\n"
    "  Physical Size: \x1b[0m0 x 0 mm\x1b[1;33m\n"
    "  Position: \x1b[0m1920,0\x1b[1;33m\n"
    "  Scale: \x1b[0m100%\x1b[1;33m\n"
    "\n"
    "  Modes:\x1b[0m\n"
    "    \x1b[35m1920x1080\x1b[0m @ \x1b[36m 60.000 Hz\x1b[0m\x1b[1;35m (current)\x1b[0m\x1b[1;32m (preferred)\x1b[0m\n"
    "\x1b[1mHDMI-A-2\x1b[0m \x1b[1;32m(enabled)\x1b[0m\x1b[1;33m\n"
    "  Make: \x1b[0mPNP(DLP)\x1b[1;33m\n"
    "  Model: \x1b[0mITE6801 \x1b[1;33m\n"
    "  Position: \x1b[0m0,0\x1b[1;33m\n"
    "  Modes:\x1b[0m\n"
    "    \x1b[35m1920x1080\x1b[0m @ \x1b[36m 59.999 Hz\x1b[0m\x1b[1;35m (current)\x1b[0m\n"
    "    \x1b[35m 1280x720\x1b[0m @ \x1b[36m 59.943 Hz\x1b[0m\n"
    "\x1b[1mDP-4\x1b[0m \x1b[1;31m(disabled)\x1b[0m\n"
    "  Model: \x1b[0mLG HDR WFHD\n"
    "  Modes:\n    2560x1080 @ 59.98 Hz (current)\n"
)


class CosmicRandrTest(unittest.TestCase):
    def test_parses_enabled_outputs_and_strips_colours(self):
        fake = mock.Mock(stdout=COSMIC_RANDR)
        with mock.patch.object(displays.subprocess, "run", return_value=fake):
            outs = displays._list_outputs_wayland()
        self.assertEqual([(o.connector, o.edid_name, o.width, o.height, o.x, o.y) for o in outs],
                         [("DP-6", "HE PLUTO-2.1", 1920, 1080, 1920, 0), ("HDMI-A-2", "ITE6801", 1920, 1080, 0, 0)])

    def test_find_output_matches_make_model_form(self):
        with mock.patch.object(displays, "list_outputs", return_value=[
                displays.Output("DP-6", "HOLOEYE HE PLUTO-2.1", None, 1920, 1080, 0, 0, False, None, None)]):
            self.assertEqual(displays.find_output("HE PLUTO-2.1").connector, "DP-6")
            with self.assertRaises(LookupError):
                displays.find_output("ITE6801")


class SessionTest(unittest.TestCase):
    def test_session_detection(self):
        with mock.patch.dict(os.environ, {"WAYLAND_DISPLAY": "wayland-1", "XDG_SESSION_TYPE": "wayland"}):
            self.assertTrue(displays.session_is_wayland())
        with mock.patch.dict(os.environ, {"WAYLAND_DISPLAY": "", "XDG_SESSION_TYPE": "x11"}):
            self.assertFalse(displays.session_is_wayland())


def _edid(name: str, serial: int = 0) -> bytes:
    """A minimal 128-byte EDID with a monitor-name descriptor, enough for the parser."""
    block = bytearray(128)
    block[0:8] = b"\x00\xff\xff\xff\xff\xff\xff\x00"
    block[12:16] = serial.to_bytes(4, "little")
    descriptor = b"\x00\x00\x00\xfc\x00" + name.encode("ascii").ljust(13, b"\n")[:13]
    block[54:72] = descriptor
    return bytes(block)


class DrmBackendTest(unittest.TestCase):
    """Wayland on any compositor: EDID from sysfs, geometry from GLFW, joined on the connector name."""

    MONITORS = [
        {"name": "HDMI-A-2", "width": 1920, "height": 1080, "x": 0, "y": 0, "scale": 1.0},
        {"name": "DP-6", "width": 1920, "height": 1080, "x": 1920, "y": 0, "scale": 1.0},
        {"name": "DP-4", "width": 2560, "height": 1080, "x": 3840, "y": 0, "scale": 1.5},
    ]
    EDIDS = {"DP-6": _edid("HE PLUTO-2.1", 1188), "HDMI-A-2": _edid("ITE6801"), "DP-4": _edid("LG HDR WFHD")}

    def test_joins_edid_names_onto_glfw_geometry(self):
        with mock.patch.object(displays, "_drm_edids", return_value=self.EDIDS), \
             mock.patch.object(displays, "_glfw_monitors", return_value=self.MONITORS):
            outs = displays._list_outputs_drm()
        self.assertEqual([(o.connector, o.edid_name, o.edid_serial, o.width, o.x, o.scale) for o in outs],
                         [("HDMI-A-2", "ITE6801", 0, 1920, 0, 1.0), ("DP-6", "HE PLUTO-2.1", 1188, 1920, 1920, 1.0),
                          ("DP-4", "LG HDR WFHD", 0, 2560, 3840, 1.5)])
        self.assertTrue(outs[0].primary)

    def test_wayland_prefers_sysfs_and_falls_back_to_cosmic_randr(self):
        with mock.patch.object(displays, "session_is_wayland", return_value=True), \
             mock.patch.object(displays, "_drm_edids", return_value=self.EDIDS), \
             mock.patch.object(displays, "_glfw_monitors", return_value=self.MONITORS), \
             mock.patch.object(displays, "_list_outputs_wayland", side_effect=AssertionError("should not be called")):
            self.assertEqual([o.edid_name for o in displays.list_outputs()], ["ITE6801", "HE PLUTO-2.1", "LG HDR WFHD"])
        # a driver with no EDID in sysfs: the compositor's own tool is the second chance
        fake = mock.Mock(stdout=COSMIC_RANDR)
        with mock.patch.object(displays, "session_is_wayland", return_value=True), \
             mock.patch.object(displays, "_drm_edids", return_value={}), \
             mock.patch.object(displays, "_glfw_monitors", return_value=self.MONITORS), \
             mock.patch.object(displays.subprocess, "run", return_value=fake):
            self.assertEqual([o.connector for o in displays.list_outputs()], ["DP-6", "HDMI-A-2"])

    def test_find_output_by_edid_name_through_the_drm_backend(self):
        with mock.patch.object(displays, "session_is_wayland", return_value=True), \
             mock.patch.object(displays, "_drm_edids", return_value=self.EDIDS), \
             mock.patch.object(displays, "_glfw_monitors", return_value=self.MONITORS):
            self.assertEqual(displays.find_output("HE PLUTO-2.1").connector, "DP-6")
            self.assertEqual(displays.find_output("ITE6801").scale, 1.0)
            with self.assertRaises(LookupError):
                displays.find_output("HOLOEYE ERIS")

    def test_sysfs_reader_skips_disconnected_and_short_edids(self):
        import tempfile, pathlib
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            for conn, status, edid in (("card1-DP-6", "connected", _edid("HE PLUTO-2.1")),
                                       ("card1-DP-5", "disconnected", b""),
                                       ("card1-HDMI-A-2", "connected", b"\x00" * 20)):
                d = root / conn
                d.mkdir()
                (d / "status").write_text(status + "\n")
                (d / "edid").write_bytes(edid)
            with mock.patch.object(displays.glob, "glob", return_value=[str(root / c / "edid") for c in
                                                                        ("card1-DP-6", "card1-DP-5", "card1-HDMI-A-2")]):
                edids = displays._drm_edids()
        self.assertEqual(list(edids), ["DP-6"])
