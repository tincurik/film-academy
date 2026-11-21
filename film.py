#!/usr/bin/env python3
"""film-academy command line.

  film.py new "<product name>" --promise "<what it does for the viewer>" [--points "Label=value|Label=value"] [--url ...]   start a film project
  film.py make films/<slug>                             render, sound, gate: a numbered build every time
  film.py import-recording screen.mov films/<slug>      a screen recording of a native app, as frames the film can show
  film.py check                                         is Chromium/Playwright, ffmpeg (and optionally tesseract) here?
  film.py render page.html out.mp4 [--fps 30 --size 1280x720 --workers 2]
  film.py stills page.html outdir 0.5,3,7.2             PNG frames to look at
  film.py join part1.mp4 part2.mp4 .. --out film.mp4    parts rendered separately, joined with dissolves (+ merged cues)
  film.py mix film.mp4 out.mp4 --plan plan.json [--music track.mp3] [--sfx dir] [--cues film.cues.json]
  film.py measure a.mp4 [b.mp4 ..] [--cards cards.json] [--timeline times.json]
  film.py gate --film new.mp4 [--against prev.mp4] [--refs ref.mp4 ..] [--cards cards.json] [--timeline times.json] [--bpm N] [--notes film-notes.json]
  film.py sheet film.mp4 sheet.jpg                      one frame per second on one image, for a reader that cannot play video
  film.py note "<their words, verbatim>" --source "who, date" [--means "your reading"]
  film.py tick N1 --film new.mp4 --where "0:04"
  film.py notes [--film new.mp4]
Gate exit codes: 0 pass, 5 pre-check failed (slower, more static, cut craft), 6 a note has no tick for this film file.
"""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from academy import notes as N  # noqa: E402

GATE_FAIL, GATE_NOTES_OPEN = 5, 6


def size_of(s):
    w, h = s.lower().split("x")
    return int(w), int(h)


def cmd_check(a):
    ok = True
    for tool in ("ffmpeg", "ffprobe"):
        p = shutil.which(tool)
        print(f"{tool}: {p or 'MISSING (install ffmpeg)'}")
        ok &= bool(p)
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            p.chromium.launch(headless=True).close()
        print("playwright + chromium: ok")
    except Exception as e:  # noqa: BLE001
        print(f"playwright + chromium: MISSING ({str(e).splitlines()[0][:120]}). pip install playwright && playwright install chromium")
        ok = False
    print(f"tesseract: {shutil.which('tesseract') or 'not installed (optional: words per card then needs --cards)'}")
    return 0 if ok else 1


def cmd_new(a):
    from academy import project
    project.new(a)


def cmd_make(a):
    from academy import project
    fps, size = (60, (1920, 1080)) if a.master else (a.fps, size_of(a.size))
    return project.make(a.dir, fps, size, a.workers)


def cmd_import(a):
    from academy import project
    project.import_recording(a.src, a.dir, a.name, a.fps, a.start, a.seconds, a.width)


def cmd_render(a):
    from academy import render
    render.render(a.html, a.out, a.fps, a.workers, size_of(a.size))


def cmd_stills(a):
    from academy import render
    for p in render.stills(a.html, a.outdir, [float(x) for x in a.times.split(",")], size_of(a.size)):
        print(p)


def cmd_join(a):
    from academy import join
    join.join(a.parts, a.out, a.dissolve)


def cmd_mix(a):
    from academy import mix
    plan = json.loads(Path(a.plan).read_text())
    cues = json.loads(Path(a.cues).read_text()) if a.cues else None
    mix.mix(a.film, a.out, plan, a.music, a.sfx, cues)


def cmd_measure(a):
    from academy import gate
    rows = [gate.measure(f, a.cards, a.timeline) for f in a.films]
    print(gate.table(rows))


def cmd_gate(a):
    from academy import gate
    if Path(a.notes).exists():
        open_notes = N.unticked(a.notes, a.film)
        if open_notes:
            print(f"GATE REFUSED: {len(open_notes)} note(s) have no tick for {Path(a.film).name}:")
            for n in open_notes:
                print(f'  {n["id"]}: "{n["words"]}"')
            print("tick each with where it is answered in this exact file: film.py tick N1 --film FILE --where 0:04")
            return GATE_NOTES_OPEN
    new = gate.measure(a.film, a.cards, a.timeline)
    new["label"] = "NEW " + new["name"]
    rows, fails, warns = [new], [], []
    if a.against:
        prev = gate.measure(a.against, a.cards, a.timeline)
        prev["label"] = "previous " + prev["name"]
        rows.append(prev)
        fails, warns = gate.precheck(new, prev)
    refs = [gate.measure(r, a.cards, a.timeline) for r in a.refs or []]
    for r in refs:
        r["label"] = "ref " + r["name"]
    rows += refs
    warns += gate.vs_refs(new, refs)
    cf, cw = gate.cut_checks(new, a.bpm)
    fails, warns = fails + cf, warns + cw
    if new["words_per_card"] is None:
        warns.append(f"words per card not measured: {new['words_how']}")
    print(gate.table(rows))
    print(f"cuts: {new['cuts']} by {new['cuts_how']}")
    for w in warns:
        print("  warning:", w)
    for f in fails:
        print("  FAIL:", f)
    print("GATE: " + ("PASS" if not fails else "STOPPED (fix the cut, render again, run the gate again)"))
    return GATE_FAIL if fails else 0


def cmd_sheet(a):
    from academy.util import duration
    n = max(1, int(duration(a.film)))
    cols = min(5, n)
    rows = -(-n // cols)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", a.film, "-an", "-vf", f"fps=1,scale=384:-1,tile={cols}x{rows}", "-frames:v", "1", "-q:v", "3", a.out], check=True)
    print(a.out)


def cmd_note(a):
    print(N.add(a.store, a.words, a.source, a.means))


def cmd_tick(a):
    N.tick(a.store, a.note, a.film, a.where)
    print(f"ticked {a.note}")


def cmd_notes(a):
    print(N.listing(a.store, a.film))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    x = sp.add_parser("check"); x.set_defaults(fn=cmd_check)
    x = sp.add_parser("new"); x.add_argument("name"); x.add_argument("--promise", required=True, help="the one thing the film promises, one sentence")
    x.add_argument("--hook", help="the opening in two lines, 'Brew tea|in 20 s.' (default: the promise split in two)"); x.add_argument("--tagline")
    x.add_argument("--points", help="proof rows, 'Label=value|Label=value' (up to 4)"); x.add_argument("--slam", help="two or three words that slam in, 'No setup.'")
    x.add_argument("--number", help="a number that grows, '4x' or '40%%'"); x.add_argument("--number-label"); x.add_argument("--action", help="the one press, 'One tap'")
    x.add_argument("--url", help="the one ask on the end card"); x.add_argument("--accent", default="#f5a524"); x.add_argument("--dir")
    x.add_argument("--music", help="your own track (a licence that lets you publish the film)"); x.add_argument("--drop-bar", type=int, help="the track's bar where its drop / last chord starts")
    x.add_argument("--recording", help="a screen recording of the product"); x.add_argument("--rec-seconds", type=float, default=6.0); x.set_defaults(fn=cmd_new)
    x = sp.add_parser("make"); x.add_argument("dir"); x.add_argument("--fps", type=int, default=30); x.add_argument("--size", default="1280x720")
    x.add_argument("--workers", type=int, default=2); x.add_argument("--master", action="store_true", help="1920x1080 at 60 fps"); x.set_defaults(fn=cmd_make)
    x = sp.add_parser("import-recording"); x.add_argument("src"); x.add_argument("dir"); x.add_argument("--name", default="app"); x.add_argument("--fps", type=int, default=30)
    x.add_argument("--start", type=float, default=0.0); x.add_argument("--seconds", type=float, default=6.0); x.add_argument("--width", type=int, default=1500); x.set_defaults(fn=cmd_import)
    x = sp.add_parser("render"); x.add_argument("html"); x.add_argument("out"); x.add_argument("--fps", type=int, default=30)
    x.add_argument("--size", default="1280x720"); x.add_argument("--workers", type=int, default=2); x.set_defaults(fn=cmd_render)
    x = sp.add_parser("stills"); x.add_argument("html"); x.add_argument("outdir"); x.add_argument("times"); x.add_argument("--size", default="1280x720"); x.set_defaults(fn=cmd_stills)
    x = sp.add_parser("join"); x.add_argument("parts", nargs="+"); x.add_argument("--out", required=True); x.add_argument("--dissolve", type=float, default=0.5); x.set_defaults(fn=cmd_join)
    x = sp.add_parser("mix"); x.add_argument("film"); x.add_argument("out"); x.add_argument("--plan", required=True); x.add_argument("--music"); x.add_argument("--sfx")
    x.add_argument("--cues"); x.set_defaults(fn=cmd_mix)
    x = sp.add_parser("measure"); x.add_argument("films", nargs="+"); x.add_argument("--cards"); x.add_argument("--timeline"); x.set_defaults(fn=cmd_measure)
    x = sp.add_parser("gate"); x.add_argument("--film", required=True); x.add_argument("--against"); x.add_argument("--refs", nargs="*"); x.add_argument("--cards")
    x.add_argument("--timeline"); x.add_argument("--bpm", type=float); x.add_argument("--notes", default=N.DEFAULT); x.set_defaults(fn=cmd_gate)
    x = sp.add_parser("sheet"); x.add_argument("film"); x.add_argument("out"); x.set_defaults(fn=cmd_sheet)
    x = sp.add_parser("note"); x.add_argument("words"); x.add_argument("--source", required=True); x.add_argument("--means", default="")
    x.add_argument("--store", default=N.DEFAULT); x.set_defaults(fn=cmd_note)
    x = sp.add_parser("tick"); x.add_argument("note"); x.add_argument("--film", required=True); x.add_argument("--where", required=True)
    x.add_argument("--store", default=N.DEFAULT); x.set_defaults(fn=cmd_tick)
    x = sp.add_parser("notes"); x.add_argument("--film"); x.add_argument("--store", default=N.DEFAULT); x.set_defaults(fn=cmd_notes)
    a = ap.parse_args(argv)
    return a.fn(a) or 0


if __name__ == "__main__":
    sys.exit(main())
