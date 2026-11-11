"""Offline regression checks for the upstream bacloud v30 download merge."""
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from compression import zstd

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))
from bacommon.bacloud import StandardResponseData
from bacommon.cloudfilecodec import CompressionType
from bacommontools.bacloud import App
from efro.error import CleanError


class Response:
    status = 200

    def __init__(self, data):
        self.data = data

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def stream(self, chunk_size):
        # Split frame headers and payloads to exercise incremental decompression.
        for start in range(0, len(self.data), 7):
            yield self.data[start:start + 7]


class DownloadTests(unittest.TestCase):
    def download(self, stored, raw, compression, *, sha=None):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'asset'
            target.write_bytes(b'previous verified content')
            entry = StandardResponseData.SignedDownloadEntry(
                path=str(target), download_url='https://example.invalid/blob',
                sha256=sha or hashlib.sha256(raw).hexdigest(), size=len(raw),
                compression=compression)
            with patch('bacommontools.bacloud._g_pool.request', return_value=Response(stored)):
                try:
                    App.__new__(App)._handle_downloads_signed([entry])
                except CleanError:
                    self.assertEqual(target.read_bytes(), b'previous verified content')
                    self.assertFalse(Path(str(target) + '.tmp').exists())
                    raise
            return target.read_bytes()

    def test_raw_download(self):
        raw = b'raw asset\x00\xff'
        self.assertEqual(self.download(raw, raw, CompressionType.UNCOMPRESSED), raw)

    def test_compressed_download_hashes_decoded_bytes(self):
        raw = bytes(range(256)) * 100
        self.assertEqual(self.download(zstd.compress(raw), raw, CompressionType.ZSTD), raw)

    def test_truncated_frame_preserves_existing_file(self):
        raw = b'compressed asset' * 100
        with self.assertRaises(CleanError):
            self.download(zstd.compress(raw)[:-1], raw, CompressionType.ZSTD)

    def test_bad_hash_preserves_existing_file(self):
        raw = b'compressed asset' * 100
        with self.assertRaises(CleanError):
            self.download(zstd.compress(raw), raw, CompressionType.ZSTD, sha='0' * 64)

    def test_unsupported_dictionary_encoding_is_rejected(self):
        with self.assertRaises(CleanError):
            self.download(b'unsupported', b'expected', CompressionType.ZSTD_DICT_BOB_V1)


if __name__ == '__main__':
    unittest.main()
