import platform
import os
import re
import urllib.error
import urllib.request
import zipfile
import tempfile
import shutil
import time


def download_archive(url, zip_path, chunk_size=1024 * 1024, max_retries=5):
    """Fetch confirmed byte ranges, resuming interrupted chunks safely."""
    total_size = None

    while True:
        offset = os.path.getsize(zip_path) if os.path.isfile(zip_path) else 0
        if total_size is not None and offset >= total_size:
            return

        requested_end = offset + chunk_size - 1
        request = urllib.request.Request(
            url, headers={"Range": f"bytes={offset}-{requested_end}"}
        )

        for attempt in range(max_retries):
            try:
                try:
                    response = urllib.request.urlopen(request, timeout=120)
                except urllib.error.HTTPError as error:
                    if error.code == 416 and offset:
                        os.unlink(zip_path)
                        total_size = None
                    raise

                with response:
                    status = getattr(response, "status", None) or response.getcode()
                    if status == 200:
                        # Range is optional at the server. Replace the prefix
                        # with the complete response instead of appending it.
                        mode = "wb"
                        content_length = response.headers.get("Content-Length")
                        response_total = int(content_length) if content_length else None
                        response_end = response_total - 1 if response_total else None
                    elif status == 206:
                        content_range = response.headers.get("Content-Range", "")
                        match = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+|\*)", content_range)
                        if not match:
                            raise IOError("FFmpeg archive returned an invalid Content-Range")
                        start, end, declared_total = match.groups()
                        start, end = int(start), int(end)
                        if start != offset or end < start or end > requested_end:
                            raise IOError("FFmpeg archive returned an unexpected byte range")
                        if declared_total != "*":
                            response_total = int(declared_total)
                            if end >= response_total:
                                raise IOError("FFmpeg archive range exceeds its declared size")
                            if total_size is not None and response_total != total_size:
                                raise IOError("FFmpeg archive size changed during download")
                            total_size = response_total
                        else:
                            response_total = None
                        content_length = response.headers.get("Content-Length")
                        if content_length and int(content_length) != end - start + 1:
                            raise IOError("FFmpeg archive range length does not match its headers")
                        mode = "ab"
                        response_end = end
                    else:
                        raise IOError(f"Unexpected HTTP status for FFmpeg archive: {status}")

                    with open(zip_path, mode) as output:
                        shutil.copyfileobj(response, output, length=chunk_size)

                actual_size = os.path.getsize(zip_path)
                if status == 200:
                    if response_total is not None and actual_size != response_total:
                        raise IOError(
                            f"incomplete FFmpeg archive: received {actual_size} of {response_total} bytes"
                        )
                    if actual_size == 0:
                        raise IOError("FFmpeg archive download was empty")
                    return

                if actual_size != response_end + 1:
                    raise IOError(
                        f"incomplete FFmpeg archive range: received through byte {actual_size - 1}, "
                        f"expected through byte {response_end}"
                    )
                if response_total is None and response_end < requested_end:
                    return
                break
            except Exception:
                if attempt == max_retries - 1:
                    raise
                time.sleep(2 ** attempt)
                offset = os.path.getsize(zip_path) if os.path.isfile(zip_path) else 0
                if total_size is not None and offset >= total_size:
                    return
                requested_end = offset + chunk_size - 1
                request = urllib.request.Request(
                    url, headers={"Range": f"bytes={offset}-{requested_end}"}
                )

def get_ffmpeg():
    ffmpeg_dst = "/usr/bin/ffmpeg"

    if os.path.isfile(ffmpeg_dst):
        print(f"{ffmpeg_dst} already installed")
        return
    
    machine = platform.machine().lower()
    version = "7.0.2"
    url = f"https://github.com/pierotofy/photogrammetry-tools/releases/download/v1.0.0/ffmpeg-{version}-amd64.zip"
    
    if "arm" in machine:
        url = f"https://github.com/pierotofy/photogrammetry-tools/releases/download/v1.0.0/ffmpeg-{version}-arm64.zip"

    max_retries = 5
    with tempfile.TemporaryDirectory() as temp_dir:
        zip_path = os.path.join(temp_dir, "ffmpeg.zip")
        extracted_ffmpeg = os.path.join(temp_dir, "ffmpeg")

        for attempt in range(max_retries):
            try:
                print(f"Downloading ffmpeg from {url} (attempt {attempt + 1}/{max_retries})...")
                download_archive(url, zip_path)

                print("Validating and extracting archive...")
                with zipfile.ZipFile(zip_path, "r") as zip_ref:
                    corrupt_member = zip_ref.testzip()
                    if corrupt_member:
                        raise zipfile.BadZipFile(f"corrupt archive member: {corrupt_member}")
                    try:
                        archive_member = zip_ref.open("ffmpeg")
                    except KeyError as error:
                        raise FileNotFoundError("ffmpeg binary not found in archive") from error
                    with archive_member, open(extracted_ffmpeg, "wb") as output:
                        shutil.copyfileobj(archive_member, output, length=1024 * 1024)

                print("Setting executable permissions...")
                if not os.access(extracted_ffmpeg, os.X_OK):
                    os.chmod(extracted_ffmpeg, 0o755)

                print(f"Moving ffmpeg to {ffmpeg_dst}...")
                shutil.move(extracted_ffmpeg, ffmpeg_dst)

                print("done!")
                return

            except Exception as e:
                print(f"Attempt {attempt + 1} failed: {e}")
                if isinstance(e, zipfile.BadZipFile):
                    # The transfer completed but the archive is invalid, so a
                    # later byte-range retry cannot repair this full-length file.
                    if os.path.exists(zip_path):
                        os.unlink(zip_path)
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    print(f"Retrying in {wait_time} seconds...")
                    time.sleep(wait_time)
                else:
                    raise Exception(f"Failed to install ffmpeg after {max_retries} attempts") from e

if __name__ == "__main__":
    get_ffmpeg()
