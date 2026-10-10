"""Archive extraction guarded against path traversal, links and decompression bombs."""

from __future__ import annotations

import os
import zipfile
from pathlib import Path


class UnsafeArchive(RuntimeError):
    pass


DEFAULT_MAX_TOTAL = 2_000_000_000   # 2 GB uncompressed per archive
DEFAULT_MAX_RATIO = 200.0            # uncompressed / compressed
DEFAULT_MAX_MEMBERS = 50_000


def _safe_target(root: Path, name: str) -> Path:
    if name.startswith(("/", "\\")) or ":" in name.split("/")[0]:
        raise UnsafeArchive(f"absolute path in archive: {name!r}")
    target = (root / name).resolve()
    if os.path.commonpath([str(root.resolve()), str(target)]) != str(root.resolve()):
        raise UnsafeArchive(f"path traversal in archive: {name!r}")
    return target


def _check_budget(total: int, compressed: int, members: int, max_total: int, max_ratio: float) -> None:
    if members > DEFAULT_MAX_MEMBERS:
        raise UnsafeArchive(f"too many members: {members}")
    if total > max_total:
        raise UnsafeArchive(f"uncompressed size {total} exceeds limit {max_total}")
    if compressed > 0 and total / compressed > max_ratio:
        raise UnsafeArchive(f"compression ratio {total / compressed:.1f} exceeds {max_ratio}")


def extract_zip(archive: Path, dest: Path, max_total: int = DEFAULT_MAX_TOTAL,
                max_ratio: float = DEFAULT_MAX_RATIO) -> list[Path]:
    dest.mkdir(parents=True, exist_ok=True)
    out: list[Path] = []
    with zipfile.ZipFile(archive) as zf:
        infos = [i for i in zf.infolist() if not i.is_dir()]
        total = sum(i.file_size for i in infos)
        _check_budget(total, archive.stat().st_size, len(infos), max_total, max_ratio)
        for info in infos:
            mode = (info.external_attr >> 16) & 0o170000
            if mode == 0o120000:
                raise UnsafeArchive(f"symlink in archive: {info.filename!r}")
            target = _safe_target(dest, info.filename)
            target.parent.mkdir(parents=True, exist_ok=True)
            written = 0
            with zf.open(info) as src, target.open("wb") as dst:
                for chunk in iter(lambda: src.read(1 << 20), b""):
                    written += len(chunk)
                    if written > info.file_size:  # lying header
                        raise UnsafeArchive(f"member {info.filename!r} larger than declared")
                    dst.write(chunk)
            out.append(target)
    return out


def extract_7z(archive: Path, dest: Path, max_total: int = DEFAULT_MAX_TOTAL,
               max_ratio: float = DEFAULT_MAX_RATIO) -> list[Path]:
    import py7zr

    dest.mkdir(parents=True, exist_ok=True)
    with py7zr.SevenZipFile(archive, mode="r") as z:
        infos = [i for i in z.list() if not i.is_directory]
        total = sum(i.uncompressed for i in infos)
        _check_budget(total, archive.stat().st_size, len(infos), max_total, max_ratio)
        names = []
        for i in infos:
            if getattr(i, "is_symlink", False):
                raise UnsafeArchive(f"symlink in archive: {i.filename!r}")
            _safe_target(dest, i.filename)
            names.append(i.filename)
        z.extractall(path=dest)
    return [dest / n for n in names]
