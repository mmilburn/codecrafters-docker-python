import json
import os
import platform
import random
import subprocess
import sys
import time
from pathlib import Path
from shutil import unpack_archive
from tempfile import TemporaryDirectory
from typing import List, Tuple
from urllib.error import HTTPError
from urllib.request import urlopen, Request


def get_goos_goarch():
    # Get OS name (similar to $GOOS)
    os_name = os.getenv("GOOS") or platform.system().lower()
    if os_name == "darwin":
        os_name = "darwin"
    elif os_name == "windows":
        os_name = "windows"
    elif os_name.startswith("linux"):
        os_name = "linux"

    # Get architecture (similar to $GOARCH)
    arch = os.getenv("GOARCH") or platform.machine().lower()
    if arch in {"x86_64", "amd64"}:
        arch = "amd64"  # Standard name for 64-bit x86
    elif arch in {"i386", "i686"}:
        arch = "386"  # Standard name for 32-bit x86
    elif arch.startswith("arm") and "64" in arch:
        arch = "arm64"
    elif arch.startswith("arm"):
        arch = "arm"

    return os_name, arch


def backoff_with_jitter(request: Request, base_delay=1, backoff_factor=2, max_retries=5, max_delay=8, jitter=True):
    for attempt in range(1, max_retries + 1):
        try:
            with urlopen(request) as response:
                return response.read()
        except HTTPError as e:
            print(f"{e.code} - {e.reason} for {e.url}", file=sys.stderr)
            print(e.headers.items(), file=sys.stderr)
            print(e.read().decode(), file=sys.stderr)
            # 400 really shouldn't be in this list.
            # We run into an issue when making the request in ingest_layer which will fail on one request, but succeed
            # on the next, despite the fact that we have changed nothing in our request. Something seems to be awry with
            # the s3 compatible storage config on Cloudflare. The output from the print statements above for a
            # "bad request" looks like this:
            # 400 - Bad Request for https://docker-images-prod.6aa30f8b08e16409b46e0173d6de2f56.r2.cloudflarestorage.com/registry-v2/docker/registry/v2/blobs/sha256/1f/1f3e46996e2966e4faa5846e56e76e3748b7315e2ded61476c24403d592134f0/data?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=f1baa2dd9b876aeb89efebbfc9e5d5f4%2F20250211%2Fauto%2Fs3%2Faws4_request&X-Amz-Date=20250211T171618Z&X-Amz-Expires=1200&X-Amz-SignedHeaders=host&X-Amz-Signature=7c6a6e4d392255fc7df6d5d2219dce21604c6b8a8e6f8ba1abcb569c47e4e50a
            # [('Date', 'Tue, 11 Feb 2025 17:16:18 GMT'), ('Content-Type', 'application/xml'), ('Content-Length', '127'), ('Connection', 'close'), ('Vary', 'Accept-Encoding'), ('Server', 'cloudflare'), ('CF-RAY', '9105fc659d2081eb-IAD')]
            # <?xml version="1.0" encoding="UTF-8"?><Error><Code>InvalidRequest</Code><Message>Missing x-amz-content-sha256</Message></Error>
            # When we set x-amz-content-sha256 to "UNSIGNED-PAYLOAD" or
            # "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855" (sha256 of an empty string) we get
            # errors about x-amz-date not being set. While we could set these things, I doubt it will solve the problem.
            # If I understand correctly, these headers / request parameters are being set by an intermediate redirect,
            # so we shouldn't have to set them ourselves anyway...
            if e.code not in [400, 502, 503, 504]:
                return
        delay = min(base_delay * (backoff_factor ** (attempt - 1)), max_delay)
        if jitter:
            delay *= random.uniform(0.8, 1.2)
        if attempt == max_retries:
            print("Max retries reached. Operation failed.", file=sys.stderr)
            return
        print(f"retrying after delay of {delay}s", file=sys.stderr)
        time.sleep(delay)
    return


def get_token(image: str) -> str:
    resp_content = backoff_with_jitter(Request(
        f"https://auth.docker.io/token?service=registry.docker.io&scope=repository:library/{image}:pull",
        method="GET")
    )
    return json.loads(resp_content.decode())["token"]


def get_digests(image: str, tag: str, token: str) -> List[Tuple[str, str]]:
    os_name, arch = get_goos_goarch()
    resp_content = backoff_with_jitter(Request(
        f"https://registry.hub.docker.com/v2/library/{image}/manifests/{tag}",
        method="GET",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.docker.distribution.manifest.v2+json",
        },
    ))
    manifest_list = json.loads(resp_content.decode())
    # Work with newer manifests (manifest lists) that enumerate manifests for multiple platforms.
    if "manifests" in manifest_list:
        digest = ""
        for manifest in manifest_list["manifests"]:
            if manifest["platform"]["architecture"] == arch and manifest["platform"]["os"] == os_name:
                digest = manifest["digest"]
                break

        resp_content = backoff_with_jitter(Request(
            f"https://registry.hub.docker.com/v2/library/{image}/manifests/{digest}",
            method="GET",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.docker.distribution.manifest.v2+json",
            },
        ))
    layers = json.loads(resp_content.decode())["layers"]
    return [(layer["digest"], layer["mediaType"]) for layer in layers]


def ingest_layer(image: str, digest: Tuple[str, str], path: Path, token: str) -> None:
    req = Request(
        f"https://registry.hub.docker.com/v2/library/{image}/blobs/{digest[0]}",
        method="GET",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": digest[1],
        },
    )
    resp_content = backoff_with_jitter(req)
    if resp_content:
        file_path = path / (digest[0].replace("sha256:", "") + ".tar.gz")
        file_path.write_bytes(resp_content)
        unpack_archive(file_path, path)
        file_path.unlink()

"""
NOTICE: The docker challenge is deprecated.
https://forum.codecrafters.io/t/docker-challenge-is-deprecated/626
"""
def main():
    command = sys.argv[3]
    args = sys.argv[4:]
    if ":" in sys.argv[2]:
        image, tag = sys.argv[2].split(":")
    else:
        image, tag = sys.argv[2], "latest"
    with TemporaryDirectory() as temp_dir:
        # copy(command, temp_dir)
        token = get_token(image)
        if token:
            digests = get_digests(image, tag, token)
            for digest in digests:
                ingest_layer(image, digest, Path(temp_dir), token)
        os.chroot(temp_dir)
        # root = Path("/")
        # command = root / Path(command).name
        os.unshare(os.CLONE_NEWPID)
        completed_process = subprocess.run([command, *args], capture_output=True)
        print(completed_process.stdout.decode(), end="")
        print(completed_process.stderr.decode(), file=sys.stderr, end="")
        exit(completed_process.returncode)


if __name__ == "__main__":
    main()
