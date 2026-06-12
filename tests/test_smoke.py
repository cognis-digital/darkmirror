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


if __name__ == "__main__":
    unittest.main()
