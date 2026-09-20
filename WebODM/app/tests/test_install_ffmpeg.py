import io
import os
import tempfile
import unittest
from unittest.mock import patch

from app.scripts.install_ffmpeg import download_archive


class _Response:
    def __init__(self, status, headers, body):
        self.status = status
        self.headers = headers
        self._body = io.BytesIO(body)

    def read(self, size=-1):
        return self._body.read(size)

    def getcode(self):
        return self.status

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self._body.close()


class DownloadArchiveTests(unittest.TestCase):
    def test_incomplete_response_resumes_from_confirmed_range(self):
        first = _Response(200, {"Content-Length": "6"}, b"abc")
        second = _Response(
            206,
            {"Content-Range": "bytes 3-5/6", "Content-Length": "3"},
            b"def",
        )

        with tempfile.TemporaryDirectory() as directory:
            destination = os.path.join(directory, "ffmpeg.zip")
            with patch(
                "app.scripts.install_ffmpeg.urllib.request.urlopen",
                side_effect=[first, second],
            ) as open_url:
                download_archive("https://example.test/ffmpeg.zip", destination, chunk_size=3)

            self.assertEqual(open_url.call_count, 2)
            self.assertEqual(open_url.call_args_list[0].args[0].get_header("Range"), "bytes=0-2")
            self.assertEqual(open_url.call_args_list[1].args[0].get_header("Range"), "bytes=3-5")
            with open(destination, "rb") as archive:
                self.assertEqual(archive.read(), b"abcdef")

    def test_server_ignoring_range_restarts_instead_of_appending(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = os.path.join(directory, "ffmpeg.zip")
            with open(destination, "wb") as partial:
                partial.write(b"old")
            response = _Response(200, {"Content-Length": "4"}, b"new!")
            with patch("app.scripts.install_ffmpeg.urllib.request.urlopen", return_value=response):
                download_archive("https://example.test/ffmpeg.zip", destination)

            with open(destination, "rb") as archive:
                self.assertEqual(archive.read(), b"new!")
