from __future__ import annotations

import hashlib
import io
import shutil
import tarfile
from pathlib import Path
from typing import Final

import httpx

VERSION: Final = "1.13.19"
ARCHIVE_NAME: Final = f"sing-box-{VERSION}-linux-amd64-glibc.tar.gz"
DOWNLOAD_URL: Final = (
    "https://api.github.com/repos/SagerNet/sing-box/releases/assets/517910421"
)
EXPECTED_SHA256: Final = (
    "77e26226c111b8a269f559aec7999f6f5ae1961f25374b58b126d06405d4f516"
)
MEMBER_NAME: Final = f"sing-box-{VERSION}-linux-amd64-glibc/sing-box"
TARGET_PATH: Final = Path(__file__).resolve().parents[1] / "vendor" / "sing-box"


def main() -> None:
    with httpx.Client(
        follow_redirects=True,
        headers={
            "Accept": "application/octet-stream",
            "User-Agent": "hh-relay-build",
        },
        timeout=120,
    ) as client:
        response = client.get(DOWNLOAD_URL)
        response.raise_for_status()
        archive_bytes = response.content

    actual_sha256 = hashlib.sha256(archive_bytes).hexdigest()
    if actual_sha256 != EXPECTED_SHA256:
        msg = f"Unexpected sing-box SHA-256: {actual_sha256}"
        raise RuntimeError(msg)

    with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:gz") as archive:
        member = archive.getmember(MEMBER_NAME)
        source = archive.extractfile(member)
        if source is None:
            msg = f"Missing {MEMBER_NAME} in sing-box archive"
            raise RuntimeError(msg)
        TARGET_PATH.parent.mkdir(parents=True, exist_ok=True)
        with TARGET_PATH.open("wb") as target:
            shutil.copyfileobj(source, target)

    TARGET_PATH.chmod(0o755)


if __name__ == "__main__":
    main()
