import math
import re
import unittest

import pandas as pd

from src import palette as P
from src.calendar_view import calendar_html, format_count, sample_monthly


def cell(html: str, year: int, month: int) -> str:
    """The <td> for one year-month, found by its data attributes."""
    m = re.search(rf'<td[^>]*data-year="{year}" data-month="{month}"[^>]*>.*?</td>', html, re.S)
    assert m, f'no cell for {year}-{month}'
    return m.group(0)


class FormatCountTests(unittest.TestCase):
    def test_formats(self):
        self.assertEqual(format_count(0), '0')
        self.assertEqual(format_count(950), '950')
        self.assertEqual(format_count(1234), '1.2k')
        self.assertEqual(format_count(16640), '16.6k')
        self.assertEqual(format_count(1_250_000), '1.2M')


class SampleTests(unittest.TestCase):
    def test_shape_and_repeatable(self):
        a, b = sample_monthly(), sample_monthly()
        self.assertEqual(len(a), 12 * 12)  # 2012-2023
        self.assertEqual(sorted(a['year'].unique()), list(range(2012, 2024)))
        pd.testing.assert_frame_equal(a, b)
        self.assertEqual(list(a.columns), ['area', 'year', 'month', 'harmonized'])

    def test_has_no_data_zero_and_a_summer_peak(self):
        s = sample_monthly()
        self.assertTrue(s['harmonized'].isna().any())
        self.assertTrue((s['harmonized'] == 0).any())
        peak = s.loc[s['harmonized'].idxmax()]
        self.assertIn(int(peak['month']), (6, 7, 8))


class CalendarHtmlTests(unittest.TestCase):
    def setUp(self):
        self.data = pd.DataFrame({
            'area': 'Canada',
            'year': [2021] * 12 + [2022] * 12,
            'month': list(range(1, 13)) * 2,
            'harmonized': [float('nan')] + [0.0] + [5.0] * 4 + [16640.0] + [2.0] * 5
                          + [1.0] * 6 + [1234.0] + [1.0] * 5,
        })
        self.html = calendar_html(self.data, title='Test <calendar>')

    def test_newest_year_first_and_twelve_months(self):
        rows = re.findall(r'<th class="fc-year"[^>]*>(\d{4})</th>', self.html)
        self.assertEqual(rows, ['2022', '2021'])
        for label in P.MONTH_LABELS:
            self.assertIn(f'>{label}<', self.html)

    def test_cell_colours_follow_the_palette(self):
        vmax = 16640.0
        self.assertIn(P.NO_DATA_COLOR, cell(self.html, 2021, 1))
        self.assertIn(P.ZERO_COLOR, cell(self.html, 2021, 2))
        self.assertIn(P.activity_color(16640.0, vmax), cell(self.html, 2021, 7))
        self.assertIn(P.activity_color(5.0, vmax), cell(self.html, 2021, 3))

    def test_peak_cells_are_labelled_small_ones_are_not(self):
        self.assertIn('16.6k', cell(self.html, 2021, 7))
        self.assertIn('1.2k', cell(self.html, 2022, 7))
        self.assertNotIn('>5<', cell(self.html, 2021, 3))

    def test_every_cell_has_a_tooltip(self):
        self.assertIn('title="Jul 2021: 16,640"', self.html)
        self.assertIn('title="Jan 2021: no data"', self.html)

    def test_legend_lists_no_data_zero_and_every_bin(self):
        self.assertIn('no data', self.html)
        for _, label in P.legend_bins(16640.0):
            self.assertIn(f'>{label}<', self.html)

    def test_flagged_years_get_an_outline(self):
        html = calendar_html(self.data, flags={2022: 'high', 2021: 'low'})
        self.assertIn(P.FLAG_HIGH_COLOR, html)
        self.assertIn(P.FLAG_LOW_COLOR, html)
        self.assertIn('unusually high', html)

    def test_text_is_escaped(self):
        self.assertIn('Test &lt;calendar&gt;', self.html)
        self.assertNotIn('<calendar>', self.html)

    def test_all_missing_still_renders(self):
        empty = self.data.assign(harmonized=math.nan)
        html = calendar_html(empty)
        self.assertIn(P.NO_DATA_COLOR, html)


if __name__ == '__main__':
    unittest.main()
