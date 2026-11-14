import unittest

import pandas as pd
from streamlit.testing.v1 import AppTest

from src.season_summary import summarize_season


def series(area, values, year=2022):
    return pd.DataFrame({'area': area, 'year': year, 'month': range(1, 13), 'harmonized': values})


class SeasonTests(unittest.TestCase):
    def test_summer_and_threshold_boundary(self):
        s = summarize_season(series('Canada', [0,0,0,0,20,60,100,30,19,0,0,0]), 'Canada')
        self.assertEqual((s.start_month, s.peak_month, s.end_month), (5,7,8))

    def test_wrap_and_disconnected_secondary_peak(self):
        s = summarize_season(series('Argentina', [100,40,0,0,0,80,0,0,0,0,20,60]), 'Argentina')
        self.assertEqual(s.season_months, (11,12,1,2))

    def test_missing_months_are_not_zero_and_partial_years_excluded(self):
        full = series('Canada', [0]*5+[10]+[0]*6)
        partial = series('Canada', [100]*12, 2023).iloc[:11]
        d = pd.concat([full, partial])
        s = summarize_season(d, 'Canada')
        self.assertEqual(s.years, (2022,))
        self.assertEqual(s.season_months, (6,))
        self.assertEqual(summarize_season(partial, 'Canada').status, 'incomplete_data')
        full.loc[0,'harmonized'] = pd.NA
        self.assertEqual(summarize_season(full, 'Canada').status, 'incomplete_data')

    def test_mean_across_years_and_tied_peaks(self):
        d = pd.concat([series('Canada', [0,0,10,0,0,0,0,0,0,0,0,0]),
                       series('Canada', [0,0,0,0,10,0,0,0,0,0,0,0], 2023)])
        self.assertEqual(summarize_season(d, 'Canada').peak_month, 3)

    def test_no_activity_no_data_and_year_round(self):
        d = series('Canada', [0]*12)
        self.assertEqual(summarize_season(d, 'Canada').status, 'no_activity')
        self.assertEqual(summarize_season(d, 'Argentina').status, 'no_data')
        self.assertEqual(summarize_season(series('Canada', [1]*12), 'Canada').status, 'year_round')

    def test_validation(self):
        d = series('Canada', [1]*12)
        for value in [-1, float('inf'), 'bad']:
            bad = d.copy().astype({'harmonized':'object'})
            bad.loc[0,'harmonized'] = value
            with self.assertRaises(ValueError):
                summarize_season(bad, 'Canada')
        with self.assertRaises(ValueError):
            summarize_season(pd.concat([d,d]), 'Canada')
        for month in [0,13,1.5,None]:
            bad = d.copy().astype({'month':'object'})
            bad.loc[0,'month'] = month
            with self.assertRaises(ValueError):
                summarize_season(bad, 'Canada')
        with self.assertRaises(ValueError):
            summarize_season(d, 'Canada', threshold_fraction=0)

    def test_area_selection_updates_three_metrics(self):
        script = '''
import pandas as pd
from src.season_summary import render_season_summary
rows = []
for area, peak in [('Canada',7), ('Argentina',1)]:
    for month in range(1,13):
        rows.append(dict(area=area,year=2022,month=month,harmonized=100 if month==peak else 0))
render_season_summary(pd.DataFrame(rows))
'''
        app = AppTest.from_string(script).run()
        self.assertFalse(app.exception)
        self.assertEqual([m.value for m in app.metric], ['January']*3)
        app.selectbox[0].select('Canada').run()
        self.assertFalse(app.exception)
        self.assertEqual([m.value for m in app.metric], ['July']*3)


if __name__ == '__main__':
    unittest.main()
