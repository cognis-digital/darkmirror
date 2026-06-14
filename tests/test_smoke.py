"""Smoke tests for DARKMIRROR. No network. Standard library only."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from darkmirror import (  # noqa: E402
    TOOL_NAME,
    TOOL_VERSION,
    normalize_posts,
    match_watchlist,
    diff_snapshots,
    summarize,
)
from darkmirror.cli import main  # noqa: E402

DEMO = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "demos", "01-basic")


RAW = [
    {"post_title": "acme-corp.com", "group_name": "lockbit3", "discovered": "2024-03-04 09:12:40.000000"},
    {"post_title": "acme-corp.com", "group_name": "lockbit3", "discovered": "2024-03-06 11:00:00.000000"},
    {"post_title": "globex-industries", "group_name": "lockbit3", "discovered": "2024-03-05 14:55:01.000000"},
    {"post_title": "some-unrelated-victim", "group_name": "play", "discovered": "2024-03-03 03:30:00.000000"},
]


class TestMeta(unittest.TestCase):
    def test_version_constants(self):
        self.assertEqual(TOOL_NAME, "darkmirror")
        self.assertTrue(TOOL_VERSION)


class TestNormalize(unittest.TestCase):
    def test_dedup_keeps_first_seen(self):
        posts = normalize_posts(RAW)
        # acme posted twice -> one entry
        self.assertEqual(len(posts), 3)
        acme = [p for p in posts if p.title == "acme-corp.com"][0]
        self.assertEqual(acme.discovered.day, 4)  # earliest kept

    def test_accepts_wrapped_object(self):
        posts = normalize_posts({"posts": RAW})
        self.assertEqual(len(posts), 3)

    def test_bad_input_raises(self):
        with self.assertRaises(ValueError):
            normalize_posts("not a list")


class TestMatch(unittest.TestCase):
    def setUp(self):
        self.posts = normalize_posts(RAW)

    def test_domain_match_scores_top(self):
        matches = match_watchlist(self.posts, ["acme-corp.com"])
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].score, 1.0)
        self.assertEqual(matches[0].post.title, "acme-corp.com")

    def test_label_fuzzy_match(self):
        matches = match_watchlist(self.posts, ["Globex"])
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].post.title, "globex-industries")

    def test_no_false_positive(self):
        matches = match_watchlist(self.posts, ["initech.io"])
        self.assertEqual(matches, [])


class TestDiff(unittest.TestCase):
    def test_added_detected(self):
        old = normalize_posts(RAW[:1] + RAW[3:])  # acme + unrelated
        new = normalize_posts(RAW)
        result = diff_snapshots(old, new)
        titles = {p.title for p in result["added"]}
        self.assertIn("globex-industries", titles)
        self.assertNotIn("acme-corp.com", titles)


class TestSummarize(unittest.TestCase):
    def test_counts(self):
        s = summarize(normalize_posts(RAW))
        self.assertEqual(s["total_posts"], 3)
        self.assertEqual(s["top_groups"][0]["group"], "lockbit3")


class TestCli(unittest.TestCase):
    def test_watch_json_exit_zero(self):
        rc = main(["--format", "json", "watch", os.path.join(DEMO, "snapshot.json"),
                   "-w", os.path.join(DEMO, "watchlist.txt")])
        self.assertEqual(rc, 0)

    def test_diff_exit_zero(self):
        rc = main(["diff", os.path.join(DEMO, "snapshot_prev.json"),
                   os.path.join(DEMO, "snapshot.json")])
        self.assertEqual(rc, 0)

    def test_stats_exit_zero(self):
        rc = main(["stats", os.path.join(DEMO, "snapshot.json")])
        self.assertEqual(rc, 0)

    def test_missing_file_nonzero(self):
        rc = main(["stats", os.path.join(DEMO, "does_not_exist.json")])
        self.assertNotEqual(rc, 0)

    def test_watch_requires_terms(self):
        rc = main(["watch", os.path.join(DEMO, "snapshot.json")])
        self.assertNotEqual(rc, 0)



class TestHardening(unittest.TestCase):
    """Tests for input validation, error handling, and edge cases."""

    def test_missing_file_returns_nonzero(self):
        """stats on a non-existent file must exit non-zero with no traceback."""
        rc = main(["stats", "/no/such/snapshot.json"])
        self.assertNotEqual(rc, 0)

    def test_malformed_json_returns_nonzero(self):
        """Non-JSON content in snapshot file must produce exit code 1."""
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as tf:
            tf.write("{this is not json}")
            name = tf.name
        try:
            rc = main(["stats", name])
            self.assertEqual(rc, 1)
        finally:
            os.unlink(name)

    def test_invalid_json_type_returns_nonzero(self):
        """Valid JSON but wrong root type (string) must exit non-zero."""
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as tf:
            tf.write('"just a string"')
            name = tf.name
        try:
            rc = main(["stats", name])
            self.assertNotEqual(rc, 0)
        finally:
            os.unlink(name)

    def test_threshold_above_one_returns_two(self):
        """--threshold > 1.0 must exit 2 with a clear error."""
        snap = os.path.join(DEMO, "snapshot.json")
        rc = main(["watch", snap, "-t", "acme", "--threshold", "1.5"])
        self.assertEqual(rc, 2)

    def test_threshold_zero_returns_two(self):
        """--threshold == 0 must exit 2 (not silently return garbage results)."""
        snap = os.path.join(DEMO, "snapshot.json")
        rc = main(["watch", snap, "-t", "acme", "--threshold", "0"])
        self.assertEqual(rc, 2)

    def test_threshold_negative_returns_two(self):
        """Negative --threshold must exit 2."""
        snap = os.path.join(DEMO, "snapshot.json")
        rc = main(["watch", snap, "-t", "acme", "--threshold", "-0.5"])
        self.assertEqual(rc, 2)

    def test_directory_as_snapshot_returns_nonzero(self):
        """Passing a directory path as snapshot must exit non-zero without traceback."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            rc = main(["stats", tmpdir])
        self.assertNotEqual(rc, 0)

    def test_empty_snapshot_returns_zero(self):
        """Empty JSON array is valid input; must exit 0 with zero posts reported."""
        import tempfile, io
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as tf:
            tf.write("[]")
            name = tf.name
        try:
            captured = io.StringIO()
            import sys as _sys
            old_stdout = _sys.stdout
            _sys.stdout = captured
            rc = main(["stats", name])
            _sys.stdout = old_stdout
            self.assertEqual(rc, 0)
            self.assertIn("0 posts", captured.getvalue())
        finally:
            os.unlink(name)

    def test_normalize_empty_list(self):
        """normalize_posts([]) must return an empty list without error."""
        from darkmirror.core import normalize_posts
        result = normalize_posts([])
        self.assertEqual(result, [])

    def test_match_watchlist_empty_posts(self):
        """match_watchlist on empty posts list must return empty list."""
        from darkmirror.core import match_watchlist
        result = match_watchlist([], ["acme"])
        self.assertEqual(result, [])

    def test_diff_snapshots_empty(self):
        """diff_snapshots on two empty lists must return zero added/removed."""
        from darkmirror.core import diff_snapshots
        result = diff_snapshots([], [])
        self.assertEqual(result["added"], [])
        self.assertEqual(result["removed"], [])

    def test_summarize_empty(self):
        """summarize([]) must return zero counts, not raise."""
        from darkmirror.core import summarize
        s = summarize([])
        self.assertEqual(s["total_posts"], 0)
        self.assertEqual(s["distinct_groups"], 0)


if __name__ == "__main__":
    unittest.main()
