"""The public site is web/ plus the data our pipeline builds, as plain files."""
import json
import re
import tempfile
import unittest
from pathlib import Path

from src.build_site import build_site
from src.serve import WEB
from tests.test_web_data import write_year


class BuildSiteTests(unittest.TestCase):
    def test_site_has_page_assets_and_built_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            data, out = Path(tmp) / 'data', Path(tmp) / 'site'
            data.mkdir()
            write_year(data, 'Canada', 2022, peak=7, lat=55.0, lon=-110.0)
            report = build_site(out, data, verbose=False)
            for rel in ('index.html', 'styles.css', 'js/main.js', 'vendor/d3.min.js',
                        'data/land.geojson', 'data/archive.json', 'data/monthly.json', 'data/outlook.json', '.nojekyll'):
                self.assertTrue((out / rel).is_file(), rel)
            self.assertFalse((out / 'data' / 'no-data').exists())
            monthly = json.loads((out / 'data' / 'monthly.json').read_text())
            self.assertEqual(list(monthly['areas']), ['Canada'])
            self.assertEqual(report['years'], '2022-2022')

    def test_page_uses_relative_paths_so_it_works_under_firecal(self):
        # GitHub Pages serves the site at /firecal/, so nothing may start with "/".
        html = (WEB / 'index.html').read_text(encoding='utf-8')
        js = ''.join(p.read_text(encoding='utf-8') for p in (WEB / 'js').glob('*.js'))
        self.assertEqual(re.findall(r'(?:src|href)="/(?!/)', html), [])
        self.assertEqual(re.findall(r"fetch\(['\"]/", js), [])
        self.assertEqual(re.findall(r"loadJSON\(['\"]/", js), [])

    def test_no_data_is_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FileNotFoundError):
                build_site(Path(tmp) / 'site', Path(tmp), verbose=False)


if __name__ == '__main__':
    unittest.main()
