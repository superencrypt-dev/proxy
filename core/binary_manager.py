import os
import sys
import platform
import stat
import tarfile
import zipfile
import requests
from typing import Optional

class BinaryManager:
    SINGBOX_VERSION = "1.9.0"

    def __init__(self, bin_dir: str = "data/bin"):
        self.bin_dir = bin_dir
        os.makedirs(self.bin_dir, exist_ok=True)
        self.bin_path = os.path.join(self.bin_dir, "sing-box")

    def detect_arch(self) -> str:
        machine = platform.machine().lower()
        system = platform.system().lower()
        if system != "linux":
            system = "linux"
        
        if machine in ("x86_64", "amd64"):
            arch = "amd64"
        elif machine in ("aarch64", "arm64"):
            arch = "arm64"
        elif "armv7" in machine or "armv6" in machine:
            arch = "armv7"
        else:
            arch = "amd64"
        return f"{system}-{arch}"

    def is_available(self) -> bool:
        return os.path.isfile(self.bin_path) and os.access(self.bin_path, os.X_OK)

    def ensure_singbox(self) -> str:
        if self.is_available():
            return self.bin_path

        arch = self.detect_arch()
        url = f"https://github.com/SagerNet/sing-box/releases/download/v{self.SINGBOX_VERSION}/sing-box-{self.SINGBOX_VERSION}-{arch}.tar.gz"
        archive_path = os.path.join(self.bin_dir, "sing-box.tar.gz")

        print(f"[Core] Downloading sing-box binary ({arch}) v{self.SINGBOX_VERSION}...")
        resp = requests.get(url, stream=True, timeout=30)
        resp.raise_for_status()

        with open(archive_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)

        with tarfile.open(archive_path, "r:gz") as tar:
            for member in tar.getmembers():
                if member.name.endswith("/sing-box") or member.name == "sing-box":
                    member.name = os.path.basename(member.name)
                    if hasattr(tarfile, "data_filter"):
                        tar.extract(member, path=self.bin_dir, filter="data")
                    else:
                        tar.extract(member, path=self.bin_dir)
                    break

        if os.path.exists(archive_path):
            os.remove(archive_path)

        if os.path.exists(self.bin_path):
            os.chmod(self.bin_path, os.stat(self.bin_path).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            return self.bin_path

        raise FileNotFoundError("Gagal mengekstrak binary sing-box")
