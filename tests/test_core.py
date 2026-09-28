import os
import tempfile
import unittest

from dup_finder import find_duplicates, DuplicateGroup


class TestFindDuplicates(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = self.tmp.name

    def _write(self, relpath, content):
        """Write a file under root, creating parent dirs as needed."""
        full = os.path.join(self.root, relpath)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "wb") as f:
            if isinstance(content, str):
                content = content.encode("utf-8")
            f.write(content)
        return full

    def test_no_duplicates(self):
        self._write("a.txt", b"hello")
        self._write("b.txt", b"world")
        self._write("c.txt", b"different content here")
        result = find_duplicates(self.root)
        self.assertEqual(result, [])

    def test_simple_duplicate(self):
        p1 = self._write("a.txt", b"same")
        p2 = self._write("sub/b.txt", b"same")
        result = find_duplicates(self.root)
        self.assertEqual(len(result), 1)
        group = result[0]
        self.assertEqual(group.size, 4)
        self.assertEqual(set(group.paths), {os.path.abspath(p1), os.path.abspath(p2)})

    def test_different_content_same_size_not_duplicate(self):
        self._write("a.txt", b"abcd")
        self._write("b.txt", b"efgh")
        result = find_duplicates(self.root)
        self.assertEqual(result, [])

    def test_multiple_groups(self):
        p1 = self._write("a.txt", b"one")
        p2 = self._write("b.txt", b"one")
        p3 = self._write("c.txt", b"two!!")
        p4 = self._write("d.txt", b"two!!")
        result = find_duplicates(self.root)
        self.assertEqual(len(result), 2)
        sizes = {g.size for g in result}
        self.assertEqual(sizes, {3, 5})

    def test_three_way_duplicate(self):
        paths = [self._write(f"f{i}.txt", b"triple") for i in range(3)]
        result = find_duplicates(self.root)
        self.assertEqual(len(result), 1)
        self.assertEqual(len(result[0]), 3)
        self.assertEqual(set(result[0].paths), {os.path.abspath(p) for p in paths})

    def test_empty_files_are_duplicates(self):
        p1 = self._write("a.txt", b"")
        p2 = self._write("b.txt", b"")
        result = find_duplicates(self.root)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].size, 0)
        self.assertEqual(len(result[0].paths), 2)

    def test_single_empty_file_not_duplicate(self):
        self._write("a.txt", b"")
        self._write("b.txt", b"x")
        result = find_duplicates(self.root)
        self.assertEqual(result, [])

    def test_paths_are_absolute(self):
        self._write("a.txt", b"data")
        self._write("b.txt", b"data")
        result = find_duplicates(self.root)
        for p in result[0].paths:
            self.assertTrue(os.path.isabs(p))

    def test_paths_sorted_within_group(self):
        self._write("z.txt", b"data")
        self._write("a.txt", b"data")
        self._write("m.txt", b"data")
        result = find_duplicates(self.root)
        paths = result[0].paths
        self.assertEqual(list(paths), sorted(paths))

    def test_groups_sorted_by_size(self):
        self._write("a.txt", b"short")
        self._write("b.txt", b"short")
        self._write("c.txt", b"longer content")
        self._write("d.txt", b"longer content")
        result = find_duplicates(self.root)
        self.assertEqual([g.size for g in result], [5, 14])

    def test_symlink_skipped(self):
        if not hasattr(os, "symlink"):
            self.skipTest("symlinks not supported")
        real = self._write("real.txt", b"data")
        self._write("copy.txt", b"data")
        link_path = os.path.join(self.root, "link.txt")
        os.symlink(real, link_path)
        result = find_duplicates(self.root)
        # The symlink should not be counted, so only real.txt and copy.txt
        # form the pair — two files, not three.
        self.assertEqual(len(result), 1)
        self.assertEqual(len(result[0].paths), 2)
        abspaths = set(result[0].paths)
        self.assertNotIn(os.path.abspath(link_path), abspaths)

    def test_single_file_as_root(self):
        p = self._write("only.txt", b"lonely")
        result = find_duplicates(p)
        self.assertEqual(result, [])

    def test_duplicate_group_is_frozen(self):
        p1 = self._write("a.txt", b"x")
        p2 = self._write("b.txt", b"x")
        result = find_duplicates(self.root)
        with self.assertRaises(Exception):
            result[0].size = 999

    def test_duplicate_group_len(self):
        self._write("a.txt", b"x")
        self._write("b.txt", b"x")
        result = find_duplicates(self.root)
        self.assertEqual(len(result[0]), 2)

    def test_nested_directories(self):
        p1 = self._write("deep/nested/path/a.txt", b"content")
        p2 = self._write("other/place/b.txt", b"content")
        result = find_duplicates(self.root)
        self.assertEqual(len(result), 1)
        self.assertEqual(set(result[0].paths),
                         {os.path.abspath(p1), os.path.abspath(p2)})

    def test_large_files_dedup(self):
        data = os.urandom(70000)  # spans multiple read chunks
        p1 = self._write("a.bin", data)
        p2 = self._write("b.bin", data)
        p3 = self._write("c.bin", os.urandom(70000))
        result = find_duplicates(self.root)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].size, 70000)
        self.assertEqual(set(result[0].paths),
                         {os.path.abspath(p1), os.path.abspath(p2)})


if __name__ == "__main__":
    unittest.main()
