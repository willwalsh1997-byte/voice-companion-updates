"""Publish only a checked Windows build to the update bucket (Cloudflare R2).

Run by the GitHub build on main (.github/workflows/windows-installer.yml). Since November 2026
updates come from Cloudflare R2, not GitHub releases. The bucket's public address is in
update-settings.json. In the bucket:

  voice-companion-update.json          the feed every installed copy reads (written last)
  VoiceCompanion-Setup.exe             a copy of the newest installer, for first installs
  releases/v<version>/...              the installer, guides, release notes and eSpeak source
  releases/v<version>/published.json   written once that version is live; it is never replaced

Nothing installed copies read changes until every file is uploaded, checked byte for byte,
and reachable at the public address.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import time
import urllib.parse
import urllib.request
from pathlib import Path
from app_updates import MAX_INSTALLER, https_url, version_key
from guide_files import GUIDE_NAMES, guide_sources, published_name
from release_documents import load_notes, validate, STEM

ROOT = Path(__file__).parent
FEED_NAME = 'voice-companion-update.json'
LATEST_INSTALLER = 'VoiceCompanion-Setup.exe'
USER_AGENT = 'VoiceCompanion-Publisher/2'


def release_manifest(setup, version, installer_url):
    version_key(version); https_url(installer_url)
    setup = Path(setup)
    if not setup.is_file() or setup.suffix.lower() != '.exe': raise ValueError('Choose the finished Setup EXE, not a source ZIP.')
    if not 1 <= setup.stat().st_size <= MAX_INSTALLER: raise ValueError('The installer must be smaller than 2 GiB.')
    with setup.open('rb') as source:
        if source.read(2) != b'MZ': raise ValueError('Choose a Windows Setup EXE.')
        source.seek(0); digest = hashlib.file_digest(source,'sha256').hexdigest()
    return {'schema':1,'version':version,'installer_url':installer_url,'sha256':digest,'size':setup.stat().st_size}


LOG_PATH = None


def progress(message):
    print(message, flush=True)
    if LOG_PATH is not None:
        with Path(LOG_PATH).open('a', encoding='utf-8') as log:
            log.write(time.strftime('%H:%M:%S') + ' ' + message + '\n')


def public_base(root=ROOT):
    """The bucket's public address, from the feed in update-settings.json, ending in '/'."""
    settings = json.loads((Path(root)/'update-settings.json').read_text(encoding='utf-8-sig'))
    feed = https_url(settings['manifest_url'])
    parts = urllib.parse.urlsplit(feed)
    if parts.path != '/' + FEED_NAME or parts.query or 'github.com' in parts.hostname:
        raise ValueError('update-settings.json must name the update bucket feed, https://<address>/' + FEED_NAME + '.')
    return 'https://' + parts.netloc + '/'


def safe_name(name):
    return re.sub('-+', '-', re.sub(r'[^A-Za-z0-9._-]+', '-', name))


def fetch(url, opener, headers=None, limit=65536):
    """GET a public address. Returns (status, headers, up to `limit` bytes of the body)."""
    request = urllib.request.Request(url, headers={'User-Agent': USER_AGENT, 'Cache-Control': 'no-cache', **(headers or {})})
    with opener(request, timeout=30) as response:
        return response.status, response.headers, response.read(limit)


def check_public_installer(url, size, opener):
    """The installer is reachable at its public address, whole, and is a Windows program."""
    try:
        status, headers, start = fetch(url, opener, {'Range': 'bytes=0-1'}, limit=2)
    except Exception as exc:
        raise RuntimeError('The installer cannot be read at its public address ' + url + ' (' + str(exc) +
                           '). Check that the bucket\'s custom domain is connected in Cloudflare.') from exc
    if status == 206:
        total = (headers.get('Content-Range') or '').rpartition('/')[2]
    else:
        total = headers.get('Content-Length') or ''
    if start != b'MZ' or total != str(size):
        raise RuntimeError('The public address ' + url + ' does not serve the uploaded installer.')


def check_public_feed(url, version, opener, attempts=6, wait=10):
    """Installed copies see this version in the feed. Cloudflare can take a moment."""
    seen = 'nothing'
    for attempt in range(attempts):
        try:
            _status, _headers, raw = fetch(url + '?check=' + str(int(time.time())) + str(attempt), opener)
            seen = json.loads(raw).get('version', 'no version')
            if seen == version:
                return
        except Exception as exc:
            seen = str(exc)
        if attempt + 1 < attempts:
            progress('The public feed shows ' + str(seen) + '. Checking again in ' + str(wait) + ' seconds.')
            time.sleep(wait)
    raise RuntimeError('The feed was written, but its public address still shows ' + str(seen) +
                       '. Check the Cloudflare cache rules for ' + url + '.')


def publish(setup, store, root=ROOT, opener=urllib.request.urlopen, wait=10):
    root = Path(root)
    version = re.search(r"APP_VERSION = '([^']+)'", (root/'companion.py').read_text())[1]
    base = public_base(root)
    tag = 'v' + version
    folder = 'releases/' + tag + '/'
    installer_url = base + folder + 'VoiceCompanion-Setup.exe'
    progress('Preparing release '+version+'. Checking the local installer and successful-build record.')
    manifest = release_manifest(setup, version, installer_url)
    receipt = json.loads((root/'VoiceCompanion-Build-Passed.json').read_text(encoding='utf-8-sig'))
    if receipt != {'version':version, 'sha256':manifest['sha256'], 'size':manifest['size']}:
        raise ValueError('This installer does not match the successful Windows build checks. Rebuild it before publishing.')
    load_notes(root)
    validate(root)
    guide_sources([root], expected_version=version)
    documentation = [root/name for name in GUIDE_NAMES]
    if not all(path.is_file() for path in documentation):
        raise ValueError('All manual and release-note formats are required before publishing.')
    source = root/'espeak'/'espeak-ng-1.52.0-source.tar.gz'
    license_path = root/'espeak'/'COPYING'
    if not source.is_file() or not license_path.is_file():
        raise ValueError('The bundled eSpeak source and license are required for distribution.')

    progress('Checking what the update bucket already has.')
    latest = store.read(FEED_NAME)
    if latest:
        latest_version = json.loads(latest)['version']
        if version_key(latest_version) > version_key(version):
            raise ValueError('A newer release ('+latest_version+') is already published. Increase the version before building.')
        if latest_version == version:
            raise ValueError('This version is already published. Published installers are never overwritten; increase the version and rebuild.')
    if store.read(folder + 'published.json') is not None:
        raise ValueError('This version was published before. Published installers are never overwritten; increase the version and rebuild.')

    output = root/'release-upload'; output.mkdir(exist_ok=True)
    installer = output/'VoiceCompanion-Setup.exe'; shutil.copy2(setup, installer)
    manifest_bytes = (json.dumps(manifest, indent=2)+'\n').encode('utf-8')
    manifest_path = output/FEED_NAME
    manifest_path.write_bytes(manifest_bytes)
    notes = output/'release-notes.txt'
    notes.write_text((root/(STEM+'.txt')).read_text(encoding='utf-8'), encoding='utf-8')
    assets = [installer, manifest_path, source, license_path, notes]
    for document in documentation:
        copy = output/safe_name(published_name(document.name, version))
        shutil.copy2(document, copy)
        assets.append(copy)
    # A retry after a failed run uploads the same files again: nothing here is live yet.
    for asset in assets:
        progress(f'Upload file: {asset.name}. Size: {asset.stat().st_size / (1024*1024):.1f} MB.')
        store.upload(asset, folder + asset.name)
    for asset in assets:
        progress('Checking uploaded checksum: '+asset.name+'.')
        with asset.open('rb') as local:
            expected = hashlib.file_digest(local, 'sha256').hexdigest()
        if store.sha256(folder + asset.name) != expected:
            raise ValueError('Uploaded file '+asset.name+' did not pass verification. Nothing was published; retry publishing.')
    progress('Checking the installer at its public address.')
    check_public_installer(installer_url, manifest['size'], opener)

    # The copy for first installs, then the feed. Until the feed changes, nobody is offered it.
    store.copy(folder + 'VoiceCompanion-Setup.exe', LATEST_INSTALLER)
    if store.sha256(LATEST_INSTALLER) != manifest['sha256']:
        raise ValueError('The newest-installer copy did not pass verification. Nothing was published; retry publishing.')
    progress('Publishing the update feed.')
    store.put(manifest_bytes, FEED_NAME)
    record = {'version':version, 'sha256':manifest['sha256'], 'published':time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}
    store.put(json.dumps(record).encode('utf-8'), folder + 'published.json')
    check_public_feed(base + FEED_NAME, version, opener, wait=wait)

    confirmation = {'version':version, 'sha256':manifest['sha256'], 'url':installer_url}
    temporary = root/'VoiceCompanion-Published.tmp'
    temporary.write_text(json.dumps(confirmation), encoding='utf-8')
    temporary.replace(root/'VoiceCompanion-Published.json')
    return installer_url


def annotate(environ, level, title, message):
    """On GitHub, show the result in the run's annotations, which can be read without the full
    log (CLAUDE.md: every failure must name itself)."""
    if environ.get('GITHUB_ACTIONS') == 'true':
        clean = str(message).replace('%', '%25').replace('\r', '').replace('\n', '%0A')
        print('::' + level + ' title=' + title + '::' + clean, flush=True)


def publish_from_environment(setup, root=ROOT, environ=os.environ, store=None, opener=urllib.request.urlopen):
    from r2_storage import MissingSetup, R2Store
    try:
        store = store or R2Store.from_environment(environ)
        url = publish(setup, store, root, opener)
    except MissingSetup as exc:
        progress('BUILD PASSED, PUBLISHING FAILED: ' + str(exc))
        annotate(environ, 'error', 'Not published', str(exc) + ' Add them in the repository settings, under Secrets and variables, Actions.')
        return 1
    except Exception as exc:
        progress('BUILD PASSED, PUBLISHING FAILED: ' + str(exc))
        progress('Installed copies still see the previous release. Run the GitHub build again to retry.')
        annotate(environ, 'error', 'Not published', str(exc))
        return 1
    progress('PUBLISHED AND VERIFIED: ' + url)
    annotate(environ, 'notice', 'Published', url)
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--setup', required=True)
    args = parser.parse_args()
    global LOG_PATH
    LOG_PATH = ROOT/'VoiceCompanion-Publish-Log.txt'
    LOG_PATH.write_text('Voice Companion publishing progress\n', encoding='utf-8')
    return publish_from_environment(args.setup)


if __name__ == '__main__': raise SystemExit(main())
