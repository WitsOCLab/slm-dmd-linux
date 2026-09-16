import unittest

import numpy as np

from slmscreen import patterns as P


class PatternTest(unittest.TestCase):
    W, H = 256, 128

    def test_shapes_and_dtype(self):
        for kind, kw in (("blank", {"level": 7}), ("crosshair", {}), ("disc", {"radius": 20}), ("blazed", {"period_px": 16}),
                         ("binary_grating", {"period_px": 8}), ("oam", {"ell": 2}), ("lee", {"ell": 1}), ("checker", {})):
            img = P.render(kind, self.W, self.H, **kw)
            self.assertEqual((img.shape, img.dtype), ((self.H, self.W), np.uint8), kind)

    def test_blazed_grating_period_and_direction(self):
        g = P.blazed_grating(self.W, self.H, period_px=16, angle_deg=0)
        row = g[self.H // 2].astype(int)
        self.assertTrue(np.array_equal(row[:16], row[16:32]))          # exactly periodic
        self.assertEqual(len(np.unique(row[:16])), 16)                 # 16 distinct levels per period
        self.assertTrue((np.diff(row[:16]) > 0).all())                 # a rising ramp along +x
        gy = P.blazed_grating(self.W, self.H, period_px=16, angle_deg=90)
        self.assertTrue(np.array_equal(gy[:, 10], gy[:, 100]))         # constant along x for a vertical ramp

    def test_grey_2pi_scaling(self):
        g = P.blazed_grating(self.W, self.H, period_px=32, grey_2pi=200)
        self.assertLessEqual(g.max(), 200)
        self.assertGreaterEqual(g.max(), 190)

    def test_depth_reduces_modulation(self):
        full = P.blazed_grating(self.W, self.H, period_px=32, depth=1.0)
        half = P.blazed_grating(self.W, self.H, period_px=32, depth=0.5)
        self.assertGreater(full.max() - full.min(), half.max() - half.min())

    def test_oam_phase_winds_ell_times(self):
        ell = 3
        h = P.oam_hologram(self.W, self.H, ell=ell, period_px=0)      # no carrier: pure helical phase
        cx, cy, r = (self.W - 1) / 2, (self.H - 1) / 2, 30
        angles = np.linspace(0, 2 * np.pi, 400, endpoint=False)
        ring = h[(cy + r * np.sin(angles)).round().astype(int), (cx + r * np.cos(angles)).round().astype(int)].astype(float)
        ring = np.append(ring, ring[0])                                  # close the loop
        wraps = int(np.sum(np.abs(np.diff(ring)) > 128))                # 2pi wraps around the ring (either sign)
        self.assertEqual(wraps, ell)

    def test_amplitude_encoding_is_dark_far_from_beam(self):
        h = P.oam_hologram(self.W, self.H, ell=1, waist_px=10, period_px=8, encoding="amplitude")
        centre = h[self.H // 2 - 8: self.H // 2 + 8, self.W // 2 - 8: self.W // 2 + 8]
        corner = h[:16, :16]
        self.assertGreater(centre.std(), corner.std())

    def test_lee_is_binary_and_carrier_periodic(self):
        h = P.lee_hologram(self.W, self.H, ell=0, waist_px=40, period_px=8)
        self.assertEqual(set(np.unique(h).tolist()) - {0, 255}, set())
        self.assertGreater(h.mean(), 0)

    def test_crosshair_centre(self):
        c = P.crosshair(self.W, self.H, centre=(40, 30), size=10, thickness=1, rings=())
        self.assertEqual(c[30, 40], 255)
        self.assertEqual(c[30, 60], 0)
        self.assertEqual(c[35, 40], 255)

    def test_experiment_presets_match_the_matlab_numbers(self):
        slm = P.experiment_presets("slm", 1920, 1080, 8.0)
        kind, prm = slm["SLM experiment: LG(0,0) + blazed carrier (532 nm)"]
        self.assertEqual(kind, "oam")
        # 200 periods/screen at 150 deg with the code's axis swap and the 632.8/532 factor: 25.1 cycles/mm -> 39.9 um
        self.assertAlmostEqual(prm["period_px"], 4.99, delta=0.02)
        self.assertAlmostEqual(prm["angle_deg"], 162.0, delta=0.2)
        self.assertAlmostEqual(prm["waist_px"], 62.5, delta=0.01)       # w0 = 0.5 mm
        dmd = P.experiment_presets("dmd", 1920, 1080, 5.4)
        kind, prm = dmd["DMD alignment target: LG(2,1) donut, experiment carrier"]
        self.assertEqual((kind, prm["ell"], prm["p"]), ("lee", 2, 1))
        self.assertAlmostEqual(prm["period_px"], 4.87, delta=0.01)      # 38 lines/mm at 5.4 um pitch
        self.assertAlmostEqual(prm["angle_deg"], 67.5)
        for name, (k, params) in {**slm, **dmd}.items():
            img = P.render(k, 192, 108, **params) if k != "blank" else P.render(k, 192, 108, **params)
            self.assertEqual(img.shape, (108, 192), name)

    def test_lee_matches_matlab_threshold(self):
        # AddBinaryGrating: 0.5 + 0.5*sign(cos(2*pi*plane*G + phase) - cos(asin(A)))
        w, h = 64, 32
        img = P.lee_hologram(w, h, ell=0, p=0, waist_px=10, period_px=8, angle_deg=0)
        x, y = P._grid(w, h)
        field = P.lg_field(w, h, 0, 0, 10)
        expected = (np.cos(2 * np.pi * x / 8 + np.angle(field)) - np.cos(np.arcsin(np.abs(field))) > 0) * 255
        np.testing.assert_array_equal(img, expected.astype(np.uint8))

    def test_unknown_pattern(self):
        with self.assertRaises(ValueError):
            P.render("spiral", 10, 10)


if __name__ == "__main__":
    unittest.main()
