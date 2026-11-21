import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from academy import gate, join, notes  # noqa: E402
from academy.util import duration  # noqa: E402


def lavfi(path, src, d=2):
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"{src}{':' if '=' in src else '='}s=320x180:r=30:d={d}", "-pix_fmt", "yuv420p", str(path)], check=True)


@unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg needed")
class Gate(unittest.TestCase):
    def test_static_film_measures_static_and_moving_film_does_not(self):
        with tempfile.TemporaryDirectory() as td:
            still, moving = Path(td) / "still.mp4", Path(td) / "moving.mp4"
            lavfi(still, "color=c=0x336699")
            lavfi(moving, "testsrc2", 3)
            s, m = gate.measure(still), gate.measure(moving)
            self.assertGreater(s["static_share"], 0.9)
            self.assertLess(m["static_share"], 0.5)

    def test_precheck_stops_a_more_static_cut(self):
        prev = {"mean_shot_s": 2.0, "cuts": 10, "cuts_how": "timeline", "static_share": 0.2, "words_per_card": 5}
        worse = dict(prev, static_share=0.5)
        fails, _ = gate.precheck(worse, prev)
        self.assertTrue(any("more static" in f for f in fails))
        self.assertEqual(gate.precheck(prev, prev)[0], [])

    def test_slower_is_a_stop_only_with_enough_cuts(self):
        prev = {"mean_shot_s": 2.0, "cuts": 10, "cuts_how": "timeline", "static_share": 0.2, "words_per_card": 5}
        slow = dict(prev, mean_shot_s=3.0)
        self.assertTrue(gate.precheck(slow, prev)[0])
        few = dict(slow, cuts=3, cuts_how="scene detector")
        self.assertFalse(gate.precheck(few, dict(prev, cuts=3, cuts_how="scene detector"))[0])

    def test_burst_of_tiny_shots_stops(self):
        t = [i * 0.4 for i in range(1, 14)]
        m = {"cuts": len(t), "cut_times": t, "seconds": 6.0}
        self.assertTrue(gate.cut_checks(m)[0])
        ok = {"cuts": 9, "cut_times": [i * 1.5 for i in range(1, 10)], "seconds": 15.0}
        self.assertEqual(gate.cut_checks(ok)[0], [])


class Notes(unittest.TestCase):
    def test_note_must_be_ticked_per_exact_file(self):
        with tempfile.TemporaryDirectory() as td:
            store, film = Path(td) / "n.json", Path(td) / "f.mp4"
            film.write_bytes(b"one")
            nid = notes.add(store, "the opening is too slow", "owner, today")
            self.assertEqual(len(notes.unticked(store, film)), 1)
            with self.assertRaises(SystemExit):
                notes.tick(store, nid, film, "somewhere")            # a tick must point into the film
            notes.tick(store, nid, film, "0:02")
            self.assertEqual(notes.unticked(store, film), [])
            film.write_bytes(b"two")                                  # a re-render is a new file: the tick does not carry over
            self.assertEqual(len(notes.unticked(store, film)), 1)
            self.assertEqual(json.loads(store.read_text())["notes"][0]["words"], "the opening is too slow")


@unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg needed")
class Join(unittest.TestCase):
    def test_join_overlaps_by_the_dissolve_and_moves_cues(self):
        with tempfile.TemporaryDirectory() as td:
            a, b, out = Path(td) / "a.mp4", Path(td) / "b.mp4", Path(td) / "o.mp4"
            lavfi(a, "testsrc2", 2); lavfi(b, "testsrc2", 2)
            b.with_suffix(".cues.json").write_text(json.dumps([{"t": 0.5, "sfx": "click"}]))
            join.join([a, b], out, 0.5)
            self.assertAlmostEqual(duration(out), 3.5, delta=0.1)
            self.assertAlmostEqual(json.loads(out.with_suffix(".cues.json").read_text())[0]["t"], 2.0, places=2)


if __name__ == "__main__":
    unittest.main()


class Project(unittest.TestCase):
    def test_new_writes_the_project_and_refuses_to_overwrite(self):
        from argparse import Namespace
        from academy import project
        with tempfile.TemporaryDirectory() as td:
            d = Path(td) / "acme"
            a = Namespace(name="Acme", promise="Plan your week in one tap.", hook=None, tagline=None, points="Inbox=cleared|Calendar=synced", slam=None, number="40%",
                          number_label="less email", action=None, url="acme.example", accent="#f5a524", dir=str(d), music=None, drop_bar=None, recording=None, rec_seconds=6)
            project.new(a)
            cfg = json.loads((d / "film.json").read_text())
            self.assertEqual(cfg["hook"], ["Plan your week", "in one tap."])
            self.assertEqual(cfg["points"], [["Inbox", "cleared"], ["Calendar", "synced"]])
            self.assertEqual(cfg["number"]["value"], 40.0)
            self.assertTrue((d / "film.html").exists() and (d / "plan.json").exists())
            with self.assertRaises(SystemExit):
                project.new(a)

    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg needed")
    def test_import_recording_makes_frames_and_updates_the_config(self):
        from argparse import Namespace
        from academy import project
        with tempfile.TemporaryDirectory() as td:
            rec, d = Path(td) / "rec.mp4", Path(td) / "p"
            lavfi(rec, "testsrc2", 3)
            project.new(Namespace(name="A", promise="Do it fast.", hook=None, tagline=None, points=None, slam=None, number=None, number_label=None, action=None,
                                  url=None, accent="#f5a524", dir=str(d), music=None, drop_bar=None, recording=None, rec_seconds=6))
            project.import_recording(rec, d, seconds=2)
            r = json.loads((d / "film.json").read_text())["recording"]
            self.assertEqual(r["n"], 60)
            self.assertEqual(r["bars"], 1)
            self.assertTrue((d / "assets" / "app" / "00060.jpg").exists())
