#!/usr/bin/env python3
"""Download an immutable public candidate; never execute its code or stop services.

Verifies LFS SHA256 and Git blob SHA1, including existing files. No implicit HF
credentials. Writes only beneath the requested new/staging directory. Interrupted
files have .partial suffix and are not mistaken for verified artifacts.
"""
import argparse
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import time
import urllib.request


def safe_path(root, name):
    relative = PurePosixPath(name)
    if relative.is_absolute() or any(p in ('..', '.') for p in relative.parts):
        raise ValueError('Unsafe repository path')
    path = root.joinpath(*relative.parts)
    if root.resolve() not in path.resolve().parents or path.is_symlink():
        raise ValueError('Path escapes staging directory')
    return path


def digest_file(path, row):
    lfs = row.get('lfs')
    digest = hashlib.sha256() if lfs else hashlib.sha1()
    if not lfs:
        digest.update(f"blob {row['size']}\0".encode())
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            digest.update(block)
    expected = lfs['sha256'] if lfs else row['blobId']
    return path.stat().st_size == row['size'] and digest.hexdigest() == expected


def stage_file(root, row, repository, revision):
    path = safe_path(root, row['rfilename'])
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if not digest_file(path, row):
            raise ValueError(f"Existing artifact has wrong digest: {row['rfilename']}")
        return {'file': row['rfilename'], 'bytes': row['size'], 'status': 'verified_existing'}
    partial = path.with_name(path.name + '.partial')
    if partial.is_symlink():
        raise ValueError('Refusing symlink partial')
    url = f'https://huggingface.co/{repository}/resolve/{revision}/{row["rfilename"]}'
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=120) as response, partial.open('wb') as out:
                shutil.copyfileobj(response, out, 8 * 1024 * 1024)
                out.flush()
                os.fsync(out.fileno())
            if not digest_file(partial, row):
                raise ValueError('Downloaded artifact digest mismatch')
            partial.replace(path)
            return {'file': row['rfilename'], 'bytes': row['size'], 'status': 'downloaded_verified'}
        except (OSError, ValueError):
            if attempt == 2:
                raise
            time.sleep(2)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destination', type=Path, required=True)
    parser.add_argument('--metadata-only', action='store_true', help='Download recipe/configuration, not model tensors')
    args = parser.parse_args()
    manifest = json.loads(Path(__file__).with_name('candidate.json').read_text())
    root = args.destination.resolve()
    if root == Path.home() or root == Path('/') or len(root.parts) < 4:
        parser.error('Use a dedicated staging directory')
    root.mkdir(parents=True, exist_ok=True)
    url = f'https://huggingface.co/api/models/{manifest["repository"]}/revision/{manifest["revision"]}?blobs=true'
    with urllib.request.urlopen(url, timeout=60) as response:
        metadata = json.load(response)
    if metadata['sha'] != manifest['revision']:
        raise ValueError('Revision mismatch')
    rows = metadata['siblings']
    if sum(row['size'] for row in rows) != manifest['expected_download_bytes']:
        raise ValueError('Unexpected repository size')
    if args.metadata_only:
        rows = [row for row in rows if not row['rfilename'].startswith('tensors/')]
    needed = sum(row['size'] for row in rows if not safe_path(root, row['rfilename']).exists())
    if shutil.disk_usage(root).free < needed + 20 * 2**30:
        raise ValueError('Insufficient staging space plus 20 GiB reserve')
    print(json.dumps({'revision': manifest['revision'], 'files': len(rows), 'download_bytes': needed}), flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(stage_file, root, row, manifest['repository'], manifest['revision']) for row in rows]
        for future in concurrent.futures.as_completed(futures):
            print(json.dumps(future.result()), flush=True)
    receipt = {'revision': manifest['revision'], 'image': manifest['image'],
               'metadata_only': args.metadata_only, 'files': rows, 'verified_at_unix': time.time()}
    receipt_path = root / 'prime-stage-receipt.json'
    if receipt_path.is_symlink():
        raise ValueError('Refusing receipt symlink')
    receipt_path.write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps({'status': 'verified', 'metadata_only': args.metadata_only}), flush=True)


if __name__ == '__main__':
    main()
