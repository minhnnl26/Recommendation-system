"""Small adversarial fixture checks accounting and recommender-specific metrics."""

import tempfile
import unittest
from pathlib import Path

import duckdb
from lastfm_eda import analyze, fingerprint, load_events, make_outputs, one


class EDATest(unittest.TestCase):
    def test_missing_duplicate_replay_and_temporal_filter(self):
        track = "11111111-1111-4111-8111-111111111111"
        other = "22222222-2222-4222-8222-222222222222"
        first = f"u1\t2009-01-01T01:00:00Z\t\tArtist\t{track}\tSong"
        lines = [
            first,
            first,
            f"u1\t2009-01-02T01:00:00Z\t\tArtist\t{track}\tSong",
            f"u2\t2009-04-02T01:00:00Z\t\tOther\t{other}\tOther Song",
            f"u1\t2013-01-01T01:00:00Z\t\tArtist\t{track}\tSong",
            "u1\t2009-01-01T01:00:00Z\t\tArtist\t\tSong",
            f"u1\tbad-time\t\tArtist\t{track}\tSong",
            "broken\tline",
        ]
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "fixture.tsv"
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            with duckdb.connect() as con:
                con.execute("SET TimeZone='UTC'")
                load_events(con, path, "2009-05-05")
                m = analyze(con, "2009-05-05")
                self.assertEqual(m["parsed_rows"], 7)
                self.assertEqual(m["malformed_lines"], 1)
                self.assertEqual(m["missing"]["track_id"], 1)
                self.assertEqual(m["invalid_timestamps"], 1)
                self.assertEqual(m["after_source_cutoff"], 1)
                self.assertEqual(m["exact_duplicates_removed"], 1)
                self.assertEqual(m["clean_events"], 3)
                self.assertEqual(m["users"], 2)
                self.assertEqual(m["tracks"], 2)
                self.assertEqual(m["unique_user_song_pairs"], 2)
                self.assertAlmostEqual(m["sparsity"], 0.5)
                self.assertAlmostEqual(m["repeat_event_fraction"], 1 / 3)
                self.assertEqual(one(con, "SELECT max(plays) FROM pairs"), 2)
                self.assertEqual(fingerprint(path)["physical_lines"], 8)
                output = Path(temp) / "output"
                make_outputs(con, output)
                self.assertTrue((output / "monthly.csv").is_file())
                self.assertGreater((output / "overview.png").stat().st_size, 1000)


if __name__ == "__main__":
    unittest.main()
