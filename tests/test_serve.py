"""T-05: python -m src.serve serves the web front end locally."""
import json
import re
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from src import web_data
from src.serve import WEB, make_server
from tests.test_web_data import write_year

JS_FILES = ['main.js', 'state.js', 'calendar.js', 'globe.js', 'timeline.js', 'theme.js', 'nav.js', 'monthly.js']


class ServeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        data = Path(cls.tmp.name)
        write_year(data, 'Canada', 2022, peak=7, lat=55.0, lon=-110.0)
        web_data.build(data, verbose=False)
        cls.server = make_server(0, generated=web_data.web_dir(data))
        cls.base = f'http://127.0.0.1:{cls.server.server_address[1]}'
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.empty_tmp = tempfile.TemporaryDirectory()
        cls.empty = make_server(0, generated=Path(cls.empty_tmp.name))
        threading.Thread(target=cls.empty.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        for server in (cls.server, cls.empty):
            server.shutdown()
            server.server_close()
        cls.tmp.cleanup()
        cls.empty_tmp.cleanup()

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

    def test_data_comes_from_the_build(self):
        status, ctype, body = self.get('/data/archive.json')
        self.assertIn('json', ctype)
        archive = json.loads(body)
        self.assertEqual({d[:4] for d in archive}, {'2022'})
        self.assertEqual(archive['2022-07-15']['Canada']['total'], 21)
        _, _, body = self.get('/data/monthly.json')
        self.assertIn('Canada', json.loads(body)['areas'])

    def test_before_first_build_data_says_no_data(self):
        port = self.empty.server_address[1]
        with urllib.request.urlopen(f'http://127.0.0.1:{port}/data/monthly.json', timeout=5) as r:
            self.assertEqual(json.loads(r.read())['status'], 'no_data')
        with urllib.request.urlopen(f'http://127.0.0.1:{port}/data/archive.json', timeout=5) as r:
            self.assertEqual(json.loads(r.read()), {})

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
        for rel in ('vendor/d3.min.js', 'vendor/D3-LICENSE.txt', 'data/land.geojson',
                    'data/no-data/archive.json', 'data/no-data/monthly.json'):
            self.assertTrue((WEB / rel).is_file(), rel)

    def test_prototype_and_demo_features_are_gone(self):
        html = (WEB / 'index.html').read_text(encoding='utf-8')
        js = ''.join(p.read_text(encoding='utf-8') for p in (WEB / 'js').glob('*.js'))
        for marker in ('ticker', 'live-mode', 'show-reports', 'geolocation', 'Your demo reports'):
            self.assertNotIn(marker.lower(), (html + js).lower(), marker)
        page_text = re.sub(r'<!--.*?-->|<script.*?</script>|<[^>]+>', ' ', html, flags=re.S).lower()
        for word in ('prototype', 'simulated', 'demo'):   # nothing on screen says it is a mock-up
            self.assertNotIn(word, page_text, word)


if __name__ == '__main__':
    unittest.main()
