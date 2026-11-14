"""Tests for src/palette.py. Run from the repo root: python -m unittest discover tests"""

import math
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import palette as P  # noqa: E402

HEX = re.compile(r"^#[0-9a-f]{6}$")


class PaletteTest(unittest.TestCase):
    def test_all_colours_are_hex(self):
        colours = P.ACTIVITY_SCALE + [
            P.ZERO_COLOR, P.NO_DATA_COLOR, P.FLAG_HIGH_COLOR, P.FLAG_LOW_COLOR,
        ]
        for c in colours:
            self.assertRegex(c, HEX)

    def test_scale_gets_darker(self):
        lum = [P.relative_luminance(c) for c in P.ACTIVITY_SCALE]
        self.assertEqual(lum, sorted(lum, reverse=True))

    def test_special_cells(self):
        self.assertEqual(P.activity_color(None, 100), P.NO_DATA_COLOR)
        self.assertEqual(P.activity_color(math.nan, 100), P.NO_DATA_COLOR)
        self.assertEqual(P.activity_color(0, 100), P.ZERO_COLOR)
        self.assertEqual(P.activity_color(5, 0), P.ZERO_COLOR)
        self.assertNotIn(P.ZERO_COLOR, P.ACTIVITY_SCALE)
        self.assertNotIn(P.NO_DATA_COLOR, P.ACTIVITY_SCALE)

    def test_extremes(self):
        self.assertEqual(P.activity_color(1, 10_000), P.ACTIVITY_SCALE[0])
        self.assertEqual(P.activity_color(10_000, 10_000), P.ACTIVITY_SCALE[-1])
        self.assertEqual(P.activity_color(50_000, 10_000), P.ACTIVITY_SCALE[-1])

    def test_legend_matches_cells(self):
        for vmax in (1, 3, 10, 250, 16_640, 48_000.5):
            bins = P.legend_bins(vmax)
            colours = [c for c, _ in bins]
            self.assertEqual(len(colours), len(set(colours)), vmax)
            expected_low = 1
            for colour, label in bins:
                low, _, high = label.partition("-")
                low, high = int(low), int(high or low)
                self.assertEqual(low, expected_low, (vmax, label))
                self.assertEqual(P.activity_color(low, vmax), colour)
                self.assertEqual(P.activity_color(high, vmax), colour)
                expected_low = high + 1
            self.assertEqual(expected_low - 1, math.ceil(vmax))

    def test_text_is_readable_on_every_fill(self):
        for fill in P.ACTIVITY_SCALE + [P.ZERO_COLOR, P.NO_DATA_COLOR]:
            self.assertGreaterEqual(P.contrast_ratio(fill, P.text_color_for(fill)), 4.5, fill)


if __name__ == "__main__":
    unittest.main()
