# Dup Finder

Find duplicate files under a directory by grouping on size first, then hashing only the size-colliding candidates.

## Usage

```python
from dup_finder import find_duplicates

for group in find_duplicates("/path/to/dir"):
    print(f"{group.size} bytes, {len(group)} copies:")
    for p in group.paths:
        print(f"  {p}")
```

`find_duplicates(root: str) -> list[DuplicateGroup]` walks `root` recursively and returns a list of `DuplicateGroup(size: int, paths: tuple[str, ...])`. Each group has at least two identical files. Paths are absolute and sorted within each group; groups are sorted by size then by first path.

## Why

Hashing every file is wasteful when most files are unique. Grouping by `stat` size first means only files that could plausibly be duplicates get hashed. SHA-256 is used rather than MD5 or SHA-1 because collision resistance is the entire point of a dedup tool — a chosen-prefix collision would silently merge two different files.

## Edge cases

- **Symlinks are skipped**, not followed. A symlink pointing at a real file would otherwise inflate the duplicate count, and a dangling symlink would crash the walker.
- **Files that vanish mid-scan** (between the size check and the hash check) are silently dropped rather than raising. Temp files and concurrent writers make this a real possibility.
- **Empty files** are treated as duplicates of each other if two or more exist. This is correct by the byte-for-byte definition, even if it is rarely what you want. Filter them out by checking `group.size == 0` if needed.
