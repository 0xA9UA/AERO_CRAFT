"""Shared paths, bounded archive handling, atomic output, and process helpers."""

from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = (
    Path(os.environ.get("AERO_CRAFT_HOME", ROOT / ".runtime")).expanduser().resolve()
)
MAX_ARCHIVE_BYTES = 4 * 1024**3
MAX_ENTRIES = 100000
IGNORED = {
    ".git",
    ".runtime",
    ".cache",
    ".dsh",
    ".aero",
    "node_modules",
    ".gradle",
    "build",
    "dist",
    "__pycache__",
    ".venv",
}


class CraftError(Exception):
    """An actionable user-facing failure."""


def read_json(path):
    with Path(path).open(encoding="utf-8-sig") as f:
        return json.load(f)


def atomic_write(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix="." + path.name, dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def write_json(path, value):
    atomic_write(
        path, json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    )


def sha256(path):
    with Path(path).open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def download(url, destination, digest):
    """HTTPS acquisition into a private temporary file; verify before publishing."""
    if not url.startswith("https://") or not re.fullmatch(r"[a-f0-9]{64}", digest):
        raise CraftError("Downloads require HTTPS and a pinned SHA-256.")
    destination = Path(destination)
    if destination.is_file() and sha256(destination) == digest:
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".download-", dir=destination.parent)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "AERO-CRAFT/0.1"})
        with os.fdopen(fd, "wb") as out, urllib.request.urlopen(
            req, timeout=120
        ) as response:
            if not response.url.startswith("https://"):
                raise CraftError("Refusing a non-HTTPS download redirect.")
            total = 0
            while chunk := response.read(1024 * 1024):
                total += len(chunk)
                if total > MAX_ARCHIVE_BYTES:
                    raise CraftError("Download exceeds 4 GiB.")
                out.write(chunk)
        if sha256(name) != digest:
            raise CraftError(
                f"SHA-256 mismatch for {url}; the existing installation was not replaced."
            )
        os.replace(name, destination)
        return destination
    finally:
        Path(name).unlink(missing_ok=True)


def member_path(name):
    p = PurePosixPath(name)
    if (
        not name
        or "\\" in name
        or p.is_absolute()
        or ".." in p.parts
        or any(":" in x for x in p.parts)
    ):
        raise CraftError(f"Unsafe archive member: {name!r}")
    return p


def check_zip(z):
    infos = z.infolist()
    if len(infos) > MAX_ENTRIES or sum(i.file_size for i in infos) > MAX_ARCHIVE_BYTES:
        raise CraftError("Archive expansion limit exceeded.")
    names = set()
    for i in infos:
        member_path(i.filename)
        canonical = str(PurePosixPath(i.filename)).casefold()
        if canonical in names:
            raise CraftError(f"Duplicate/case-colliding archive member: {i.filename}")
        names.add(canonical)
        if stat.S_ISLNK(i.external_attr >> 16) or i.flag_bits & 1:
            raise CraftError(
                f"Links and encrypted ZIP members are unsupported: {i.filename}"
            )
    return infos


def extract(archive, destination):
    """Extract only to a new directory; validate all members before writing."""
    destination = Path(destination)
    if destination.exists():
        raise CraftError(f"Extraction destination already exists: {destination}")
    destination.mkdir(parents=True)
    try:
        if zipfile.is_zipfile(archive):
            with zipfile.ZipFile(archive) as z:
                infos = check_zip(z)
                z.extractall(destination)
                if os.name != "nt":
                    for i in infos:
                        if not i.is_dir():
                            (destination / i.filename).chmod(
                                (i.external_attr >> 16 & 0o755) or 0o644
                            )
        else:
            with tarfile.open(archive) as t:
                members = t.getmembers()
                if (
                    len(members) > MAX_ENTRIES
                    or sum(m.size for m in members) > MAX_ARCHIVE_BYTES
                ):
                    raise CraftError("Archive expansion limit exceeded.")
                for m in members:
                    member_path(m.name)
                    if m.isdev() or m.isfifo():
                        raise CraftError(f"Special archive member: {m.name}")
                    if m.issym() or m.islnk():
                        base = (
                            (destination / m.name).parent if m.issym() else destination
                        )
                        if (
                            not (base / m.linkname)
                            .resolve()
                            .is_relative_to(destination.resolve())
                        ):
                            raise CraftError(f"Escaping archive link: {m.name}")
                if not hasattr(tarfile, "data_filter"):
                    raise CraftError(
                        "Safe TAR extraction needs Python 3.11.8+; update Python."
                    )
                t.extractall(destination, filter="data")
        return destination
    except BaseException:
        shutil.rmtree(destination)
        raise


def files(root):
    """Walk project files without following symlinks or build/cache directories."""
    root = Path(root).resolve()
    for directory, dirs, names in os.walk(root, followlinks=False):
        dirs[:] = sorted(
            d
            for d in dirs
            if d not in IGNORED and not (Path(directory) / d).is_symlink()
        )
        for name in sorted(names):
            p = Path(directory) / name
            if not p.is_symlink():
                yield p


def run(command, cwd=None, env=None, timeout=1800, output=None):
    result = subprocess.run(
        [str(x) for x in command], cwd=cwd, env=env, timeout=timeout,
        stdout=sys.stderr if output is None else output, stderr=sys.stderr,
    )
    if result.returncode:
        raise CraftError(
            f"Command failed with exit code {result.returncode}: {command[0]}"
        )
    return result.returncode
