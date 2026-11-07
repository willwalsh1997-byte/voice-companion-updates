"""Get the eSpeak NG 1.52.0 source that ships with every release, and check its checksum.

The GPL asks that the source goes out with the eSpeak program. The verified copy is kept in
the update bucket (Cloudflare R2) at third-party/<name>. It used to be on the old GitHub
account's v0.2.77-test release. When the bucket does not have it yet, it is fetched from the
older addresses, checked, and, when the R2 secrets are there, stored in the bucket for next time.

Usage: python fetch_espeak_source.py <output file>
"""
import hashlib
import os
import shutil
import sys
import tempfile
import urllib.request
from pathlib import Path

NAME = 'espeak-ng-1.52.0-source.tar.gz'
KEY = 'third-party/' + NAME
SHA256 = 'bb4338102ff3b49a81423da8a1a158b420124b055b60fa76cfb4b18677130a23'
LIMIT = 100 * 1024 * 1024
OLD_ADDRESSES = (
    'https://github.com/willwalsh14-hub/voice-companion-updates/releases/download/v0.2.77-test/' + NAME,
    'https://github.com/willwalsh14-hub/voice-companion-releases/releases/latest/download/' + NAME,
    'https://github.com/willwalsh14-hub/voice-companion-updates/releases/latest/download/' + NAME,
    # eSpeak NG's own source downloads for the 1.52.0 tag. Used only if their bytes match.
    'https://github.com/espeak-ng/espeak-ng/archive/refs/tags/1.52.0.tar.gz',
    'https://codeload.github.com/espeak-ng/espeak-ng/tar.gz/refs/tags/1.52.0',
    'https://github.com/espeak-ng/espeak-ng/releases/download/1.52.0/espeak-ng-1.52.0.tar.gz',
)


def bucket_address(root=Path(__file__).parent):
    from publish_release import public_base
    return public_base(root) + KEY


def download(url, target, opener=urllib.request.urlopen):
    request = urllib.request.Request(url, headers={'User-Agent': 'VoiceCompanion-Build/1'})
    digest, size = hashlib.sha256(), 0
    with opener(request, timeout=60) as response, open(target, 'wb') as output:
        while True:
            block = response.read(1024 * 1024)
            if not block:
                break
            size += len(block)
            if size > LIMIT:
                raise ValueError('larger than any eSpeak source')
            digest.update(block)
            output.write(block)
    return digest.hexdigest()


def annotate(level, title, message):
    if os.environ.get('GITHUB_ACTIONS') == 'true':
        clean = str(message).replace('%', '%25').replace('\r', '').replace('\n', '%0A')
        print('::' + level + ' title=' + title + '::' + clean, flush=True)


def fetch(target, root=Path(__file__).parent, opener=urllib.request.urlopen, store_factory=None, environ=os.environ):
    """Write the verified source to target. Returns the address it came from."""
    target = Path(target)
    problems = []
    addresses = []
    try:
        addresses.append(bucket_address(root))
    except Exception as exc:
        problems.append('update bucket address: ' + str(exc))
    addresses.extend(OLD_ADDRESSES)
    for address in addresses:
        with tempfile.TemporaryDirectory() as folder:
            part = Path(folder) / NAME
            try:
                digest = download(address, part, opener)
            except Exception as exc:
                problems.append(address + ': ' + str(exc))
                continue
            if digest != SHA256:
                problems.append(address + ': the checksum differs from the verified source (it is ' + digest + ')')
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(part), str(target))
        print('eSpeak source verified from ' + address + '.', flush=True)
        if address != addresses[0] or problems:
            keep_in_bucket(target, store_factory, environ)
        return address
    raise RuntimeError('The verified eSpeak source could not be found. Tried:\n' + '\n'.join(problems))


def keep_in_bucket(path, store_factory=None, environ=os.environ):
    """Store the verified source in the bucket, so builds stop needing the old account."""
    from r2_storage import FOREVER, MissingSetup, R2Store
    try:
        store = (store_factory or R2Store.from_environment)(environ)
        store.upload(path, KEY, cache_control=FOREVER)
        if store.sha256(KEY) != SHA256:
            raise ValueError('the stored copy did not pass verification')
    except MissingSetup as exc:
        print('The eSpeak source was not stored in the update bucket: ' + str(exc), flush=True)
        return False
    except Exception as exc:
        print('The eSpeak source was not stored in the update bucket: ' + str(exc), flush=True)
        annotate('warning', 'eSpeak source not stored in the update bucket', str(exc))
        return False
    print('The eSpeak source is now stored in the update bucket at ' + KEY + '.', flush=True)
    annotate('notice', 'eSpeak source stored in the update bucket', KEY)
    return True


def main(argv=sys.argv[1:]):
    if len(argv) != 1:
        print(__doc__)
        return 2
    try:
        fetch(argv[0])
    except Exception as exc:
        print(str(exc), file=sys.stderr, flush=True)
        annotate('error', 'eSpeak source missing', exc)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
