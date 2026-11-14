"""T-05: python -m src.serve serves the web front end locally."""
import json
import re
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from src.serve import WEB, make_server

JS_FILES = ['main.js', 'state.js', 'calendar.js', 'globe.js', 'timeline.js', 'theme.js', 'nav.js']


class ServeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = make_server(0)
        cls.base = f'http://127.0.0.1:{cls.server.server_address[1]}'
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def get(self, path):
        with urllib.request.urlopen(self.base + path, timeout=5) as r:
            return r.status, r.headers.get('Content-Type', ''), r.read()

    def test_index_page(self):
        status, ctype, body = self.get('/')
        self.assertEqual(status, 200)
        self.assertIn('text/html', ctype)
        self.assertIn(b'Fire activity calendar', body)

    def test_scripts_are_served_as_javascript(self):
        for name in JS_FILES:
            status, ctype, _ = self.get(f'/js/{name}')
            self.assertEqual(status, 200, name)
            self.assertIn('javascript', ctype, name)

    def test_archive_has_the_prototype_format(self):
        status, ctype, body = self.get('/data/archive.json')
        self.assertIn('json', ctype)
        archive = json.loads(body)
        self.assertEqual({d[:4] for d in archive}, {'2022', '2023'})
        day = archive['2023-07-01']['Canada']
        self.assertEqual(set(day), {'total', 'frp', 'points'})
        self.assertEqual(len(day['points'][0]), 3)  # [lat, lon, frp]

    def test_missing_file_is_404_and_parent_folders_are_not_served(self):
        for path in ('/nope.html', '/../src/serve.py', '/%2e%2e/src/serve.py'):
            with self.assertRaises(urllib.error.HTTPError) as cm:
                self.get(path)
            self.assertEqual(cm.exception.code, 404, path)

    def test_listens_on_localhost_only(self):
        self.assertEqual(self.server.server_address[0], '127.0.0.1')

    def test_next_port_when_taken(self):
        port = self.server.server_address[1]
        other = make_server(port)
        try:
            self.assertNotEqual(other.server_address[1], port)
        finally:
            other.server_close()


class OfflineTests(unittest.TestCase):
    def test_only_external_request_is_web_fonts(self):
        urls = set()
        for path in [WEB / 'index.html', WEB / 'styles.css', *(WEB / 'js').glob('*.js')]:
            urls |= set(re.findall(r'https?://[^\s"\')]+', path.read_text(encoding='utf-8')))
        hosts = {re.match(r'https?://([^/]+)', u).group(1) for u in urls}
        self.assertLessEqual(hosts, {'fonts.googleapis.com', 'fonts.gstatic.com'})

    def test_bundled_assets_exist(self):
        for rel in ('vendor/d3.min.js', 'vendor/D3-LICENSE.txt', 'data/land.geojson', 'data/archive.json'):
            self.assertTrue((WEB / rel).is_file(), rel)

    def test_left_out_prototype_features_are_gone(self):
        html = (WEB / 'index.html').read_text(encoding='utf-8')
        js = ''.join(p.read_text(encoding='utf-8') for p in (WEB / 'js').glob('*.js'))
        for marker in ('ticker', 'live-mode', 'show-reports', 'geolocation', 'Your demo reports'):
            self.assertNotIn(marker, html + js, marker)


if __name__ == '__main__':
    unittest.main()
