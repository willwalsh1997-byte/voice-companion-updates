import contextlib
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import fetch_espeak_source
from fetch_espeak_source import KEY, fetch
from r2_storage import MemoryStore, MissingSetup

GOOD = b'the verified eSpeak source'
BUCKET = 'https://updates.example.org/' + KEY


class Body:
    def __init__(self, data): self.data = data
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def read(self, size=-1):
        part, self.data = (self.data, b'') if size < 0 else (self.data[:size], self.data[size:])
        return part


class FetchEspeakSourceTests(unittest.TestCase):
    """The GPL source ships with every release. It moves from the old account's v0.2.77-test
    release to the update bucket, and the checksum is checked wherever it comes from."""
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root/'update-settings.json').write_text(json.dumps({'manifest_url': 'https://updates.example.org/voice-companion-update.json'}))
        self.target = self.root/'espeak'/'espeak-ng-1.52.0-source.tar.gz'
        self.sites = {}; self.requests = []
        self.store = MemoryStore()
        patcher = patch.object(fetch_espeak_source, 'SHA256', hashlib.sha256(GOOD).hexdigest())
        patcher.start(); self.addCleanup(patcher.stop)

    def opener(self, request, timeout=None):
        self.requests.append(request.full_url)
        if request.full_url not in self.sites: raise OSError('HTTP Error 404: Not Found')
        return Body(self.sites[request.full_url])

    def run_fetch(self, store=True):
        factory = (lambda environ: self.store) if store else (lambda environ: (_ for _ in ()).throw(MissingSetup('missing')))
        with contextlib.redirect_stdout(io.StringIO()):
            return fetch(self.target, self.root, self.opener, factory, {})

    def test_the_bucket_copy_is_used_first_and_not_stored_again(self):
        self.sites[BUCKET] = GOOD
        self.assertEqual(self.run_fetch(), BUCKET)
        self.assertEqual(self.target.read_bytes(), GOOD)
        self.assertEqual(self.requests, [BUCKET])
        self.assertEqual(self.store.log, [])

    def test_the_old_release_is_checked_and_stored_in_the_bucket(self):
        old = fetch_espeak_source.OLD_ADDRESSES[0]
        self.sites[old] = GOOD
        self.assertEqual(self.run_fetch(), old)
        self.assertEqual(self.target.read_bytes(), GOOD)
        self.assertEqual(self.store.objects[KEY], GOOD)

    def test_a_changed_file_is_never_used(self):
        self.sites[BUCKET] = b'something else'
        self.sites[fetch_espeak_source.OLD_ADDRESSES[1]] = GOOD
        self.assertEqual(self.run_fetch(), fetch_espeak_source.OLD_ADDRESSES[1])
        self.assertEqual(self.target.read_bytes(), GOOD)

    def test_nothing_verified_names_every_address(self):
        self.sites[BUCKET] = b'something else'
        with self.assertRaises(RuntimeError) as caught: self.run_fetch()
        self.assertFalse(self.target.exists())
        message = str(caught.exception)
        self.assertIn('checksum differs', message)
        for address in fetch_espeak_source.OLD_ADDRESSES: self.assertIn(address, message)

    def test_a_build_without_the_secrets_still_gets_the_source(self):
        old = fetch_espeak_source.OLD_ADDRESSES[0]
        self.sites[old] = GOOD
        self.assertEqual(self.run_fetch(store=False), old)
        self.assertEqual(self.target.read_bytes(), GOOD)

    def test_the_real_checksum_is_the_verified_one(self):
        patch.stopall()
        self.assertEqual(fetch_espeak_source.SHA256, 'bb4338102ff3b49a81423da8a1a158b420124b055b60fa76cfb4b18677130a23')
        workflow = (Path(__file__).parent.parent/'.github'/'workflows'/'windows-installer.yml').read_text()
        self.assertIn(fetch_espeak_source.SHA256, workflow)


if __name__ == '__main__':
    unittest.main()
