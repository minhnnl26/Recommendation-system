import bz2
import tempfile
import unittest
from pathlib import Path

import duckdb
from music4all_audit import coverage, metadata


class Music4AllTest(unittest.TestCase):
    def test_zero_features_duplicate_tags_and_weighted_coverage(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with bz2.open(root / "id_genres_tf-idf.tsv.bz2", "wt") as f:
                f.write("id\trock\tjazz\na\t1\t0\nb\t0\t0\nc\t0\t2\n")
            with bz2.open(root / "id_tags_dict.tsv.bz2", "wt") as f:
                f.write(
                    "id\t(tag, weight)\na\t{'rock': 100}\n"
                    "a\t{'happy': 1}\nb\t{}\nc\t{'jazz': 5}\n"
                )
            stats, rows = metadata(root)
            self.assertEqual(stats["genre_tracks_zero"], 1)
            self.assertEqual(stats["duplicate_tag_id_rows"], 1)
            self.assertEqual(stats["conflicting_tag_ids"], 1)
            self.assertEqual(stats["tag_unique_ids"], 3)
            self.assertEqual(stats["metadata_both_nonempty"], 2)
            self.assertEqual(dict(stats["top_tags"])["rock"], 1)
            path = root / "pairs.tsv"
            path.write_text(
                "user_id\ttrack_id\tcount\nu1\ta\t2\nu1\tb\t3\n"
                "u2\tc\t4\nu2\tx\t1\nu1\ta\t2\n",
                encoding="utf-8",
            )
            with duckdb.connect() as con:
                result = coverage(con, path, rows)
            self.assertEqual(result["pair_rows"], 5)
            self.assertEqual(result["unique_pairs"], 4)
            self.assertEqual(result["duplicate_pair_rows"], 1)
            self.assertAlmostEqual(result["sparsity"], 0.5)
            both = result["coverage"]["both_nonempty"]
            self.assertEqual(both["tracks"], 2)
            self.assertAlmostEqual(both["track_fraction"], 0.5)
            self.assertAlmostEqual(both["pair_row_fraction"], 3 / 5)
            self.assertAlmostEqual(both["play_fraction"], 8 / 12)


if __name__ == "__main__":
    unittest.main()
