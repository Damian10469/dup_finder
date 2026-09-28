from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from typing import Iterable, Iterator


@dataclass(frozen=True)
class DuplicateGroup:
    """A set of files that are byte-for-byte identical.

    ``size`` is the shared size in bytes. ``paths`` are absolute paths, sorted
    for deterministic output. A group always has at least two members — a lone
    file is not a duplicate of anything.
    """
    size: int
    paths: tuple[str, ...]

    def __len__(self) -> int:
        return len(self.paths)


def _iter_files(root: str) -> Iterator[str]:
    """Yield absolute paths to regular files under ``root``.

    Symlinks are skipped: a symlink's target may not exist, and following one
    would risk double-counting the same file. ``os.walk(followlinks=False)``
    is the default, but we also reject symlinks at the top level in case the
    caller passes one directly.
    """
    if os.path.islink(root):
        return
    if os.path.isfile(root):
        yield os.path.abspath(root)
        return
    for dirpath, dirnames, filenames in os.walk(root):
        # Mutating dirnames in place prunes the walk, which is cheaper than
        # descending and then ignoring the results.
        dirnames[:] = [d for d in dirnames if not os.path.islink(os.path.join(dirpath, d))]
        for name in filenames:
            full = os.path.join(dirpath, name)
            if os.path.islink(full):
                continue
            if os.path.isfile(full):
                yield os.path.abspath(full)


def _file_size(path: str) -> int | None:
    """Return file size, or ``None`` if the file vanished between listing and stat.

    Files can disappear mid-scan (temp files, concurrent writers). We treat
    that as "not a duplicate" rather than crashing, because the caller's
    intent is to find duplicates among files that exist.
    """
    try:
        return os.path.getsize(path)
    except OSError:
        return None


def _hash_file(path: str, chunk_size: int = 65536) -> str | None:
    """Return the SHA-256 hex digest of ``path``, or ``None`` on read error.

    SHA-256 over MD5/SHA-1 because collision resistance still matters for a
    dedup tool — a chosen-prefix collision in MD5 would make two different
    files look identical. The cost difference is negligible for this use case.
    """
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(chunk_size), b""):
                h.update(chunk)
    except OSError:
        return None
    return h.hexdigest()


def find_duplicates(root: str) -> list[DuplicateGroup]:
    """Find duplicate files under ``root``.

    Strategy: group by size first (a single ``stat`` call), then only hash
    files that share a size with at least one other file. This avoids hashing
    unique files, which is the expensive part.

    Returns a list of :class:`DuplicateGroup`, sorted by size then by the
    first path in each group, so output is deterministic across runs and
    filesystem traversal orders.

    A file that disappears between the size check and the hash check is
    silently dropped. A file that raises during hashing is also dropped.
    """
    by_size: dict[int, list[str]] = {}
    for path in _iter_files(root):
        size = _file_size(path)
        if size is None:
            continue
        by_size.setdefault(size, []).append(path)

    groups: list[DuplicateGroup] = []
    for size, paths in by_size.items():
        if len(paths) < 2:
            continue
        by_hash: dict[str, list[str]] = {}
        for p in paths:
            digest = _hash_file(p)
            if digest is None:
                continue
            by_hash.setdefault(digest, []).append(p)
        for dup_paths in by_hash.values():
            if len(dup_paths) < 2:
                continue
            ordered = tuple(sorted(dup_paths))
            groups.append(DuplicateGroup(size=size, paths=ordered))

    groups.sort(key=lambda g: (g.size, g.paths[0]))
    return groups
