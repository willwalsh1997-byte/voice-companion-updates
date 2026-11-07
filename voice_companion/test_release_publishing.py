import contextlib
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import publish_release
from publish_release import publish, publish_from_environment
from r2_storage import MemoryStore, NO_CACHE, FOREVER

BASE = 'https://updates.example.org/'
FOLDER = 'releases/v1.2.3-test/'


class PublicSite:
    """The bucket as installed copies see it over HTTPS: what the store holds, after the
    custom domain. `broken` stands for a custom domain that is not connected."""
    def __init__(self, store):
        self.store = store; self.broken = False; self.stale_feed = None; self.requests = []

    def __call__(self, request, timeout=None):
        url = request.full_url; self.requests.append(url)
        if self.broken: raise OSError('Name or service not known')
        key = url[len(BASE):].split('?')[0]
        if key == 'voice-companion-update.json' and self.stale_feed is not None:
            body = self.stale_feed
        else:
            body = self.store.objects.get(key)
        if body is None: raise OSError('HTTP Error 404: Not Found')
        status, headers = 200, {'Content-Length': str(len(body))}
        if request.get_header('Range') == 'bytes=0-1':
            status, headers = 206, {'Content-Range': 'bytes 0-1/' + str(len(body))}
            body = body[:2]
        return Response(status, headers, body)


class Response:
    def __init__(self, status, headers, body): self.status = status; self.headers = headers; self.body = body
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def read(self, size=-1): return self.body if size < 0 else self.body[:size]


class PublishingTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.setup=self.root/'VoiceCompanion-Setup.exe';self.setup.write_bytes(b'MZtested installer')
        (self.root/'companion.py').write_text("APP_VERSION = '1.2.3-test'\n")
        (self.root/'update-settings.json').write_text(json.dumps({'manifest_url':BASE+'voice-companion-update.json'}))
        (self.root/'VoiceCompanion-Build-Passed.json').write_text(json.dumps({'version':'1.2.3-test','sha256':hashlib.sha256(self.setup.read_bytes()).hexdigest(),'size':self.setup.stat().st_size}),encoding='utf-8-sig')
        (self.root/'espeak').mkdir()
        for name in ('espeak-ng-1.52.0-source.tar.gz','COPYING'): (self.root/'espeak'/name).write_bytes(b'source or license')
        from guide_files import GUIDE_NAMES
        from test_release_documents import fixture
        fixture(self.root)
        for name in GUIDE_NAMES:
            if not (self.root/name).exists():(self.root/name).write_bytes(b'fixture manual')
        from guide_files import write_manifest
        write_manifest(self.root,'1.2.3-test')
        self.store=MemoryStore();self.site=PublicSite(self.store)
        self.output=io.StringIO()

    def run_publish(self):
        with contextlib.redirect_stdout(self.output):
            return publish(self.setup,self.store,root=self.root,opener=self.site,wait=0)

    def feed(self):
        return json.loads(self.store.objects['voice-companion-update.json'])

    def test_complete_release_is_verified_before_the_feed_changes(self):
        url=self.run_publish()
        self.assertEqual(url,BASE+FOLDER+'VoiceCompanion-Setup.exe')
        feed=self.feed()
        self.assertEqual(feed,{'schema':1,'version':'1.2.3-test','installer_url':url,
                               'sha256':hashlib.sha256(self.setup.read_bytes()).hexdigest(),'size':self.setup.stat().st_size})
        log=self.store.log
        feed_write=log.index(('put','voice-companion-update.json'))
        uploads=[key for action,key in log if action=='upload']
        checks=[key for action,key in log[:feed_write] if action=='sha256']
        # Installer, its manifest, eSpeak source, license, notes and every guide (12 files).
        self.assertEqual(len(uploads),17)
        self.assertTrue(all(key.startswith(FOLDER) for key in uploads))
        self.assertTrue(set(uploads)<=set(checks))
        self.assertLess(max(i for i,(a,_k) in enumerate(log) if a=='upload'),feed_write)
        self.assertLess(log.index(('copy','VoiceCompanion-Setup.exe')),feed_write)
        self.assertIn(('put',FOLDER+'published.json'),log[feed_write:])
        # The public installer address was checked before the feed was written.
        self.assertIn(url,self.site.requests)
        self.assertEqual(self.store.cache['voice-companion-update.json'],NO_CACHE)
        self.assertEqual(self.store.cache[FOLDER+'VoiceCompanion-Setup.exe'],FOREVER)
        self.assertEqual(self.store.objects['VoiceCompanion-Setup.exe'],self.setup.read_bytes())
        self.assertEqual(json.loads((self.root/'VoiceCompanion-Published.json').read_text())['url'],url)

    def test_release_document_names_are_portable(self):
        self.run_publish()
        uploads=[key[len(FOLDER):] for action,key in self.store.log if action=='upload']
        self.assertIn('Release-Notes-for-Voice-Companion-1.2.3-test.brf',uploads)
        self.assertIn('START-HERE-Veteran.brf',uploads)
        self.assertIn('espeak-ng-1.52.0-source.tar.gz',uploads)
        self.assertFalse(any(' ' in name for name in uploads))

    def test_a_corrupt_upload_never_reaches_the_feed(self):
        real_upload=self.store.upload
        def corrupt(path,key,cache_control=FOREVER):
            real_upload(path,key,cache_control)
            if key.endswith('.exe'):self.store.objects[key]=b'MZcorrupted'
        self.store.upload=corrupt
        with self.assertRaises(ValueError):self.run_publish()
        self.assertNotIn('voice-companion-update.json',self.store.objects)

    def test_a_failed_upload_never_reaches_the_feed(self):
        def offline(*args,**kwargs):raise OSError('Could not connect to the endpoint URL')
        self.store.upload=offline
        with self.assertRaises(OSError):self.run_publish()
        self.assertNotIn('voice-companion-update.json',self.store.objects)

    def test_an_unreachable_public_address_never_reaches_the_feed(self):
        # The custom domain is not connected to the bucket: copies could not download it.
        self.site.broken=True
        with self.assertRaises(RuntimeError) as caught:self.run_publish()
        self.assertIn('custom domain',str(caught.exception))
        self.assertNotIn('voice-companion-update.json',self.store.objects)

    def test_a_retry_after_a_failure_publishes(self):
        self.site.broken=True
        with self.assertRaises(RuntimeError):self.run_publish()
        self.site.broken=False
        self.run_publish()
        self.assertEqual(self.feed()['version'],'1.2.3-test')

    def test_published_version_or_downgrade_is_never_overwritten(self):
        for feed_version in ('1.2.3-test','1.2.4-test'):
            store=MemoryStore();store.objects['voice-companion-update.json']=json.dumps({'version':feed_version}).encode()
            self.store=store
            with self.assertRaises(ValueError):self.run_publish()
            self.assertFalse(any(action=='upload' for action,_key in store.log))
        # A later release went out, but this version was published before it.
        store=MemoryStore();store.objects['voice-companion-update.json']=json.dumps({'version':'1.2.2-test'}).encode()
        store.objects[FOLDER+'published.json']=b'{}'
        self.store=store
        with self.assertRaises(ValueError):self.run_publish()
        self.assertFalse(any(action=='upload' for action,_key in store.log))

    def test_an_older_published_release_is_replaced_in_the_feed(self):
        self.store.objects['voice-companion-update.json']=json.dumps({'version':'1.2.2-test'}).encode()
        self.run_publish()
        self.assertEqual(self.feed()['version'],'1.2.3-test')

    def test_a_feed_that_stays_old_at_the_public_address_fails_and_names_itself(self):
        self.site.stale_feed=json.dumps({'version':'1.2.2-test'}).encode()
        with self.assertRaises(RuntimeError) as caught:self.run_publish()
        self.assertIn('1.2.2-test',str(caught.exception))
        self.assertIn('cache',str(caught.exception))

    def test_missing_or_mismatched_documentation_is_not_uploaded(self):
        (self.root/'Voice Companion Release Notes.brf').unlink()
        with self.assertRaises(OSError):self.run_publish()
        self.assertEqual(self.store.log,[])

    def test_changed_or_unchecked_installer_is_not_uploaded(self):
        self.setup.write_bytes(b'MZchanged')
        with self.assertRaises(ValueError):self.run_publish()
        self.assertEqual(self.store.log,[])
        (self.root/'VoiceCompanion-Build-Passed.json').unlink()
        with self.assertRaises(OSError):self.run_publish()

    def test_a_github_feed_in_the_settings_is_refused(self):
        (self.root/'update-settings.json').write_text(json.dumps({'manifest_url':'https://github.com/owner/repository/releases/latest/download/voice-companion-update.json'}))
        with self.assertRaises(ValueError):self.run_publish()
        self.assertEqual(self.store.log,[])

    def test_publishing_help_does_not_require_document_authoring_dependencies(self):
        import subprocess,sys
        result=subprocess.run([sys.executable,'-S',str(Path(__file__).parent/'publish_release.py'),'--help'],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_only_the_github_build_publishes(self):
        # Will, November 3, 2026: the old hand publishing tools were removed. A build on
        # your own computer is for testing; the GitHub workflow runs publish_release.py.
        folder=Path(__file__).parent
        script=(folder/'build-windows.ps1').read_text()
        self.assertNotIn('publish-windows.ps1',script)
        self.assertNotIn('publish_release.py',script)
        self.assertIn('Local build only.',script)
        for name in ('update_publisher.py','github_login.py','publish-windows.ps1','PUBLISH UPDATE - Double click.cmd','SET UP UPDATES - Double click.cmd'):
            self.assertFalse((folder/name).exists(),name)
        workflow=(folder.parent/'.github'/'workflows'/'windows-installer.yml').read_text()
        self.assertIn('publish_release.py',workflow)


class PublishFromEnvironmentTests(unittest.TestCase):
    """Every failure names itself in a GitHub annotation (CLAUDE.md)."""
    def run_main(self, environ, store=None, failure=None):
        out=io.StringIO()
        def fake(setup,store,root,opener):
            if failure:raise failure
            return BASE+FOLDER+'VoiceCompanion-Setup.exe'
        with patch.object(publish_release,'publish',side_effect=fake),contextlib.redirect_stdout(out):
            code=publish_from_environment('setup.exe',environ=environ,store=store)
        return code,out.getvalue()

    def test_missing_secrets_are_named(self):
        code,out=self.run_main({'GITHUB_ACTIONS':'true','R2_ACCOUNT_ID':'abc'})
        self.assertEqual(code,1)
        self.assertIn('::error title=Not published::',out)
        self.assertIn('R2_ACCESS_KEY_ID',out);self.assertIn('R2_SECRET_ACCESS_KEY',out)
        self.assertNotIn('R2_ACCOUNT_ID,',out)

    def test_a_failure_and_a_success_are_annotated(self):
        code,out=self.run_main({'GITHUB_ACTIONS':'true'},store=MemoryStore(),failure=RuntimeError('The installer cannot be read'))
        self.assertEqual(code,1);self.assertIn('::error title=Not published::The installer cannot be read',out)
        code,out=self.run_main({'GITHUB_ACTIONS':'true'},store=MemoryStore())
        self.assertEqual(code,0);self.assertIn('::notice title=Published::'+BASE,out)


class ShippedSettingsTests(unittest.TestCase):
    def test_the_shipped_settings_name_the_update_bucket(self):
        # Will, November 7, 2026: updates come from Cloudflare R2 at updates.voicecompanionapp.com.
        self.assertEqual(publish_release.public_base(),'https://updates.voicecompanionapp.com/')
        settings=json.loads((Path(__file__).parent/'update-settings.json').read_text())
        self.assertFalse(settings.get('fallback_urls'))

    def test_the_workflow_publishes_with_the_r2_secrets(self):
        workflow=(Path(__file__).parent.parent/'.github'/'workflows'/'windows-installer.yml').read_text()
        publish=workflow[workflow.index('- name: Publish verified installer'):]
        publish=publish[:publish.index('- name: Tag the published release')]
        for name in ('R2_ACCOUNT_ID','R2_ACCESS_KEY_ID','R2_SECRET_ACCESS_KEY'):
            self.assertIn('secrets.'+name,publish)
        self.assertNotIn('RELEASES_TOKEN',workflow)
        self.assertNotIn('willwalsh14-hub/voice-companion-updates/releases/download',workflow)
        self.assertIn('fetch_espeak_source.py',workflow)


class R2StoreTests(unittest.TestCase):
    """The real S3 client calls, against moto's S3 stand-in when it is installed."""
    def setUp(self):
        try:
            import boto3
            from moto import mock_aws
        except ImportError:
            self.skipTest('boto3 and moto are not installed')
        mock=mock_aws();mock.start();self.addCleanup(mock.stop)
        client=boto3.client('s3',region_name='us-east-1',aws_access_key_id='a',aws_secret_access_key='b')
        client.create_bucket(Bucket='bucket')
        from r2_storage import R2Store
        self.store=R2Store(client,'bucket')

    def test_upload_read_copy_and_checksums(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'VoiceCompanion-Setup.exe';path.write_bytes(b'MZ'+b'x'*1000)
            self.assertIsNone(self.store.read('missing'))
            self.assertIsNone(self.store.size('missing'))
            self.assertIsNone(self.store.sha256('missing'))
            self.store.upload(path,'releases/v1/VoiceCompanion-Setup.exe')
            self.assertEqual(self.store.sha256('releases/v1/VoiceCompanion-Setup.exe'),hashlib.sha256(path.read_bytes()).hexdigest())
            self.assertEqual(self.store.size('releases/v1/VoiceCompanion-Setup.exe'),1002)
            self.store.copy('releases/v1/VoiceCompanion-Setup.exe','VoiceCompanion-Setup.exe')
            head=self.store.client.head_object(Bucket='bucket',Key='VoiceCompanion-Setup.exe')
            self.assertEqual(head['CacheControl'],NO_CACHE)
            self.assertEqual(head['ContentType'],'application/vnd.microsoft.portable-executable')
            self.store.put(b'{"version":"1"}','voice-companion-update.json')
            self.assertEqual(self.store.read('voice-companion-update.json'),b'{"version":"1"}')
            head=self.store.client.head_object(Bucket='bucket',Key='voice-companion-update.json')
            self.assertEqual((head['ContentType'],head['CacheControl']),('application/json',NO_CACHE))

    def test_other_errors_are_not_treated_as_missing(self):
        from r2_storage import R2Store
        import boto3
        client=boto3.client('s3',region_name='us-east-1',aws_access_key_id='a',aws_secret_access_key='b')
        with self.assertRaises(Exception):R2Store(client,'no-such-bucket').read('key')

    def test_the_client_points_at_r2(self):
        from r2_storage import R2Store
        store=R2Store.from_environment({'R2_ACCOUNT_ID':'acct','R2_ACCESS_KEY_ID':'id','R2_SECRET_ACCESS_KEY':'secret'})
        self.assertEqual(store.client.meta.endpoint_url,'https://acct.r2.cloudflarestorage.com')
        self.assertEqual(store.bucket,'voice-companion-updates')
        self.assertEqual(R2Store.from_environment({'R2_ACCOUNT_ID':'a','R2_ACCESS_KEY_ID':'b','R2_SECRET_ACCESS_KEY':'c','R2_BUCKET':'other'}).bucket,'other')


if __name__ == '__main__':
    unittest.main()
