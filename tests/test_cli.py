"""The command line, without a panel: listing outputs."""
import io
import unittest
from unittest import mock

from slmscreen import cli, displays


class CliTest(unittest.TestCase):
    def test_list_prints_edid_names_and_flags_scaling(self):
        outs = [displays.Output("DP-6", "HE PLUTO-2.1", 1188, 1920, 1080, 1920, 0, False, None, None, 1.0),
                displays.Output("DP-4", "LG HDR WFHD", 1351, 2560, 1080, 3840, 0, True, None, None, 1.5)]
        with mock.patch.object(cli, "build_parser", wraps=cli.build_parser), \
             mock.patch("slmscreen.displays.list_outputs", return_value=outs), \
             mock.patch("slmscreen.displays.session_is_wayland", return_value=True), \
             mock.patch("sys.stdout", new_callable=io.StringIO) as out:
            self.assertEqual(cli.main(["list"]), 0)
        text = out.getvalue()
        self.assertIn("HE PLUTO-2.1", text)
        self.assertIn("scale 1.5x", text)

    def test_unknown_output_is_an_error(self):
        with mock.patch("slmscreen.displays.list_outputs", return_value=[]), \
             mock.patch("sys.stderr", new_callable=io.StringIO) as err:
            self.assertEqual(cli.main(["show", "HOLOEYE ERIS", "blank"]), 1)
        self.assertIn("no connected output", err.getvalue())


if __name__ == "__main__":
    unittest.main()
