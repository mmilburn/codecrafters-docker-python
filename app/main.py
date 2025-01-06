import json
import os
import platform
import subprocess
import sys
from pathlib import Path
from shutil import unpack_archive
from tempfile import TemporaryDirectory
from typing import List, Tuple
from urllib import request


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


def get_token(image: str) -> str:
    response = request.urlopen(request.Request(
        f"https://auth.docker.io/token?service=registry.docker.io&scope=repository:library/{image}:pull",
        method="GET")
    )
    return json.loads(response.read().decode())["token"]


def get_digests(image: str, tag: str, token: str) -> List[Tuple[str, str]]:
    os_name, arch = get_goos_goarch()
    response = request.urlopen(request.Request(
        f"https://registry.hub.docker.com/v2/library/{image}/manifests/{tag}",
        method="GET",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.docker.distribution.manifest.v2+json",
        },
    ))
    manifest_list = json.loads(response.read().decode())
    # Work with newer manifests (manifest lists) that enumerate manifests for multiple platforms.
    if "manifests" in manifest_list:
        digest = ""
        for manifest in manifest_list["manifests"]:
            if manifest["platform"]["architecture"] == arch and manifest["platform"]["os"] == os_name:
                digest = manifest["digest"]

        response = request.urlopen(request.Request(
            f"https://registry.hub.docker.com/v2/library/{image}/manifests/{digest}",
            method="GET",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.docker.distribution.manifest.v2+json",
            },
        ))
    layers = json.loads(response.read().decode())["layers"]
    return [(layer["digest"], layer["mediaType"]) for layer in layers]


def ingest_layer(image: str, digest: Tuple[str, str], dir: Path, token: str) -> None:
    response = request.urlopen(request.Request(
        f"https://registry.hub.docker.com/v2/library/{image}/blobs/{digest[0]}",
        method="GET",
        headers={"Authorization": f"Bearer {token}", "Accept": digest[1]},
    ))
    file_path = dir / (digest[0].replace("sha256:", "") + ".tar.gz")
    file_path.write_bytes(response.read())
    unpack_archive(file_path, dir)
    file_path.unlink()


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
