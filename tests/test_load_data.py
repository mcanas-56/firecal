import tempfile
import unittest
from pathlib import Path

import pandas as pd

from src.load_data import load_hotspots


class LoadHotspotsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def write(self, rows, name='modis_2022_Canada.csv'):
        path = Path(self.tmp.name) / name
        pd.DataFrame(rows).to_csv(path, index=False)
        return path

    def row(self, **changes):
        return dict(latitude=45, longitude=-75, acq_date='2022-06-01',
                    instrument='MODIS', confidence='30', type=0, **changes)

    def test_confidence_boundaries_and_both_sensors(self):
        rows = []
        for sensor, values in [('MODIS', ['0','29','30','79','80','100','101',None]),
                               ('VIIRS', ['l','n','h',' N ','unknown',None])]:
            for value in values:
                row = self.row()
                row.update(instrument=sensor, confidence=value)
                rows.append(row)
        result = load_hotspots(self.write(rows), verbose=False)
        self.assertEqual(result.confidence.tolist(), ['30','79','80','100','n','h','n'])
        self.assertEqual(set(result.area), {'Canada'})
        self.assertTrue(pd.api.types.is_datetime64_any_dtype(result.acq_date))

    def test_invalid_rows_and_exclusive_counts(self):
        rows = [self.row()]
        for changes in [dict(latitude=None), dict(longitude=181), dict(latitude=float('inf')),
                        dict(acq_date='2022-02-30'), dict(acq_date=None),
                        dict(type=2), dict(type=None), dict(instrument='OTHER'),
                        dict(latitude=91, confidence='0')]:
            row = self.row()
            row.update(changes)
            rows.append(row)
        result = load_hotspots(self.write(rows), verbose=False)
        self.assertEqual(len(result), 1)
        report = result.attrs['cleaning_reports'][0]
        self.assertEqual(report['dropped_rows'], 9)
        self.assertEqual(sum(report['drop_reasons'].values()), 9)
        self.assertEqual(report['drop_reasons']['invalid_coordinates'], 4)

    def test_multiple_files_and_empty_result(self):
        a = self.write([self.row()])
        row = self.row()
        row.update(instrument='VIIRS', confidence='l')
        b = self.write([row], 'viirs-snpp_2023_Argentina.csv')
        result = load_hotspots([a,b], verbose=False)
        self.assertEqual(len(result), 1)
        self.assertEqual(len(result.attrs['cleaning_reports']), 2)
        empty = load_hotspots(b, verbose=False)
        self.assertTrue(empty.empty)
        self.assertIn('source_file', empty.columns)

    def test_missing_schema_and_arguments(self):
        with self.assertRaisesRegex(ValueError, 'missing required columns'):
            load_hotspots(self.write([{'latitude': 45}]), verbose=False)
        with self.assertRaises(ValueError):
            load_hotspots([], verbose=False)
        with self.assertRaises(ValueError):
            load_hotspots([], min_modis_confidence=101, verbose=False)


if __name__ == '__main__':
    unittest.main()
