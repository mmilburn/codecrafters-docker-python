import os
import subprocess
import sys
from shutil import copy
from tempfile import TemporaryDirectory
from pathlib import Path


def main():
    command = sys.argv[3]
    args = sys.argv[4:]
    with TemporaryDirectory() as temp_dir:
        copy(command, temp_dir)
        os.chroot(temp_dir)
        root = Path("/")
        command = root / Path(command).name
        os.unshare(os.CLONE_NEWPID)
        completed_process = subprocess.run([command, *args], capture_output=True)
        print(completed_process.stdout.decode(), end="")
        print(completed_process.stderr.decode(), file=sys.stderr, end="")
        exit(completed_process.returncode)


if __name__ == "__main__":
    main()
