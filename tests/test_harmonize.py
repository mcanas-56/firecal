import math
import unittest

import pandas as pd

from src.harmonize import fit_factors, harmonize, monthly_cell_days


def det(date, lat=45.01, lon=-75.01, instrument='MODIS', satellite='Aqua',
        area='Canada', source_file=None):
    """One cleaned detection, shaped like load_hotspots output."""
    year = date[:4]
    sensor = 'modis' if instrument == 'MODIS' else 'viirs-snpp'
    return dict(latitude=lat, longitude=lon, acq_date=pd.Timestamp(date),
                instrument=instrument, satellite=satellite, area=area,
                source_file=source_file or f'{sensor}_{year}_{area}.csv')


def frame(rows):
    return pd.DataFrame(rows)


class CellDayTests(unittest.TestCase):
    def test_many_detections_in_one_cell_on_one_day_count_once(self):
        rows = [det('2022-06-01', lat=45.01 + i * 0.01, lon=-75.01) for i in range(5)]  # all in one 0.1 deg cell
        rows.append(det('2022-06-01', lat=46.05, lon=-75.01))   # a second cell, same day
        rows.append(det('2022-06-02', lat=45.01, lon=-75.01))   # first cell again, next day
        monthly = monthly_cell_days(frame(rows), grid=0.1)
        june = monthly[(monthly.sensor == 'modis') & (monthly.month == 6)]
        self.assertEqual(int(june.cell_days.iloc[0]), 3)

    def test_sensors_are_counted_separately(self):
        rows = [det('2022-06-01'),
                det('2022-06-01', instrument='VIIRS', satellite='N')]
        monthly = monthly_cell_days(frame(rows), grid=0.1)
        june = monthly[monthly.month == 6].set_index('sensor').cell_days
        self.assertEqual(int(june['modis']), 1)
        self.assertEqual(int(june['viirs']), 1)

    def test_month_with_no_fires_is_zero(self):
        rows = [det('2022-01-15'), det('2022-03-15')]
        monthly = monthly_cell_days(frame(rows), grid=0.1)
        modis = monthly[monthly.sensor == 'modis'].set_index('month').cell_days
        self.assertEqual(list(modis.index), list(range(1, 13)))  # whole year of the source file
        self.assertEqual(int(modis[2]), 0)
        self.assertEqual(int(modis[12]), 0)

    def test_year_without_a_sensor_file_is_missing_not_zero(self):
        rows = [det('2010-07-01'), det('2022-07-01'),
                det('2022-07-01', instrument='VIIRS', satellite='N')]
        monthly = monthly_cell_days(frame(rows), grid=0.1)
        viirs_2010 = monthly[(monthly.sensor == 'viirs') & (monthly.year == 2010)]
        self.assertTrue(viirs_2010.cell_days.isna().all())
        self.assertEqual(len(viirs_2010), 12)

    def test_terra_dropped_by_default_and_kept_on_request(self):
        rows = [det('2022-06-01', satellite='Terra')]
        self.assertEqual(int(monthly_cell_days(frame(rows)).cell_days.sum()), 0)
        self.assertEqual(int(monthly_cell_days(frame(rows), include_terra=True).cell_days.sum()), 1)


class FactorTests(unittest.TestCase):
    def synthetic(self, ratio, months=24, noise=None):
        """Wide table: MODIS cell-days per month and VIIRS = ratio x MODIS."""
        idx = pd.MultiIndex.from_product([['Canada'], [2022, 2023], range(1, 13)],
                                         names=['area', 'year', 'month'])
        modis = pd.Series([10 + 7 * (i % 12) for i in range(months)], index=idx, dtype=float)
        viirs = modis * ratio
        if noise is not None:
            viirs = viirs + noise.to_numpy()
        return pd.DataFrame({'modis_cell_days': modis, 'viirs_cell_days': viirs}).reset_index()

    def test_factor_recovered_from_known_ratio(self):
        fits = fit_factors(self.synthetic(3.5))
        fit = fits.set_index('area').loc['Canada']
        self.assertAlmostEqual(fit.factor, 3.5, places=9)
        self.assertAlmostEqual(fit.r2, 1.0, places=9)
        self.assertAlmostEqual(fit.median_abs_pct_diff, 0.0, places=9)
        self.assertEqual(int(fit.overlap_months), 24)

    def test_factor_close_with_noise(self):
        noise = pd.Series([(-1) ** i * 2.0 for i in range(24)])
        fit = fit_factors(self.synthetic(2.0, noise=noise)).set_index('area').loc['Canada']
        self.assertAlmostEqual(fit.factor, 2.0, delta=0.05)
        self.assertGreater(fit.r2, 0.95)

    def test_no_overlap_gives_no_factor(self):
        wide = self.synthetic(2.0)
        wide['viirs_cell_days'] = float('nan')
        fit = fit_factors(wide).set_index('area').loc['Canada']
        self.assertTrue(math.isnan(fit.factor))
        self.assertEqual(int(fit.overlap_months), 0)


class HarmonizeTests(unittest.TestCase):
    def test_pre_viirs_months_use_modis_times_factor(self):
        rows = []
        # Overlap year 2022: each month MODIS has 1 cell-day, VIIRS 3 (factor 3).
        for m in range(1, 13):
            d = f'2022-{m:02d}-01'
            rows.append(det(d))
            for k in range(3):
                rows.append(det(d, lat=40.05 + k, instrument='VIIRS', satellite='N'))
        # Pre-VIIRS year 2010: MODIS only, 2 cell-days in May.
        rows += [det('2010-05-01'), det('2010-05-02')]
        table, fits = harmonize(frame(rows), grid=0.1)
        self.assertAlmostEqual(fits.set_index('area').loc['Canada'].factor, 3.0)

        may_2010 = table[(table.year == 2010) & (table.month == 5)].iloc[0]
        self.assertEqual(may_2010.source, 'modis_scaled')
        self.assertAlmostEqual(may_2010.harmonized, 6.0)
        self.assertTrue(pd.isna(may_2010.viirs_cell_days))

        june_2022 = table[(table.year == 2022) & (table.month == 6)].iloc[0]
        self.assertEqual(june_2022.source, 'viirs')
        self.assertEqual(june_2022.harmonized, 3)
        self.assertAlmostEqual(june_2022.modis_scaled, 3.0)

    def test_output_has_one_row_per_area_month_and_spec_columns(self):
        rows = [det('2022-06-01'), det('2022-06-01', instrument='VIIRS', satellite='N'),
                det('2022-06-01', area='Argentina', lat=-35.0, lon=-60.0),
                det('2022-06-01', area='Argentina', lat=-35.0, lon=-60.0,
                    instrument='VIIRS', satellite='N')]
        table, _ = harmonize(frame(rows))
        self.assertEqual(list(table.columns),
                         ['area', 'year', 'month', 'modis_cell_days', 'viirs_cell_days',
                          'modis_scaled', 'harmonized', 'source', 'factor', 'viirs_gap_days'])
        self.assertFalse(table.duplicated(['area', 'year', 'month']).any())
        self.assertEqual(len(table), 24)  # 2 areas x 12 months



def overlap_year(areas=('Canada', 'Argentina')):
    """2022, every month: MODIS 1 cell-day and VIIRS 3 on the 1st (factor 3) in each area."""
    rows = []
    for area in areas:
        lat = 45.05 if area == 'Canada' else -35.05
        for m in range(1, 13):
            d = f'2022-{m:02d}-01'
            rows.append(det(d, lat=lat, area=area))
            for k in range(3):
                rows.append(det(d, lat=lat + 1 + k, area=area, instrument='VIIRS', satellite='N'))
    return rows


class GapTests(unittest.TestCase):
    def test_viirs_gap_is_left_out_of_fit_and_filled_with_modis(self):
        rows = overlap_year()
        # 5 Aug: MODIS sees 2 cells in Canada, VIIRS records nothing anywhere -> VIIRS gap
        rows += [det('2022-08-05', lat=50.05), det('2022-08-05', lat=51.05)]
        table, fits = harmonize(frame(rows))
        gaps = table.attrs['gaps']
        self.assertEqual(list(zip(gaps.sensor, gaps.date)), [('viirs', pd.Timestamp('2022-08-05'))])
        self.assertAlmostEqual(fits.set_index('area').loc['Canada'].factor, 3.0)  # gap day not in fit
        aug = table[(table.area == 'Canada') & (table.month == 8)].iloc[0]
        self.assertEqual(aug.viirs_cell_days, 3)                 # raw count unchanged
        self.assertAlmostEqual(aug.harmonized, 3 + 2 * 3.0)      # + MODIS x factor on the gap day
        self.assertEqual(aug.source, 'viirs+modis_gap_fill')
        self.assertEqual(aug.viirs_gap_days, 1)
        arg = table[(table.area == 'Argentina') & (table.month == 8)].iloc[0]
        self.assertEqual(arg.harmonized, 3)                      # nothing to fill there
        self.assertEqual(arg.viirs_gap_days, 1)

    def test_quiet_day_for_both_sensors_is_not_a_gap(self):
        table, _ = harmonize(frame(overlap_year()))
        self.assertEqual(len(table.attrs['gaps']), 0)
        self.assertTrue((table.source == 'viirs').all())
        self.assertTrue((table.viirs_gap_days == 0).all())

    def test_gap_detected_with_a_single_area(self):
        rows = overlap_year(areas=('Canada',)) + [det('2022-08-05', lat=50.05)]
        table, _ = harmonize(frame(rows))
        self.assertEqual(list(table.attrs['gaps'].sensor), ['viirs'])

    def test_viirs_in_one_area_means_no_gap(self):
        rows = overlap_year() + [det('2022-08-05', lat=50.05),
                                 det('2022-08-05', lat=-30.05, area='Argentina', instrument='VIIRS', satellite='N')]
        table, _ = harmonize(frame(rows))
        self.assertEqual(len(table.attrs['gaps']), 0)

    def test_modis_gap_is_left_out_of_fit_but_not_filled(self):
        rows = overlap_year()
        # 5 Aug: VIIRS sees 10 cells in Canada, MODIS nothing -> MODIS gap; would skew the fit
        rows += [det('2022-08-05', lat=50.05 + k * 0.2, instrument='VIIRS', satellite='N') for k in range(10)]
        table, fits = harmonize(frame(rows))
        self.assertEqual(list(table.attrs['gaps'].sensor), ['modis'])
        self.assertAlmostEqual(fits.set_index('area').loc['Canada'].factor, 3.0)
        aug = table[(table.area == 'Canada') & (table.month == 8)].iloc[0]
        self.assertEqual(aug.harmonized, 13)                     # VIIRS as recorded
        self.assertEqual(aug.source, 'viirs')


if __name__ == '__main__':
    unittest.main()
